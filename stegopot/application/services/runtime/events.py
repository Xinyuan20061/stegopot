"""进程内同步事件总线。"""

from collections import defaultdict
from collections.abc import Callable
import threading

from stegopot.domain.model.events import RuntimeEvent


class InMemoryEventBus:
  """为可信插件提供确定性同步通知，不承担进程级隔离。"""

  def __init__(self) -> None:
    """初始化独立订阅表；不同实验不得共享实例。"""
    self._handlers: dict[str, list[Callable[[RuntimeEvent], None]]] = defaultdict(list)
    self._lock = threading.RLock()

  def subscribe(
      self, kind: str, handler: Callable[[RuntimeEvent], None],
  ) -> Callable[[], None]:
    """订阅精确 kind 或通配符 `*`，并返回幂等取消函数。"""
    if not isinstance(kind, str) or not kind.strip() or not callable(handler):
      raise ValueError("kind 必须非空且 handler 必须可调用")
    key = kind.strip()
    with self._lock:
      self._handlers[key].append(handler)
    removed = False

    def unsubscribe() -> None:
      """只移除本次注册的 handler。"""
      nonlocal removed
      with self._lock:
        if not removed:
          self._handlers[key].remove(handler)
          removed = True

    return unsubscribe

  def emit(self, event: RuntimeEvent) -> None:
    """按注册顺序同步执行精确订阅者和通配订阅者。"""
    if not isinstance(event, RuntimeEvent):
      raise TypeError("事件总线只接受 RuntimeEvent")
    with self._lock:
      handlers = tuple(self._handlers.get(event.kind, ())) + tuple(
          self._handlers.get("*", ()))
    for handler in handlers:
      handler(event)
