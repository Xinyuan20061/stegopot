"""节点局部观察构造器的扩展接口。"""

from __future__ import annotations

import abc
from collections.abc import Mapping, Sequence
import dataclasses
from typing import Any

from stegopot.domain.model import AgentAction
from stegopot.domain.model import AgentMessage
from stegopot.domain.model import AgentTopology


@dataclasses.dataclass(frozen=True)
class ObservationContext:
  """构造一次节点局部观察所需的稳定上下文。

  该契约只包含值对象，不引用 AgentNode 等运行时实现，因此自定义观察
  构造器不需要依赖 core 层。

  属性：
    node_id: 当前节点 ID。
    role: 当前节点角色。
    node_metadata: 当前节点的公开元数据。
    topology: 本次运行的通信拓扑。
    task: 全局任务文本。
    shared_context: 对全部节点可见的结构化上下文。
    environment: Substrate 只允许当前节点看到的环境观察。
    round_index: 当前同步轮次，从 0 开始。
    inbox: 上一轮投递到当前节点的消息。
    previous_action: 当前节点上一轮动作；第一轮为空。
  """

  node_id: str
  role: str
  node_metadata: Mapping[str, Any]
  topology: AgentTopology
  task: str
  shared_context: Mapping[str, Any]
  environment: Mapping[str, Any]
  round_index: int
  inbox: Sequence[AgentMessage]
  previous_action: AgentAction | None


class ObservationBuilder(metaclass=abc.ABCMeta):
  """把稳定上下文转换成节点可见观察的抽象接口。"""

  @abc.abstractmethod
  def build(self, context: ObservationContext) -> Any:
    """构造一个节点的局部观察。

    参数：
      context: 节点身份、任务、拓扑、消息和环境上下文。

    返回：
      传给 Policy.step 的任意观察对象。
    """
    raise NotImplementedError
