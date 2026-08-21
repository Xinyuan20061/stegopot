"""节点局部观察的构造接口。"""

from __future__ import annotations

import abc
from collections.abc import Mapping, Sequence
import dataclasses
from typing import Any

from meltingpot.utils.multi_agent.message import AgentMessage
from meltingpot.utils.multi_agent.node import AgentNode
from meltingpot.utils.multi_agent.topology import AgentTopology
from meltingpot.utils.policies.action import AgentAction


@dataclasses.dataclass(frozen=True)
class ObservationContext:
  """构造一次节点观察所需的完整上下文。

  属性：
    node: 当前要接收观察的智能体节点。
    topology: 当前运行使用的通信拓扑。
    task: 本次多智能体运行的全局任务文本。
    shared_context: 对全部节点可见的结构化上下文。
    round_index: 当前轮次，从 0 开始。
    inbox: 上一轮路由到当前节点的消息。
    previous_action: 当前节点上一轮的动作；第一轮为空。
  """

  node: AgentNode
  topology: AgentTopology
  task: str
  shared_context: Mapping[str, Any]
  round_index: int
  inbox: Sequence[AgentMessage]
  previous_action: AgentAction | None


class ObservationBuilder(metaclass=abc.ABCMeta):
  """把运行时上下文转换成节点可见观察的抽象接口。"""

  @abc.abstractmethod
  def build(self, context: ObservationContext) -> Any:
    """构造一个节点的局部观察。

    参数：
      context: 当前节点、拓扑、任务、消息和轮次上下文。

    返回：
      传给节点 Policy.step 的任意观察对象。
    """
    raise NotImplementedError


class DefaultObservationBuilder(ObservationBuilder):
  """默认观察构造器，输出可直接放入 LLM 提示词的字典。"""

  def build(self, context: ObservationContext) -> dict[str, Any]:
    """构造默认局部观察。

    参数：
      context: 当前节点、拓扑、任务、消息和轮次上下文。

    返回：
      包含任务、节点身份、邻居、收件箱和上一动作的字典。
    """
    return {
        "task": context.task,
        "round_index": context.round_index,
        "self": {
            "node_id": context.node.node_id,
            "role": context.node.role,
            "metadata": dict(context.node.metadata),
        },
        "topology": {
            "outgoing_neighbors": list(
                context.topology.outgoing_neighbors(context.node.node_id)
            ),
            "incoming_neighbors": list(
                context.topology.incoming_neighbors(context.node.node_id)
            ),
        },
        "inbox": [message.to_dict() for message in context.inbox],
        "previous_action": self._action_to_dict(context.previous_action),
        "shared_context": dict(context.shared_context),
    }

  @staticmethod
  def _action_to_dict(action: AgentAction | None) -> dict[str, Any] | None:
    """把可选动作转换成可序列化字典。"""
    if action is None:
      return None
    return {
        "kind": action.kind,
        "content": action.content,
        "target": action.target,
        "metadata": dict(action.metadata),
    }
