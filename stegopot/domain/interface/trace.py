"""可选调用链契约；普通 AuditSink 无须实现调用链即可继续用于嵌入测试。"""

from contextlib import AbstractContextManager, nullcontext
from typing import Protocol

from stegopot.domain.interface.audit import AuditSink


class TraceSink(AuditSink, Protocol):
  """宿主审计器的作用域扩展；关联标识只用于研究记录，不进入节点观察。"""

  def span(
      self, name: str, *, actor: str | None = None, round_index: int | None = None,
      message_id: str | None = None, parent_span_id: str | None = None,
  ) -> AbstractContextManager[str]:
    """建立 name 调用作用域；actor/round_index/message_id 关联主体，parent_span_id 指定因果父调用。"""
    ...


def audit_span(
    sink: AuditSink | None, name: str, *, actor: str | None = None,
    round_index: int | None = None, message_id: str | None = None,
    parent_span_id: str | None = None,
) -> AbstractContextManager[str | None]:
  """为支持调用链的 sink 建立作用域；其他接收器返回空作用域以保持兼容。

  参数：
    sink: 宿主审计接口，不拥有其关闭责任。
    name: 当前操作的稳定名称。
    actor: 节点身份；为空时继承已有作用域。
    round_index: 当前轮次；为空时继承。
    message_id: 实际公开消息的身份，不是秘密载荷。
    parent_span_id: 显式父调用；为空时使用当前作用域。
  """
  method = getattr(sink, "span", None)
  if callable(method):
    return method(name, actor=actor, round_index=round_index,
                  message_id=message_id, parent_span_id=parent_span_id)
  return nullcontext(None)
