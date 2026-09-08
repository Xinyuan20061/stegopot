"""对所有通用工具调用执行统一预算、类型检查和研究审计。"""

from __future__ import annotations

from uuid import uuid4

from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.interface.tool import ToolExecutor
from stegopot.domain.interface.trace import audit_span
from stegopot.domain.model.execution import ContractViolation, error_details
from stegopot.domain.model.tool import ToolRequest, ToolResult


class AuditedTool:
  """包装一个已授权工具，使每次外部作用都经过相同宿主边界。"""

  def __init__(
      self,
      tool: ToolExecutor,
      *,
      audit: AuditSink,
      component_id: str,
      node_id: str | None,
      control: ExecutionGuard | None = None,
  ) -> None:
    """保存工具依赖和宿主控制对象。

    参数：
      tool: 实际工具实现；包装器不拥有其关闭责任。
      audit: 研究审计接收器，写入失败必须向上传播。
      component_id: 当前工具组件的注册 ID。
      node_id: 获准调用工具的节点 ID；中央调用时可为空。
      control: 可选工具调用预算、大小和取消控制器。
    """
    self._tool = tool
    self._audit = audit
    self._component_id = component_id
    self._node_id = node_id
    self._control = control

  def execute(self, request: ToolRequest) -> ToolResult:
    """执行并记录一次受控工具请求。

    参数：
      request: 不包含基础设施凭证的标准工具请求。

    返回：
      经过类型和大小检查的工具结果；失败不会伪造成空结果。
    """
    if not isinstance(request, ToolRequest):
      raise ContractViolation("工具请求必须是 ToolRequest")
    if self._control is not None:
      self._control.check_size(request.to_dict(), kind="context")
      self._control.reserve(
          "tool",
          node_id=self._node_id or self._component_id,
      )
    call_id = uuid4().hex
    self._audit.emit({
        "kind": "tool.request",
        "data": {
            "call_id": call_id,
            "component": self._component_id,
            "operation": request.operation,
            "request": request.to_dict(),
        },
    })
    try:
      with audit_span(self._audit, "tool.plugin_execute", actor=self._node_id):
        result = self._tool.execute(request)
      if not isinstance(result, ToolResult):
        raise ContractViolation("工具实现必须返回 ToolResult")
      if self._control is not None:
        self._control.check_size(result.to_dict(), kind="context")
        self._control.checkpoint()
    except Exception as exc:
      self._audit.emit({
          "kind": "tool.failed",
          "data": {
              "call_id": call_id,
              "component": self._component_id,
              "operation": request.operation,
              "failure": error_details(exc),
          },
      })
      raise
    self._audit.emit({
        "kind": "tool.response",
        "data": {
            "call_id": call_id,
            "component": self._component_id,
            "operation": request.operation,
            "result": result.to_dict(),
        },
    })
    return result

  def close(self) -> None:
    """包装器不关闭被包装工具；生命周期由 ComponentSession 统一管理。"""
