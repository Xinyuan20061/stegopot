"""工具来源标记及载体级隐写调用审计。"""

from dataclasses import asdict

from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.codec import DecodeRequest, DecodeResult, EncodeRequest, EncodeResult, StegoCodec


class AuditedCodec:
  """包装注入的隐写工具，不把工具恢复伪装成 LLM 推断。"""

  def __init__(self, codec: StegoCodec, *, audit: AuditSink, component_id: str) -> None:
    """设置 codec、研究 audit 和用于关联的 component_id；底层资源由宿主管理。"""
    self._codec = codec
    self._audit = audit
    self._id = component_id

  def encode(self, request: EncodeRequest) -> EncodeResult:
    """审计实际 request 和编码返回值；私有比特只进入研究事件。"""
    return self._call("encode", request)

  def decode(self, request: DecodeRequest) -> DecodeResult:
    """审计 request 的公开输入和工具解码结果，明确标记来源。"""
    return self._call("decode", request)

  def close(self) -> None:
    """包装器不拥有被包装工具的生命周期。"""

  def _call(self, operation, request):
    """统一记录 operation 的 request、结果或失败，不修改工具输出。"""
    self._audit.emit({"kind": "codec.request", "data": {
        "component": self._id, "operation": operation, "request": asdict(request),
    }})
    try:
      result = getattr(self._codec, operation)(request)
    except Exception as exc:
      self._audit.emit({"kind": "codec.failed", "data": {
          "component": self._id, "operation": operation, "error_type": type(exc).__name__,
          "error": str(exc),
      }})
      raise
    self._audit.emit({"kind": "codec.response", "data": {
        "component": self._id, "operation": operation, "origin": "tool", "result": asdict(result),
    }})
    return result
