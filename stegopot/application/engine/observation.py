"""默认节点局部观察构造器。"""

from __future__ import annotations

from typing import Any

from stegopot.domain.model import AgentAction
from stegopot.domain.interface import ObservationBuilder
from stegopot.domain.interface import ObservationContext


class DefaultObservationBuilder(ObservationBuilder):
  """默认观察构造器，输出可直接放入 LLM 提示词的字典。"""

  def build(self, context: ObservationContext) -> dict[str, Any]:
    """构造默认局部观察。

    参数：
      context: 当前节点、拓扑、任务、消息和轮次上下文。

    返回：
      包含任务、节点身份、邻居、环境、收件箱和上一动作的字典。
    """
    return {
        "task": context.task,
        "round_index": context.round_index,
        "self": {
            "node_id": context.node_id,
            "role": context.role,
            "metadata": dict(context.node_metadata),
        },
        "topology": {
            "outgoing_neighbors": list(
                context.topology.outgoing_neighbors(context.node_id)
            ),
            "incoming_neighbors": list(
                context.topology.incoming_neighbors(context.node_id)
            ),
        },
        "inbox": [message.to_dict() for message in context.inbox],
        "previous_action": self._action_to_dict(context.previous_action),
        "shared_context": dict(context.shared_context),
        "environment": dict(context.environment),
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
