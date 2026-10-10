"""能力驱动的模型运行时门面。"""

from __future__ import annotations

from collections.abc import Sequence
import threading
from uuid import uuid4

from stegopot.domain.interface.events import EventBus
from stegopot.domain.interface.runtime import ModelAdapter, TokenGenerationSession
from stegopot.domain.model.capability import Capability, MissingCapabilityError
from stegopot.domain.model.intervention_runtime import Intervention
from stegopot.domain.model.reference import TracePolicy
from stegopot.domain.model.runtime import ForwardResult, GenerationConfig, ModelInput


class ModelRuntime:
  """统一能力检查、持久干预和 Adapter 生命周期。"""

  def __init__(
      self, adapter: ModelAdapter, *, event_bus: EventBus | None = None,
      own_adapter: bool = True,
  ) -> None:
    """初始化运行时。

    参数：
      adapter: 实现统一模型后端契约的实例。
      event_bus: 可选实验级事件总线；为空时只执行模型而不广播。
      own_adapter: close 时是否同时关闭 adapter。
    """
    self.adapter = adapter
    self.event_bus = event_bus
    self.own_adapter = bool(own_adapter)
    self._registered: dict[str, Intervention] = {}
    self._lock = threading.RLock()
    self._closed = False

  @property
  def capabilities(self) -> frozenset[Capability]:
    """返回后端实际能力的不可变副本。"""
    return frozenset(self.adapter.capabilities)

  def require(self, capabilities: Sequence[Capability | str]) -> None:
    """在创建模型调用前验证所需能力。"""
    required = frozenset(Capability(item) for item in capabilities)
    if not required.issubset(self.capabilities):
      raise MissingCapabilityError(required, self.capabilities)

  def register(self, intervention: Intervention):
    """注册跨调用生效的干预并返回幂等取消函数。"""
    with self._lock:
      self._ensure_open()
      if intervention.intervention_id in self._registered:
        raise ValueError(f"干预 ID 重复：{intervention.intervention_id}")
      self._registered[intervention.intervention_id] = intervention
    removed = False

    def unregister() -> None:
      """移除本次注册的干预。"""
      nonlocal removed
      with self._lock:
        if not removed:
          self._registered.pop(intervention.intervention_id, None)
          removed = True

    return unregister

  def forward(
      self, inputs: ModelInput, *, policy: TracePolicy | None = None,
      interventions: Sequence[Intervention] = (), run_id: str | None = None,
  ) -> ForwardResult:
    """执行普通、追踪、梯度感知或干预前向。"""
    self._ensure_open()
    resolved_policy = policy or TracePolicy(profile="none")
    active = self._active(interventions)
    required = [Capability.FORWARD]
    if resolved_policy.enabled:
      required.append(Capability.ACTIVATION_READ)
    if resolved_policy.retain_gradients:
      required.append(Capability.GRADIENT_READ)
    if active:
      required.append(Capability.ACTIVATION_WRITE)
    self.require(required)
    return self.adapter.forward(
        inputs, policy=resolved_policy, interventions=active,
        run_id=run_id or f"forward-{uuid4().hex}", event_sink=self.event_bus)

  def generate_session(
      self, inputs: ModelInput, *, config: GenerationConfig,
      policy: TracePolicy | None = None,
      interventions: Sequence[Intervention] = (), run_id: str | None = None,
  ) -> TokenGenerationSession:
    """创建逐 token 可检查、可重算、可提交的生成会话。"""
    self._ensure_open()
    resolved_policy = policy or TracePolicy(profile="none")
    active = self._active(interventions)
    required = [Capability.GENERATION, Capability.TOKEN_STEP_CONTROL]
    if resolved_policy.enabled:
      required.append(Capability.ACTIVATION_READ)
    if resolved_policy.retain_gradients:
      required.append(Capability.GRADIENT_READ)
    if active:
      required.append(Capability.ACTIVATION_WRITE)
    self.require(required)
    return self.adapter.open_generation_session(
        inputs, config=config, policy=resolved_policy, interventions=active,
        run_id=run_id or f"generation-{uuid4().hex}", event_sink=self.event_bus)

  def clear_gradients(self) -> None:
    """释放后端参数梯度，同时保留模型权重和已分离工件。"""
    self._ensure_open()
    self.require((Capability.GRADIENT_READ,))
    self.adapter.clear_gradients()

  def close(self) -> None:
    """清除注册干预并按所有权关闭 Adapter。"""
    with self._lock:
      if self._closed:
        return
      self._registered.clear()
      self._closed = True
    if self.own_adapter:
      self.adapter.close()

  def _active(self, values: Sequence[Intervention]) -> tuple[Intervention, ...]:
    """合并注册和单次干预并拒绝 ID 冲突。"""
    with self._lock:
      merged = (*self._registered.values(), *tuple(values))
    identifiers = [item.intervention_id for item in merged]
    if len(set(identifiers)) != len(identifiers):
      raise ValueError("注册干预和单次干预的 ID 不能重复")
    return tuple(sorted(merged, key=lambda item: (item.priority, item.intervention_id)))

  def _ensure_open(self) -> None:
    """拒绝在关闭后创建新的模型调用。"""
    if self._closed:
      raise RuntimeError("ModelRuntime 已关闭")
