"""协作式取消与分层预算；不依赖配置读取、模型供应商和日志实现。"""

from collections.abc import Callable, Mapping
import json
import threading
import time
from typing import Any, Literal

from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.model.execution import CancellationToken, ExecutionStopped


class ExecutionBudget:
  """整组实验的控制状态；一次运行一个实例，试验作用域只共享全局额度。"""

  def __init__(
      self, limits: Mapping[str, Any], *, cancellation: CancellationToken | None = None,
      clock: Callable[[], float] = time.monotonic,
  ) -> None:
    """初始化有限预算。

    参数：
      limits: 已校验运行参数；本对象不读取文件或修改该映射。
      cancellation: 调用方持有的取消令牌；为空时创建本次内部令牌。
      clock: 单调时钟，默认真实时间；可注入确定性时钟做契约测试。
    """
    self._limits = dict(limits)
    self._token = cancellation or CancellationToken()
    self._clock = clock
    self._deadline = clock() + limits["max_seconds"]
    self._lock = threading.RLock()
    self._calls = {"model": 0, "tool": 0}
    self._tokens = 0
    self._unknown_usage = 0
    self._stopped: ExecutionStopped | None = None
    self._scopes: dict[str, _TrialGuard] = {}
    self._global = _TrialGuard(self, global_only=True)

  def global_scope(self) -> ExecutionGuard:
    """返回中央评价作用域，只受全局额度限制，不占用任意实验节点的局部额度。"""
    return self._global

  def for_trial(self, trial_id: str) -> ExecutionGuard:
    """返回 trial_id 独享的局部计数器；同一 ID 重复获取不会重置已使用预算。"""
    with self._lock:
      if trial_id not in self._scopes:
        self._scopes[trial_id] = _TrialGuard(self)
      return self._scopes[trial_id]

  def snapshot(self) -> dict[str, Any]:
    """返回研究用计数副本；未知 token 用量明确计数，不解释为免费调用。"""
    with self._lock:
      return {"model_calls": self._calls["model"], "tool_calls": self._calls["tool"],
              "reported_total_tokens": self._tokens, "calls_without_token_usage": self._unknown_usage,
              "stop_reason": self._stopped.code if self._stopped else None}

  def _checkpoint(self) -> None:
    """在持锁状态下检查全局停止；第一次原因固定，不改写已有失败分类。"""
    if self._stopped is None:
      if self._token.cancelled:
        self._stopped = ExecutionStopped("cancelled")
      elif self._clock() >= self._deadline:
        self._stopped = ExecutionStopped("deadline_exceeded", resource="max_seconds")
    if self._stopped is not None:
      raise self._stopped


class _TrialGuard:
  """ExecutionGuard 的试验级实现；不拥有注入资源，不强制终止正在进行的调用。"""

  def __init__(self, owner: ExecutionBudget, *, global_only: bool = False) -> None:
    """绑定 owner；global_only 为中央评价提供仅全局计数的作用域。"""
    self._owner = owner
    self._calls = {"model": 0, "tool": 0}
    self._nodes: dict[tuple[str, str], int] = {}
    self._stopped: ExecutionStopped | None = None
    self._global_only = global_only

  def checkpoint(self) -> None:
    """检查全局与本试验状态；取消和时间上限只在该方法被调用时生效。"""
    with self._owner._lock:
      self._owner._checkpoint()
      if self._stopped is not None:
        raise self._stopped

  def reserve(self, kind: Literal["model", "tool"], *, node_id: str) -> None:
    """为 kind/node_id 原子预占额度；失败不消耗次数，局部耗尽不阻断后续独立试验。"""
    if kind not in {"model", "tool"} or not isinstance(node_id, str):
      raise ValueError("调用类型或节点身份无效")
    owner = self._owner
    with owner._lock:
      self.checkpoint()
      if kind == "model" and owner._limits.get("max_total_tokens") is not None:
        if owner._tokens >= owner._limits["max_total_tokens"]:
          self._stop("budget_exceeded", "max_total_tokens", global_limit=True)
      key = (kind, node_id)
      limits = ((f"max_{kind}_calls", owner._calls[kind], True),
                (f"max_{kind}_calls_per_trial", self._calls[kind], False),
                (f"max_{kind}_calls_per_node", self._nodes.get(key, 0), False))
      for name, used, global_limit in limits:
        if self._global_only and not global_limit:
          continue
        maximum = owner._limits.get(name)
        if maximum is not None and used >= maximum:
          self._stop("budget_exceeded", name, global_limit=global_limit)
      owner._calls[kind] += 1
      self._calls[kind] += 1
      self._nodes[key] = self._nodes.get(key, 0) + 1

  def check_size(self, value: Any, *, kind: Literal["message", "context"]) -> None:
    """限制 value 大小；只拒绝，不自动截断载体、上下文或私有材料。"""
    if kind not in {"message", "context"}:
      raise ValueError("未知载荷种类")
    self.checkpoint()
    name = f"max_{kind}_bytes"
    maximum = self._owner._limits.get(name)
    if maximum is None:
      return
    chunks = (value,) if kind == "message" and isinstance(value, str) else json.JSONEncoder(
        ensure_ascii=False, allow_nan=False).iterencode(value)
    size = 0
    for chunk in chunks:
      size += len(chunk.encode("utf-8"))
      if size > maximum:
        with self._owner._lock:
          self._stop("payload_exceeded", name)

  def record_usage(self, usage: Mapping[str, Any] | None) -> None:
    """累计 usage；恰好达到上限时拒绝下一模型请求，超过上限时在下一检查点停止。"""
    owner = self._owner
    with owner._lock:
      count = usage.get("total_tokens") if isinstance(usage, Mapping) else None
      if type(count) is not int or count < 0:
        owner._unknown_usage += 1
        return
      owner._tokens += count
      maximum = owner._limits.get("max_total_tokens")
      if maximum is not None and owner._tokens > maximum and owner._stopped is None:
        owner._stopped = ExecutionStopped("budget_exceeded", resource="max_total_tokens")

  def _stop(self, code: str, resource: str, *, global_limit: bool = False) -> None:
    """以 code/resource 固定停止原因；global_limit 决定是否阻止后续试验。"""
    error = ExecutionStopped(code, resource=resource)
    if global_limit:
      self._owner._stopped = error
    else:
      self._stopped = error
    raise error
