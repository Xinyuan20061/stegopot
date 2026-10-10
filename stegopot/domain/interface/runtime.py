"""模型适配器、可控运行时和逐 token 会话协议。"""

from collections.abc import Sequence
from typing import Any, Callable, Protocol

from stegopot.domain.interface.events import EventSink
from stegopot.domain.model.capability import Capability
from stegopot.domain.model.intervention_runtime import Intervention
from stegopot.domain.model.reference import ResolvedTensorRef, TensorRef, TracePolicy
from stegopot.domain.model.runtime import (
    ForwardResult,
    GenerationConfig,
    GenerationResult,
    ModelInput,
)
from stegopot.domain.model.trace import ActivationRecord


class GenerationStep(Protocol):
  """token 提交前可检查、重算和采样的一步生成。"""

  @property
  def index(self) -> int:
    """返回零基生成步骤。"""
    ...

  @property
  def result(self) -> ForwardResult:
    """返回当前尚未提交 token 的前向结果。"""
    ...

  def inspect(self, ref: TensorRef) -> ActivationRecord:
    """读取当前步骤已请求的激活。"""
    ...

  def apply(self, interventions: Sequence[Intervention]) -> "GenerationStep":
    """在采样前用附加干预重新执行当前步骤。"""
    ...

  def sample(self) -> int:
    """按会话采样参数选择但不提交 token。"""
    ...


class TokenGenerationSession(Protocol):
  """控制每个 token 前向、采样与提交边界的会话。"""

  @property
  def finished(self) -> bool:
    """返回会话是否达到停止条件。"""
    ...

  def forward_next(self, interventions: Sequence[Intervention] = ()) -> GenerationStep:
    """计算下一 token 的 logits 和选择性内部状态。"""
    ...

  def commit(self, token_id: int) -> None:
    """提交当前步骤采样得到的一个 token。"""
    ...

  def result(self) -> GenerationResult:
    """在完成后返回生成 token、文本和各步轨迹。"""
    ...

  def close(self) -> None:
    """移除 Hook 并释放会话资源。"""
    ...


class ModelAdapter(Protocol):
  """把任意模型生态映射到 StegoPot 运行能力。"""

  @property
  def adapter_id(self) -> str:
    """返回后端适配器 ID。"""
    ...

  @property
  def model_id(self) -> str:
    """返回模型与权重版本标识。"""
    ...

  @property
  def capabilities(self) -> frozenset[Capability]:
    """返回当前实例实际支持的能力。"""
    ...

  def resolve(self, ref: TensorRef) -> ResolvedTensorRef:
    """把逻辑 TensorRef 解析为精确后端位置。"""
    ...

  def forward(
      self,
      inputs: ModelInput,
      *,
      policy: TracePolicy,
      interventions: Sequence[Intervention],
      run_id: str,
      step_index: int | None = None,
      event_sink: EventSink | None = None,
  ) -> ForwardResult:
    """执行一次可选择采集、保留梯度和干预的模型前向。"""
    ...

  def open_generation_session(
      self,
      inputs: ModelInput,
      *,
      config: GenerationConfig,
      policy: TracePolicy,
      interventions: Sequence[Intervention],
      run_id: str,
      event_sink: EventSink | None = None,
  ) -> TokenGenerationSession:
    """创建逐 token 可控生成会话。"""
    ...

  def clear_gradients(self) -> None:
    """释放参数梯度；不修改模型权重或已分离的轨迹。"""
    ...

  def close(self) -> None:
    """释放模型和后端资源。"""
    ...


class ControlledRuntime(Protocol):
  """Scenario、Analyzer 和 Probe 共同依赖的公开运行时。"""

  @property
  def capabilities(self) -> frozenset[Capability]:
    """返回经运行时暴露的后端能力。"""
    ...

  def forward(
      self, inputs: ModelInput, *, policy: TracePolicy | None = None,
      interventions: Sequence[Intervention] = (), run_id: str | None = None,
  ) -> ForwardResult:
    """执行可控前向。"""
    ...

  def generate_session(
      self, inputs: ModelInput, *, config: GenerationConfig,
      policy: TracePolicy | None = None,
      interventions: Sequence[Intervention] = (), run_id: str | None = None,
  ) -> TokenGenerationSession:
    """创建逐 token 生成会话。"""
    ...

  def register(self, intervention: Intervention) -> Callable[[], None]:
    """注册跨调用生效的干预并返回取消函数。"""
    ...

  def clear_gradients(self) -> None:
    """释放后端参数梯度，供重复白盒实验控制显存。"""
    ...

  def close(self) -> None:
    """释放适配器所有权。"""
    ...
