"""通过稳定客户端接口记录模型调用，不保存 HTTP 鉴权头或隐藏推理字段。"""

from collections.abc import Sequence
import threading
import time
from uuid import uuid4

from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.llm import LLMClient, LLMMessage, LLMResponse


class CallBudget:
  """多个模型包装器共享的调用上限，避免实验无界重试。"""

  def __init__(self, limit: int) -> None:
    """设置 limit 次应用级调用上限；底层 HTTP 重试由供应商配置控制。"""
    if type(limit) is not int or limit < 1:
      raise ValueError("调用上限必须为正整数")
    self.limit = limit
    self.used = 0
    self.usage: dict[str, int] = {}
    self.models: set[str] = set()
    self._lock = threading.Lock()

  def reserve(self) -> None:
    """预占一次调用，达到上限时抛出异常而不发送请求。"""
    with self._lock:
      if self.used >= self.limit:
        raise RuntimeError("实验模型调用预算已耗尽")
      self.used += 1

  def record_response(self, response: LLMResponse) -> None:
    """累计 response 声明的用量和实际模型名，不把缺失用量当作真实零费用。"""
    with self._lock:
      model = response.metadata.get("model")
      if isinstance(model, str):
        self.models.add(model)
      usage = response.metadata.get("usage") or {}
      for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage.get(key)
        if isinstance(value, int):
          self.usage[key] = self.usage.get(key, 0) + value


class AuditedLLMClient(LLMClient):
  """供应商无关的模型调用审计装饰器。"""

  def __init__(
      self, client: LLMClient, *, audit_sink: AuditSink,
      node_id: str, budget: CallBudget, max_output_tokens: int | None = None,
  ) -> None:
    """注入客户端与记录器。

    参数：
      client: 被装饰的供应商客户端，所有权仍由外部调用者持有。
      audit_sink: 研究审计接收器，写入失败时禁止继续模型调用。
      node_id: 当前节点身份，用于关联请求和运行器观察。
      budget: 当前实验共享的有限调用预算。
      max_output_tokens: 宿主输出上限；为空时保持旧调用行为。
    """
    self._client = client
    self._audit_sink = audit_sink
    self._node_id = node_id
    self._budget = budget
    self._max_output_tokens = max_output_tokens

  def generate(
      self, messages: Sequence[LLMMessage], *, model: str | None = None,
      temperature: float | None = None, max_tokens: int | None = None,
  ) -> LLMResponse:
    """记录并代理一次调用。

    参数：
      messages: 实际发送的完整提示词序列，仅进入研究记录。
      model: 请求模型名称；实际响应型号另行记录。
      temperature: 请求采样温度。
      max_tokens: 输出 token 上限。

    返回：
      未经篡改的模型响应。异常不会替换成模拟成功结果。
    """
    if self._max_output_tokens is not None:
      max_tokens = min(max_tokens or self._max_output_tokens, self._max_output_tokens)
    self._budget.reserve()
    call_id = uuid4().hex
    self._emit("llm.request", {
        "call_id": call_id,
        "messages": [{"role": item.role, "content": item.content} for item in messages],
        "model": model, "temperature": temperature, "max_tokens": max_tokens,
    })
    started = time.perf_counter()
    try:
      response = self._client.generate(messages, model=model,
                                       temperature=temperature, max_tokens=max_tokens)
    except Exception as exc:
      self._emit("llm.failed", {"call_id": call_id,
                 "elapsed_seconds": time.perf_counter() - started,
                 "error_type": type(exc).__name__, "error": str(exc)})
      raise
    self._budget.record_response(response)
    self._emit("llm.response", {
        "call_id": call_id, "content": response.content,
        "elapsed_seconds": time.perf_counter() - started,
        "metadata": {key: response.metadata.get(key) for key in (
            "provider", "id", "model", "usage", "finish_reason")},
    })
    return response

  def _emit(self, kind: str, data: dict) -> None:
    """将 kind 和 data 关联到当前节点，交给注入记录器。"""
    self._audit_sink.emit({"kind": kind, "actor": self._node_id, "data": data})
