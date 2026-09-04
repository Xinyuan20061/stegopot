"""命令行取消信号适配；嵌入调用不修改宿主应用的信号处理器。"""

from collections.abc import Iterator
from contextlib import contextmanager
import signal
import threading
from types import FrameType

from stegopot.domain.model.execution import CancellationToken


@contextmanager
def cancellation_signals(token: CancellationToken) -> Iterator[None]:
  """临时适配 Ctrl+C 到 token，退出时还原；非主线程不注册信号。

  参数：
    token: 本次运行的取消令牌。第一次中断请求协作停止，第二次强制抛出
      KeyboardInterrupt，可能留下未封印目录，但仍执行 Python 的资源释放。
  """
  if threading.current_thread() is not threading.main_thread():
    yield
    return
  previous = signal.getsignal(signal.SIGINT)

  def handle(signum: int, frame: FrameType | None) -> None:
    """处理 signum/frame；第一次请求取消，后续中断不伪造完成报告。"""
    if token.cancelled:
      raise KeyboardInterrupt
    token.cancel()

  signal.signal(signal.SIGINT, handle)
  try:
    yield
  finally:
    signal.signal(signal.SIGINT, previous)
