"""大语言模型智能体策略。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses
from types import MappingProxyType
from typing import Any

from stegopot.domain.model import AgentAction
from stegopot.domain.interface import LLMClient
from stegopot.domain.interface import LLMMessage
from stegopot.domain.interface import Policy
from stegopot.infrastructure.llm.action_parser import JsonActionParser
from stegopot.infrastructure.llm.prompt import PromptBuilder


@dataclasses.dataclass(frozen=True)
class LLMState:
  """LLM 节点在一次实验中的可复现状态。

  属性：
    messages: 当前节点保留的模型消息历史。
    memory: 当前节点的结构化内部记忆。
    step_count: 当前节点已经执行过的步数。
    last_action: 当前节点上一次输出的动作。
  """

  messages: Sequence[LLMMessage] = ()
  memory: Mapping[str, Any] = dataclasses.field(default_factory=dict)
  step_count: int = 0
  last_action: AgentAction | None = None

  def __post_init__(self) -> None:
    object.__setattr__(self, "messages", tuple(self.messages))
    object.__setattr__(self, "memory", MappingProxyType(dict(self.memory)))


class LLMPolicy(Policy[LLMState]):
  """可被运行核心调度的 LLM 节点策略。

  该类只负责一次智能体决策流程：构造消息、调用模型、
  解析动作、更新状态。具体模型供应商由 LLMClient 负责。
  """

  def __init__(
      self,
      *,
      node_id: str,
      role: str,
      client: LLMClient,
      prompt_builder: PromptBuilder | None = None,
      action_parser: JsonActionParser | None = None,
      model: str | None = None,
      temperature: float | None = None,
      max_tokens: int | None = None,
      keep_history: bool = True,
      max_history_messages: int = 20,
      metadata: Mapping[str, Any] | None = None,
  ) -> None:
    """初始化 LLM 节点。

    参数：
      node_id: 智能体节点 ID，用于日志、动作元数据和实验区分。
      role: 节点在实验中的角色，例如 sender、receiver 或 auditor。
      client: 负责实际生成模型响应的 LLM 客户端。
      prompt_builder: 负责把观察和状态转换成模型消息的构造器。
      action_parser: 负责把模型文本解析成结构化动作的解析器。
      model: 模型名称；为空时由客户端使用默认模型。
      temperature: 采样温度；为空时由客户端使用默认值。
      max_tokens: 最大输出 token 数；为空时由客户端使用默认值。
      keep_history: 是否在状态中保留模型消息历史。
      max_history_messages: 最多保留多少条非 system 历史消息。
      metadata: 节点级元数据，供实验记录和后续扩展使用。
    """
    self.node_id = node_id
    self.role = role
    self._client = client
    self._prompt_builder = prompt_builder or PromptBuilder()
    self._action_parser = action_parser or JsonActionParser()
    self._model = model
    self._temperature = temperature
    self._max_tokens = max_tokens
    self._keep_history = keep_history
    self._max_history_messages = max_history_messages
    self.metadata = MappingProxyType(dict(metadata or {}))

  def initial_state(self) -> LLMState:
    """返回 LLM 节点初始状态。

    返回：
      空消息历史、空记忆、步数为 0 的初始状态。
    """
    return LLMState()

  def step(
      self,
      observation: Any,
      prev_state: LLMState,
  ) -> tuple[AgentAction, LLMState]:
    """根据当前观察生成结构化动作。

    参数：
      observation: 当前环境提供给该节点的观察。
      prev_state: 该节点上一步返回的内部状态。

    返回：
      二元组，包含结构化动作和下一步内部状态。
    """
    current_messages = self._prompt_builder.build(
        node_id=self.node_id,
        role=self.role,
        observation=observation,
        memory=prev_state.memory,
        step_count=prev_state.step_count,
    )
    messages = self._compose_messages(prev_state.messages, current_messages)
    response = self._client.generate(
        messages,
        model=self._model,
        temperature=self._temperature,
        max_tokens=self._max_tokens,
    )
    action = self._action_parser.parse(response.content)
    action = dataclasses.replace(
        action,
        metadata={
            **action.metadata,
            "node_id": self.node_id,
            "role": self.role,
            "llm_metadata": dict(response.metadata),
        },
    )
    next_messages = self._next_history(messages, response.content)
    next_state = LLMState(
        messages=next_messages,
        memory=prev_state.memory,
        step_count=prev_state.step_count + 1,
        last_action=action,
    )
    return action, next_state

  def close(self) -> None:
    """释放 LLM 客户端资源。"""
    self._client.close()

  def _compose_messages(
      self,
      history: Sequence[LLMMessage],
      current_messages: Sequence[LLMMessage],
  ) -> tuple[LLMMessage, ...]:
    """按配置组合历史消息和本轮消息。

    参数：
      history: 上一状态中保存的历史消息。
      current_messages: 本轮根据观察构造出的消息。

    返回：
      实际发送给模型的消息序列。
    """
    if not self._keep_history or not history:
      return tuple(current_messages)
    system_messages = tuple(
        message for message in current_messages if message.role == "system"
    )
    non_system_history = tuple(
        message for message in history if message.role != "system"
    )
    non_system_current = tuple(
        message for message in current_messages if message.role != "system"
    )
    return system_messages + non_system_history + non_system_current

  def _next_history(
      self,
      messages: Sequence[LLMMessage],
      response_content: str,
  ) -> tuple[LLMMessage, ...]:
    """生成下一状态要保存的消息历史。

    参数：
      messages: 本轮发送给模型的消息序列。
      response_content: 本轮模型返回的文本内容。

    返回：
      截断后的下一状态消息历史。
    """
    if not self._keep_history:
      return ()
    history = tuple(messages) + (
        LLMMessage(role="assistant", content=response_content),
    )
    if self._max_history_messages <= 0:
      return ()
    system_messages = tuple(
        message for message in history if message.role == "system"
    )
    non_system = tuple(
        message for message in history if message.role != "system"
    )
    return system_messages[:1] + non_system[-self._max_history_messages:]
