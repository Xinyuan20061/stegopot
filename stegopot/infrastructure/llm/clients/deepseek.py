"""DeepSeek 大语言模型客户端。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import os
import time
from typing import Any
import urllib.error
import urllib.request

from stegopot.domain.interface import LLMClient
from stegopot.domain.interface import LLMMessage
from stegopot.domain.interface import LLMResponse
from stegopot.infrastructure.settings import load_env_file


class DeepSeekAPIError(RuntimeError):
  """DeepSeek API 调用失败时抛出的异常。"""


class DeepSeekClient(LLMClient):
  """通过 DeepSeek Chat Completions API 调用模型的客户端。

  该类只负责 HTTP 请求、鉴权、请求体构造和响应解析。
  智能体如何构造提示词、如何解释模型输出，仍由 LLMPolicy、
  PromptBuilder 和 JsonActionParser 负责。
  """

  def __init__(
      self,
      *,
      api_key: str | None = None,
      api_key_env: str = "DEEPSEEK_API_KEY",
      base_url: str = "https://api.deepseek.com",
      default_model: str = "deepseek-v4-flash",
      timeout: float = 60.0,
      max_retries: int = 2,
      retry_backoff: float = 1.0,
      default_temperature: float | None = None,
      default_max_tokens: int | None = None,
      env_file: str | os.PathLike[str] | None = ".env",
      response_format: Mapping[str, Any] | None = None,
      thinking: Mapping[str, Any] | None = None,
      reasoning_effort: str | None = None,
      extra_body: Mapping[str, Any] | None = None,
  ) -> None:
    """初始化 DeepSeek 客户端。

    参数：
      api_key: DeepSeek API 密钥；为空时从 api_key_env 指定的环境变量读取。
      api_key_env: 保存 DeepSeek API 密钥的环境变量名称。
      base_url: DeepSeek OpenAI 兼容接口的基础地址。
      default_model: generate 未传入 model 时使用的默认模型。
      timeout: HTTP 请求超时时间，单位为秒。
      max_retries: 遇到超时、连接错误、限流或服务端错误时的最大重试次数。
      retry_backoff: 首次重试前等待秒数，后续重试按指数增加。
      default_temperature: generate 未传入 temperature 时使用的默认温度。
      default_max_tokens: generate 未传入 max_tokens 时使用的默认最大输出数。
      env_file: 初始化时要读取的环境变量文件；为空时不读取 .env 文件。
      response_format: 传给 API 的响应格式；为空时默认请求 JSON 对象。
      thinking: DeepSeek thinking 参数；为空时不发送该字段。
      reasoning_effort: DeepSeek 推理强度参数；为空时不发送该字段。
      extra_body: 追加到请求体的额外字段；会覆盖默认字段。
    """
    if env_file is not None:
      load_env_file(env_file, override=False)
    self._api_key = api_key or os.environ.get(api_key_env)
    self._api_key_env = api_key_env
    self._base_url = base_url.rstrip("/")
    self._default_model = default_model
    self._timeout = timeout
    if max_retries < 0:
      raise ValueError("max_retries 不能小于 0")
    if retry_backoff < 0:
      raise ValueError("retry_backoff 不能小于 0")
    self._max_retries = max_retries
    self._retry_backoff = retry_backoff
    self._default_temperature = default_temperature
    self._default_max_tokens = default_max_tokens
    self._response_format = dict(
        response_format
        if response_format is not None else {"type": "json_object"}
    )
    self._thinking = dict(thinking) if thinking is not None else None
    self._reasoning_effort = reasoning_effort
    self._extra_body = dict(extra_body or {})

  def generate(
      self,
      messages: Sequence[LLMMessage],
      *,
      model: str | None = None,
      temperature: float | None = None,
      max_tokens: int | None = None,
  ) -> LLMResponse:
    """调用 DeepSeek API 生成一次模型响应。

    参数：
      messages: 按顺序发送给模型的消息列表。
      model: 本次调用使用的模型名称；为空时使用默认模型。
      temperature: 本次调用使用的采样温度；为空时使用默认温度。
      max_tokens: 本次调用使用的最大输出 token 数；为空时使用默认值。

    返回：
      标准模型响应对象，content 为 choices[0].message.content。
    """
    if not self._api_key:
      raise ValueError(
          f"缺少 DeepSeek API 密钥，请设置环境变量 {self._api_key_env}，"
          "或在构造 DeepSeekClient 时传入 api_key。"
      )

    body = self._build_request_body(
        messages=messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url=f"{self._base_url}/chat/completions",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        },
    )
    response_body = self._send_request(request)

    return self._parse_response(response_body)

  def _send_request(self, request: urllib.request.Request) -> str:
    """发送 HTTP 请求，并对可恢复的网络错误进行有限重试。

    参数：
      request: 已包含鉴权头和 JSON 请求体的 urllib 请求对象。

    返回：
      DeepSeek API 返回的 UTF-8 响应正文。
    """
    for attempt in range(self._max_retries + 1):
      try:
        with urllib.request.urlopen(
            request,
            timeout=self._timeout,
        ) as response:
          return response.read().decode("utf-8")
      except urllib.error.HTTPError as exc:
        if self._should_retry_http(exc.code, attempt):
          self._wait_before_retry(attempt)
          continue
        raise DeepSeekAPIError(self._format_http_error(exc)) from exc
      except (urllib.error.URLError, TimeoutError) as exc:
        if attempt < self._max_retries:
          self._wait_before_retry(attempt)
          continue
        reason = getattr(exc, "reason", exc)
        raise DeepSeekAPIError(
            f"DeepSeek API 请求失败，已重试 {self._max_retries} 次：{reason}"
        ) from exc
    raise AssertionError("DeepSeek 重试循环意外结束")

  def _should_retry_http(self, status_code: int, attempt: int) -> bool:
    """判断 HTTP 错误是否满足重试条件。

    参数：
      status_code: DeepSeek API 返回的 HTTP 状态码。
      attempt: 当前已执行的重试轮次，从 0 开始。

    返回：
      当前仍有重试次数，且错误为限流或服务端错误时返回 True。
    """
    retryable_codes = {429, 500, 502, 503, 504}
    return attempt < self._max_retries and status_code in retryable_codes

  def _wait_before_retry(self, attempt: int) -> None:
    """按指数退避等待下一次请求。

    参数：
      attempt: 当前已执行的重试轮次，从 0 开始。
    """
    delay = self._retry_backoff * (2 ** attempt)
    if delay > 0:
      time.sleep(delay)

  def _build_request_body(
      self,
      *,
      messages: Sequence[LLMMessage],
      model: str | None,
      temperature: float | None,
      max_tokens: int | None,
  ) -> dict[str, Any]:
    """构建 DeepSeek Chat Completions 请求体。

    参数：
      messages: 按顺序发送给模型的消息列表。
      model: 本次调用的模型名称。
      temperature: 本次调用的采样温度。
      max_tokens: 本次调用的最大输出 token 数。

    返回：
      可以序列化为 JSON 的请求体字典。
    """
    body: dict[str, Any] = {
        "model": model or self._default_model,
        "messages": [
            {"role": message.role, "content": message.content}
            for message in messages
        ],
        "stream": False,
    }
    actual_temperature = (
        temperature if temperature is not None else self._default_temperature
    )
    actual_max_tokens = (
        max_tokens if max_tokens is not None else self._default_max_tokens
    )
    if actual_temperature is not None:
      body["temperature"] = actual_temperature
    if actual_max_tokens is not None:
      body["max_tokens"] = actual_max_tokens
    if self._response_format:
      body["response_format"] = dict(self._response_format)
    if self._thinking is not None:
      body["thinking"] = dict(self._thinking)
    if self._reasoning_effort is not None:
      body["reasoning_effort"] = self._reasoning_effort
    body.update(self._extra_body)
    return body

  def _parse_response(self, response_body: str) -> LLMResponse:
    """解析 DeepSeek API 响应体。

    参数：
      response_body: DeepSeek API 返回的 JSON 字符串。

    返回：
      标准模型响应对象。
    """
    try:
      data = json.loads(response_body)
    except json.JSONDecodeError as exc:
      raise DeepSeekAPIError("DeepSeek API 返回了无法解析的 JSON。") from exc

    choices = data.get("choices") or []
    if not choices:
      raise DeepSeekAPIError("DeepSeek API 响应中没有 choices。")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
      raise DeepSeekAPIError("DeepSeek API 响应中没有有效的 message.content。")

    metadata = {
        "provider": "deepseek",
        "id": data.get("id"),
        "model": data.get("model"),
        "usage": data.get("usage"),
        "finish_reason": choices[0].get("finish_reason"),
        "base_url": self._base_url,
    }
    return LLMResponse(content=content, metadata=metadata, raw=data)

  def _format_http_error(self, exc: urllib.error.HTTPError) -> str:
    """格式化 HTTP 错误信息。

    参数：
      exc: urllib 抛出的 HTTPError。

    返回：
      适合展示给调用方的中文错误信息。
    """
    try:
      body = exc.read().decode("utf-8")
    except UnicodeDecodeError:
      body = "<无法解码的响应体>"
    return f"DeepSeek API HTTP {exc.code}：{body}"
