"""执行取消与结构化失败数据，不依赖运行器、模型或存储实现。"""

import threading
from typing import Any


class CancellationToken:
  """可跨线程发出取消请求；由调用方持有，单次使用，不负责强制中断线程。"""

  def __init__(self) -> None:
    """创建未取消的令牌；不包含用户提示或其他研究数据。"""
    self._event = threading.Event()

  def cancel(self) -> None:
    """请求取消；重复调用无副作用，在宿主下一个检查点生效。"""
    self._event.set()

  @property
  def cancelled(self) -> bool:
    """返回调用方是否已请求取消。"""
    return self._event.is_set()


class ExecutionStopped(RuntimeError):
  """受控停止。code 为机器可读原因，resource 为预算项，不携带原始载荷。"""

  def __init__(self, code: str, *, resource: str | None = None) -> None:
    """保存 code/resource；错误文本不包含节点私有数据或基础设施凭证。"""
    self.code = code
    self.resource = resource
    super().__init__(f"执行已停止：{code}" + (f"（{resource}）" if resource else ""))


class ContractViolation(TypeError):
  """组件返回值不满足公开契约，不允许转换为模拟成功结果。"""


def error_details(error: Exception) -> dict[str, Any]:
  """将 error 转成可审计错误；保留类型和原因，持久化时仍须经过宿主脱敏。"""
  if isinstance(error, ExecutionStopped):
    return {"type": type(error).__name__, "message": str(error),
            "code": error.code, "resource": error.resource}
  return {"type": type(error).__name__, "message": str(error),
          "code": "protocol_error" if isinstance(error, ContractViolation) else "component_error"}
