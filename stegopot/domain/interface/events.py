"""运行时和实验生命周期事件协议。"""

from collections.abc import Callable
from typing import Protocol

from stegopot.domain.model.events import RuntimeEvent


class EventSink(Protocol):
  """只接收事件、不暴露订阅状态的最小接口。"""

  def emit(self, event: RuntimeEvent) -> None:
    """同步提交一个不含原始张量的事件。"""
    ...

class EventBus(EventSink, Protocol):
  """允许插件按精确事件名订阅的总线。"""

  def subscribe(self, kind: str, handler: Callable[[RuntimeEvent], None]) -> Callable[[], None]:
    """注册 handler 并返回幂等取消函数。"""
    ...
