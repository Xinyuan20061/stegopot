"""大语言模型客户端抽象。"""

from __future__ import annotations

import abc
from collections.abc import Mapping, Sequence
import dataclasses
from types import MappingProxyType
from typing import Any


@dataclasses.dataclass(frozen=True)
class LLMMessage:
  """发送给模型的一条消息。

  属性：
    role: 消息角色，例如 "system"、"user" 或 "assistant"。
    content: 消息正文。
  """

  role: str
  content: str


@dataclasses.dataclass(frozen=True)
class LLMResponse:
  """模型返回的一次响应。

  属性：
    content: 模型生成的主要文本内容。
    metadata: 与响应相关的元数据，例如 token 用量或模型名称。
    raw: 底层客户端返回的原始对象；没有时为空。
  """

  content: str
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)
  raw: Any | None = None

  def __post_init__(self) -> None:
    object.__setattr__(self, "metadata",
                       MappingProxyType(dict(self.metadata)))


class LLMClient(metaclass=abc.ABCMeta):
  """大语言模型客户端基类。

  具体模型供应商、鉴权方式和网络调用都应该封装在该层，
  不应泄漏到智能体策略里。
  """

  @abc.abstractmethod
  def generate(
      self,
      messages: Sequence[LLMMessage],
      *,
      model: str | None = None,
      temperature: float | None = None,
      max_tokens: int | None = None,
  ) -> LLMResponse:
    """根据消息列表生成一次模型响应。

    参数：
      messages: 按顺序发送给模型的消息列表。
      model: 模型名称；为空时由具体客户端使用默认模型。
      temperature: 采样温度；为空时由具体客户端使用默认值。
      max_tokens: 最大输出 token 数；为空时由具体客户端使用默认值。

    返回：
      模型响应对象。
    """
    raise NotImplementedError

  def close(self) -> None:
    """释放客户端持有的资源。"""
