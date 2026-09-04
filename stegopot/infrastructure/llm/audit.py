"""通过稳定客户端接口记录模型调用，不保存 HTTP 鉴权头或隐藏推理字段。"""

from collections.abc import Mapping, Sequence
import json
import threading
import time
from uuid import uuid4

from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.llm import LLMClient, LLMMessage, LLMResponse
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.interface.trace import audit_span
from stegopot.domain.model.execution import ContractViolation, error_details


class CallBudget:
  """多个模型包装器共享的调用上限，避免实验无界重试。"""

  def __init__(self, limit: int) -> None:
    """设置 limit 次应用级调用上限；供应商适配不得自行重试或绕过宿主计数。"""
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
      control: ExecutionGuard | None = None,
  ) -> None:
    """注入客户端与记录器。

    参数：
      client: 被装饰的供应商客户端，所有权仍由外部调用者持有。
      audit_sink: 研究审计接收器，写入失败时禁止继续模型调用。
      node_id: 当前节点身份，用于关联请求和运行器观察。
      budget: 当前实验共享的有限调用预算。
      max_output_tokens: 宿主输出上限；为空时保持旧调用行为。
      control: 可选试验级预算与取消接口；不拥有其生命周期。
    """
    self._client = client
    self._audit_sink = audit_sink
    self._node_id = node_id
    self._budget = budget
    self._max_output_tokens = max_output_tokens
    self._control = control

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
    with audit_span(self._audit_sink, "llm.call", actor=self._node_id):
      return self._generate(messages, model=model, temperature=temperature, max_tokens=max_tokens)

  def _generate(
      self, messages: Sequence[LLMMessage], *, model: str | None,
      temperature: float | None, max_tokens: int | None,
  ) -> LLMResponse:
    """执行 messages/model/temperature/max_tokens 请求；先占额，再审计，最后调用。"""
    if self._control is not None:
      self._control.check_size(
          [{"role": item.role, "content": item.content} for item in messages], kind="context")
      self._control.reserve("model", node_id=self._node_id)
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
      self._validate_response(response)
    except Exception as exc:
      self._emit("llm.failed", {"call_id": call_id,
                 "elapsed_seconds": time.perf_counter() - started,
                 "error_type": type(exc).__name__, "error": str(exc),
                 "failure": error_details(exc)})
      raise
    self._budget.record_response(response)
    self._emit("llm.response", {
        "call_id": call_id, "content": response.content,
        "elapsed_seconds": time.perf_counter() - started,
        "metadata": {key: response.metadata.get(key) for key in (
            "provider", "id", "model", "usage", "finish_reason")},
    })
    if self._control is not None:
      self._control.record_usage(response.metadata.get("usage"))
      self._control.checkpoint()
    return response

  @staticmethod
  def _validate_response(response: LLMResponse) -> None:
    """验证 response 类型及允许公开给审计器的元数据；不读取原始 HTTP 对象。"""
    if not isinstance(response, LLMResponse) or not isinstance(response.content, str):
      raise ContractViolation("模型必须返回正文为字符串的 LLMResponse")
    usage = response.metadata.get("usage")
    if usage is not None:
      if not isinstance(usage, Mapping) or any(
          type(value) is not int or value < 0 for key, value in usage.items()
          if key in {"prompt_tokens", "completion_tokens", "total_tokens"}):
        raise ContractViolation("模型用量必须是非负整数映射")
    try:
      json.dumps({key: response.metadata.get(key) for key in (
          "provider", "id", "model", "usage", "finish_reason")}, allow_nan=False)
    except (TypeError, ValueError) as exc:
      raise ContractViolation("模型审计元数据必须可标准 JSON 序列化") from exc

  def _emit(self, kind: str, data: dict) -> None:
    """将 kind 和 data 关联到当前节点，交给注入记录器。"""
    self._audit_sink.emit({"kind": kind, "actor": self._node_id, "data": data})
