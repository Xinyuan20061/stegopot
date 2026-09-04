"""工具来源标记及载体级隐写调用审计。"""

from dataclasses import asdict
from typing import Literal
from uuid import uuid4

from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.codec import DecodeRequest, DecodeResult, EncodeRequest, EncodeResult, StegoCodec
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.interface.trace import audit_span
from stegopot.domain.model.execution import ContractViolation, error_details


class AuditedCodec:
  """包装注入的隐写工具，不把工具恢复伪装成 LLM 推断。"""

  def __init__(
      self, codec: StegoCodec, *, audit: AuditSink, component_id: str,
      node_id: str | None = None, control: ExecutionGuard | None = None,
  ) -> None:
    """注入 codec、研究 audit、组件 component_id、所属 node_id 及 control；不拥有依赖资源。"""
    self._codec = codec
    self._audit = audit
    self._id = component_id
    self._node_id = node_id
    self._control = control

  def encode(self, request: EncodeRequest) -> EncodeResult:
    """审计实际 request 和编码返回值；私有比特只进入研究事件。"""
    with audit_span(self._audit, "codec.encode", actor=self._node_id):
      return self._call("encode", request)

  def decode(self, request: DecodeRequest) -> DecodeResult:
    """审计 request 的公开输入和工具解码结果，明确标记来源。"""
    with audit_span(self._audit, "codec.decode", actor=self._node_id):
      return self._call("decode", request)

  def close(self) -> None:
    """包装器不拥有被包装工具的生命周期。"""

  def _call(
      self, operation: Literal["encode", "decode"], request: EncodeRequest | DecodeRequest,
  ) -> EncodeResult | DecodeResult:
    """统一记录 operation 的 request、结果或失败，不修改工具输出。"""
    expected_request = EncodeRequest if operation == "encode" else DecodeRequest
    if not isinstance(request, expected_request):
      raise ContractViolation("隐写请求类型与操作不匹配")
    if self._control is not None:
      self._control.check_size(asdict(request), kind="context")
      self._control.reserve("tool", node_id=self._node_id or self._id)
    call_id = uuid4().hex
    self._audit.emit({"kind": "codec.request", "data": {
        "call_id": call_id,
        "component": self._id, "operation": operation, "request": asdict(request),
    }})
    try:
      result = getattr(self._codec, operation)(request)
      expected_result = EncodeResult if operation == "encode" else DecodeResult
      if not isinstance(result, expected_result):
        raise ContractViolation("隐写工具返回值不满足编解码契约")
      if operation == "encode" and result.consumed_bits > len(request.bits):
        raise ContractViolation("编码器声明消耗的比特数超过请求载荷")
    except Exception as exc:
      self._audit.emit({"kind": "codec.failed", "data": {
          "component": self._id, "operation": operation, "call_id": call_id,
          "error_type": type(exc).__name__, "error": str(exc), "failure": error_details(exc),
      }})
      raise
    self._audit.emit({"kind": "codec.response", "data": {
        "component": self._id, "operation": operation, "call_id": call_id,
        "origin": "tool", "result": asdict(result),
    }})
    if self._control is not None:
      if isinstance(result, EncodeResult):
        self._control.check_size(result.carrier.content, kind="message")
      else:
        self._control.check_size(result.bits, kind="context")
      self._control.checkpoint()
    return result
