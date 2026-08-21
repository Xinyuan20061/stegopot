"""测试和本地联调用的假模型客户端。"""

from __future__ import annotations

from typing import Callable, Sequence, Union

from meltingpot.utils.llm.client import LLMClient
from meltingpot.utils.llm.client import LLMMessage
from meltingpot.utils.llm.client import LLMResponse

MockResponseValue = Union[str, LLMResponse]
MockResponder = Callable[[Sequence[LLMMessage]], MockResponseValue]


class MockLLMClient(LLMClient):
  """可预测的假模型客户端。

  该客户端不访问网络，适合先把智能体、环境和评估流程跑通。
  可以传入固定响应序列，也可以传入自定义 responder 函数。
  """

  def __init__(
      self,
      responses: Sequence[MockResponseValue] = (),
      *,
      responder: MockResponder | None = None,
  ) -> None:
    """初始化假模型客户端。

    参数：
      responses: 预设响应序列；每次调用按顺序返回，耗尽后重复最后一条。
      responder: 自定义响应函数；传入后优先使用它生成响应。
    """
    self._responses = tuple(responses)
    self._responder = responder
    self._index = 0

  def generate(
      self,
      messages: Sequence[LLMMessage],
      *,
      model: str | None = None,
      temperature: float | None = None,
      max_tokens: int | None = None,
  ) -> LLMResponse:
    """返回下一条固定响应或 responder 生成的响应。

    参数：
      messages: 本次模型调用收到的消息列表。
      model: 模型名称；假模型会忽略该参数。
      temperature: 采样温度；假模型会忽略该参数。
      max_tokens: 最大输出 token 数；假模型会忽略该参数。

    返回：
      假模型响应对象。
    """
    del model, temperature, max_tokens
    if self._responder is not None:
      return self._to_response(self._responder(messages))
    if not self._responses:
      return LLMResponse(
          content='{"kind": "wait", "content": null, "target": null}',
          metadata={"source": "mock"},
      )
    response = self._responses[min(self._index, len(self._responses) - 1)]
    self._index += 1
    return self._to_response(response)

  def _to_response(self, value: MockResponseValue) -> LLMResponse:
    """把字符串或响应对象统一成 LLMResponse。

    参数：
      value: 字符串响应或已经构造好的响应对象。

    返回：
      标准响应对象。
    """
    if isinstance(value, LLMResponse):
      return value
    return LLMResponse(content=value, metadata={"source": "mock"})
