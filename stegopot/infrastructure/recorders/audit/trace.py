"""上下文局部的调用链装饰器；不改变持久化封印或公开投影规则。"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any
from uuid import uuid4


class TracedAudit:
  """为标准 Mapping 事件补充关联字段；不依赖应用结果类型，也不拥有底层存储。"""

  def __init__(self, sink: Any, *, run_id: str, trial_id: str | None = None) -> None:
    """绑定 sink、整组 run_id 和可选 trial_id；每个实例使用独立上下文变量。"""
    self._sink = sink
    self._run_id = run_id
    self._trial_id = trial_id
    self._current: ContextVar[dict[str, Any] | None] = ContextVar("stegopot_trace", default=None)

  def emit(self, event: Mapping[str, Any]) -> None:
    """转交 event 并附加可信 trace；插件提供的 trace 不能覆盖宿主关联字段。"""
    frame = dict(self._current.get() or {})
    actor = event.get("actor")
    round_index = event.get("round_index")
    if actor is not None:
      frame["node_id"] = actor
    if round_index is not None:
      frame["round_index"] = round_index
    trace = {"schema_version": "stegopot.trace/1", "run_id": self._run_id,
             "trial_id": self._trial_id, **frame}
    self._sink.emit({**event, "actor": frame.get("node_id"),
                     "round_index": frame.get("round_index"), "trace": trace})

  @contextmanager
  def span(
      self, name: str, *, actor: str | None = None, round_index: int | None = None,
      message_id: str | None = None, parent_span_id: str | None = None,
  ) -> Iterator[str]:
    """建立一个可嵌套调用作用域，结束或异常都会记录，写盘失败不被吞掉。

    参数：
      name: 操作名称，例如 node.decision、llm.call、codec.decode。
      actor: 当前节点，None 继承父作用域。
      round_index: 当前轮次，None 继承父作用域。
      message_id: 关联公开消息，None 继承父作用域。
      parent_span_id: 可选显式因果父调用；默认使用当前父作用域。
    """
    previous = self._current.get() or {}
    span_id = uuid4().hex
    frame = {**previous, "span_id": span_id, "span_name": name,
             "parent_span_id": parent_span_id or previous.get("span_id")}
    for key, value in (("node_id", actor), ("round_index", round_index), ("message_id", message_id)):
      if value is not None:
        frame[key] = value
    token = self._current.set(frame)
    status = "failed"
    try:
      self.emit({"kind": "span.started", "data": {"name": name}})
      yield span_id
      status = "completed"
    finally:
      try:
        self.emit({"kind": "span.finished", "data": {"name": name, "status": status}})
      finally:
        self._current.reset(token)
