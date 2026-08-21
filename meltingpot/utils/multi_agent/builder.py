"""多智能体系统的链式构建器。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from meltingpot.utils.llm.action_parser import JsonActionParser
from meltingpot.utils.llm.client import LLMClient
from meltingpot.utils.llm.prompt import PromptBuilder
from meltingpot.utils.multi_agent.node import AgentNode
from meltingpot.utils.multi_agent.observation import ObservationBuilder
from meltingpot.utils.multi_agent.runtime import MultiAgentRuntime
from meltingpot.utils.multi_agent.runtime import RuntimeConfig
from meltingpot.utils.multi_agent.topology import AgentTopology
from meltingpot.utils.policies.llm_policy import LLMPolicy
from meltingpot.utils.policies.policy import Policy


class MultiAgentBuilder:
  """通过添加节点和通信边构建多智能体运行器。"""

  def __init__(self) -> None:
    """初始化一个没有节点和边的构建器。"""
    self._nodes: dict[str, AgentNode] = {}
    self._topology = AgentTopology()

  def add_node(
      self,
      *,
      node_id: str,
      role: str,
      policy: Policy,
      metadata: Mapping[str, Any] | None = None,
  ) -> "MultiAgentBuilder":
    """添加一个已经创建好策略的通用节点。

    参数：
      node_id: 节点在当前系统中的唯一 ID。
      role: 节点承担的业务角色。
      policy: 节点使用的策略，可以是 LLM、规则或测试策略。
      metadata: 节点级附加信息，仅用于记录或后续扩展。

    返回：
      当前构建器，便于链式调用。
    """
    node = AgentNode(
        node_id=node_id,
        role=role,
        policy=policy,
        metadata=metadata,
    )
    self._topology.add_node(node.node_id)
    self._nodes[node.node_id] = node
    return self

  def add_llm_node(
      self,
      *,
      node_id: str,
      role: str,
      client: LLMClient,
      system_prompt: str = "",
      model: str | None = None,
      temperature: float | None = None,
      max_tokens: int | None = None,
      keep_history: bool = True,
      max_history_messages: int = 20,
      action_parser: JsonActionParser | None = None,
      metadata: Mapping[str, Any] | None = None,
  ) -> "MultiAgentBuilder":
    """创建并添加一个 LLM 节点。

    参数：
      node_id: 节点在当前系统中的唯一 ID。
      role: 节点承担的业务角色。
      client: 实际调用模型供应商的 LLM 客户端。
      system_prompt: 该节点专属的系统提示词。
      model: 模型名称；为空时由客户端使用默认模型。
      temperature: 模型采样温度；为空时由客户端使用默认值。
      max_tokens: 单次模型响应的最大 token 数。
      keep_history: 是否保留该节点自己的模型消息历史。
      max_history_messages: 最多保留多少条非 system 历史消息。
      action_parser: 自定义模型输出解析器；为空时使用 JSON 解析器。
      metadata: 节点级附加信息，仅用于记录或后续扩展。

    返回：
      当前构建器，便于链式调用。
    """
    policy = LLMPolicy(
        node_id=node_id,
        role=role,
        client=client,
        prompt_builder=PromptBuilder(system_prompt=system_prompt),
        action_parser=action_parser,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        keep_history=keep_history,
        max_history_messages=max_history_messages,
        metadata=metadata,
    )
    return self.add_node(
        node_id=node_id,
        role=role,
        policy=policy,
        metadata=metadata,
    )

  def connect(
      self,
      source: str,
      target: str,
      *,
      bidirectional: bool = False,
  ) -> "MultiAgentBuilder":
    """添加一条节点通信边。

    参数：
      source: 允许发送消息的源节点 ID。
      target: 允许接收消息的目标节点 ID。
      bidirectional: 是否同时添加一条反向边。

    返回：
      当前构建器，便于链式调用。
    """
    self._topology.connect(
        source,
        target,
        bidirectional=bidirectional,
    )
    return self

  def connect_all(self) -> "MultiAgentBuilder":
    """把当前全部节点连接成不含自环的全连接有向拓扑。

    返回：
      当前构建器，便于链式调用。
    """
    for source in self._topology.nodes:
      for target in self._topology.nodes:
        if source != target:
          self._topology.connect(source, target)
    return self

  def build(
      self,
      *,
      config: RuntimeConfig | None = None,
      observation_builder: ObservationBuilder | None = None,
  ) -> MultiAgentRuntime:
    """构建一个可执行的多智能体运行器。

    参数：
      config: 轮数、终止和错误处理配置。
      observation_builder: 自定义局部观察构造器。

    返回：
      持有节点与拓扑副本的 MultiAgentRuntime。
    """
    return MultiAgentRuntime(
        nodes=self._nodes,
        topology=self._topology,
        config=config,
        observation_builder=observation_builder,
    )
