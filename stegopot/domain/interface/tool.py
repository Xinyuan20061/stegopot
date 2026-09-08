"""不绑定代码执行、搜索或文件系统实现的通用工具协议。"""

from typing import Protocol, runtime_checkable

from stegopot.domain.model.tool import ToolRequest, ToolResult


@runtime_checkable
class ToolExecutor(Protocol):
  """由宿主按节点授权、限额并审计的通用工具组件。"""

  def execute(self, request: ToolRequest) -> ToolResult:
    """执行一次工具请求。

    参数：
      request: 只含操作名称和 JSON 参数的不可变请求。

    返回：
      可序列化且只返回调用节点的工具结果。
    """
    ...

  def close(self) -> None:
    """释放当前工具实例拥有的资源。"""
    ...
