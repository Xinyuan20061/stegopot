"""通用 Chat Completions 传输适配；提示、策略和审计由上层注入。"""

from __future__ import annotations

from collections.abc import Sequence
import json
import math
from typing import Any
import urllib.error
import urllib.parse
import urllib.request

from stegopot.domain.interface.llm import LLMClient, LLMMessage, LLMResponse


class ModelRequestError(RuntimeError):
  """模型传输或响应协议失败；错误信息不回显鉴权头与服务端响应正文。"""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
  """禁止带凭证的请求被重定向到其他地址。"""

  def redirect_request(self, req, fp, code, msg, headers, newurl):
    """拒绝重定向；参数均为 urllib 提供的原请求、响应与目标信息。"""
    return None


class ChatCompletionsClient(LLMClient):
  """支持 DeepSeek 及兼容协议的服务；一次 generate 最多一次 HTTP 请求。

  客户端不读取文件或环境变量，不自动重试，不自动下载模型。
  每次响应连接立即关闭；宿主负责调用 close 结束客户端生命周期。
  """

  def __init__(
      self, *, base_url: str, model: str, api_key: str | None = None,
      timeout: float = 60.0, response_format: str = "json_object",
      thinking: str | None = None, reasoning_effort: str | None = None,
  ) -> None:
    """配置连接参数，构造时不联网。

    参数：
      base_url: API 根地址，可带 /v1；自动追加 /chat/completions。
        远程地址必须 HTTPS，HTTP 只允许 localhost、127.0.0.1 或 ::1。
      model: 默认模型名，由用户根据服务提供方支持的型号指定。
      api_key: 宿主注入的密钥；本地无鉴权服务可为空，不自行读取环境变量。
      timeout: HTTP 连接与读操作超时秒数；必须为有限正数，不代表整次实验硬截止。
      response_format: json_object 请求 JSON；text 不发送 response_format 字段。
      thinking: 可选 enabled/disabled，仅在兼容服务支持此参数时填写。
      reasoning_effort: 可选推理强度，由服务端校验，不通过额外字段覆盖消息或预算。
    """
    endpoint = urllib.parse.urlsplit(base_url)
    if (endpoint.scheme not in {"https", "http"} or not endpoint.hostname
        or endpoint.username is not None or endpoint.password is not None
        or endpoint.query or endpoint.fragment):
      raise ValueError("base_url 必须是无凭证、查询参数和片段的 HTTP(S) 地址")
    if endpoint.scheme == "http" and endpoint.hostname not in {"localhost", "127.0.0.1", "::1"}:
      raise ValueError("远程模型接口必须使用 HTTPS")
    if not isinstance(model, str) or not model.strip():
      raise ValueError("model 不能为空")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
      raise ValueError("timeout 必须为有限正数")
    if response_format not in {"json_object", "text"}:
      raise ValueError("response_format 必须为 json_object 或 text")
    if thinking not in {None, "enabled", "disabled"}:
      raise ValueError("thinking 必须为 enabled 或 disabled")
    if api_key is not None and (not api_key.strip() or "\r" in api_key or "\n" in api_key):
      raise ValueError("API 密钥格式无效")
    self._url = base_url.rstrip("/") + "/chat/completions"
    self._model = model
    self._key = api_key
    self._timeout = timeout
    self._format = response_format
    self._thinking = thinking
    self._effort = reasoning_effort
    self._opener = urllib.request.build_opener(_NoRedirect())
    self._closed = False

  def generate(
      self, messages: Sequence[LLMMessage], *, model: str | None = None,
      temperature: float | None = None, max_tokens: int | None = None,
  ) -> LLMResponse:
    """发送一次非流式请求并返回实际模型文本，不补写或替换答案。

    参数：
      messages: 完整有序消息，不自动添加或移除系统提示。
      model: 单次型号覆盖值；None 使用构造参数。
      temperature: 可选采样温度，有限数值且介于 0 和 2。
      max_tokens: 本次输出上限；None 使用 1024，必须为正整数。

    返回：
      LLMResponse，metadata 包含实际模型、用量和结束原因。
      HTTP、超时、格式和响应大小错误抛出 ModelRequestError，不重试。
    """
    if self._closed:
      raise RuntimeError("模型客户端已经关闭")
    if not messages or any(not isinstance(item, LLMMessage) for item in messages):
      raise ValueError("messages 必须包含标准 LLMMessage")
    actual_model = self._model if model is None else model
    if not isinstance(actual_model, str) or not actual_model.strip():
      raise ValueError("model 不能为空")
    limit = 1024 if max_tokens is None else max_tokens
    if type(limit) is not int or limit < 1:
      raise ValueError("max_tokens 必须为正整数")
    body: dict[str, Any] = {
        "model": actual_model,
        "messages": [{"role": item.role, "content": item.content} for item in messages],
        "stream": False, "max_tokens": limit,
    }
    if temperature is not None:
      if isinstance(temperature, bool) or not math.isfinite(temperature) or not 0 <= temperature <= 2:
        raise ValueError("temperature 必须在 0 到 2 之间")
      body["temperature"] = temperature
    if self._format == "json_object":
      body["response_format"] = {"type": "json_object"}
    if self._thinking is not None:
      body["thinking"] = {"type": self._thinking}
    if self._effort is not None:
      body["reasoning_effort"] = self._effort
    headers = {"Content-Type": "application/json"}
    if self._key:
      headers["Authorization"] = f"Bearer {self._key}"
    request = urllib.request.Request(self._url, method="POST", headers=headers,
                                     data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    try:
      with self._opener.open(request, timeout=self._timeout) as response:
        # 给异常服务端响应设上限；超过上限保留失败，不截断后冒充完整模型回复。
        raw = response.read(8 * 1024 * 1024 + 1)
        if len(raw) > 8 * 1024 * 1024:
          raise ModelRequestError("模型响应超过 8 MiB 上限")
    except urllib.error.HTTPError as exc:
      status = exc.code
      exc.close()
      raise ModelRequestError(f"模型接口返回 HTTP {status}，未自动重试") from None
    except (urllib.error.URLError, TimeoutError, OSError):
      raise ModelRequestError("模型接口连接失败或超时，未自动重试") from None
    return self._parse_response(raw)

  def close(self) -> None:
    """幂等关闭客户端并清除本实例的密钥引用；不关闭宿主或其他节点资源。"""
    self._closed = True
    self._key = None

  @staticmethod
  def _parse_response(raw: bytes) -> LLMResponse:
    """解析 raw 响应字节；拒绝无文本和非法用量，不回显原始错误正文。"""
    try:
      data = json.loads(raw)
      if not isinstance(data, dict):
        raise ValueError
      choice = data["choices"][0]
      content = choice["message"]["content"]
      if not isinstance(content, str):
        raise ValueError
      usage = data.get("usage")
      if usage is not None:
        if not isinstance(usage, dict):
          raise ValueError
        usage = {key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens") if key in usage}
        if any(type(value) is not int or value < 0 for value in usage.values()):
          raise ValueError
      metadata = {"provider": "chat_completions", "usage": usage}
      for name, value in (("id", data.get("id")), ("model", data.get("model")),
                          ("finish_reason", choice.get("finish_reason"))):
        if value is not None and not isinstance(value, str):
          raise ValueError
        metadata[name] = value
    except (ValueError, TypeError, KeyError, IndexError, UnicodeDecodeError):
      raise ModelRequestError("模型响应不符合 Chat Completions 文本协议") from None
    return LLMResponse(content=content, metadata=metadata, raw=data)
