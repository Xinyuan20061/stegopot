"""节点 ID 驱动的多智能体环境基底接口。"""

from __future__ import annotations

import abc
from collections.abc import Mapping, Sequence
import dataclasses
from types import MappingProxyType
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
  from stegopot.domain.model import AgentAction
  from stegopot.domain.model import AgentMessage


@dataclasses.dataclass(frozen=True)
class SubstrateResetContext:
  """开始一次实验时传给环境基底的完整上下文。

  属性：
    task: 本次实验的全局任务文本。
    node_ids: 按运行顺序排列的节点 ID。
    shared_context: 对全部节点可见的结构化背景信息。
    topology: 当前通信拓扑的可序列化快照。
  """

  task: str
  node_ids: Sequence[str]
  shared_context: Mapping[str, Any] = dataclasses.field(default_factory=dict)
  topology: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    normalized_task = self.task.strip() if isinstance(self.task, str) else ""
    normalized_nodes = tuple(self.node_ids)
    if not normalized_task:
      raise ValueError("SubstrateResetContext.task 必须是非空字符串")
    if not normalized_nodes:
      raise ValueError("SubstrateResetContext.node_ids 不能为空")
    if len(normalized_nodes) != len(set(normalized_nodes)):
      raise ValueError("SubstrateResetContext.node_ids 不能包含重复节点")
    if any(not isinstance(node_id, str) or not node_id.strip()
           for node_id in normalized_nodes):
      raise ValueError("SubstrateResetContext.node_ids 必须是非空字符串")
    object.__setattr__(self, "task", normalized_task)
    object.__setattr__(self, "node_ids", normalized_nodes)
    object.__setattr__(
        self, "shared_context", MappingProxyType(dict(self.shared_context))
    )
    object.__setattr__(
        self, "topology", MappingProxyType(dict(self.topology))
    )


@dataclasses.dataclass(frozen=True)
class SubstrateStepContext:
  """环境基底处理一个同步轮次所需的输入。

  属性：
    round_index: 当前同步轮次，从 0 开始。
    actions: 节点 ID 到该节点本轮动作的映射。
    messages: 通过拓扑检查后、等待环境处理的候选消息。
  """

  round_index: int
  actions: Mapping[str, AgentAction]
  messages: Sequence[AgentMessage]

  def __post_init__(self) -> None:
    if self.round_index < 0:
      raise ValueError("SubstrateStepContext.round_index 不能小于 0")
    object.__setattr__(self, "actions", MappingProxyType(dict(self.actions)))
    object.__setattr__(self, "messages", tuple(self.messages))


@dataclasses.dataclass(frozen=True)
class SubstrateEvent:
  """环境在处理一轮动作时产生的结构化事件。

  属性：
    kind: 事件类型，例如 message_delivered 或 stego_embedded。
    round_index: 事件所属轮次，从 0 开始。
    actor: 触发事件的节点 ID；没有明确节点时为空。
    target: 事件目标节点 ID；没有明确目标时为空。
    metadata: 事件附加数据，供日志、评估和调试使用。
  """

  kind: str
  round_index: int
  actor: str | None = None
  target: str | None = None
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    if not isinstance(self.kind, str) or not self.kind.strip():
      raise ValueError("SubstrateEvent.kind 必须是非空字符串")
    if self.round_index < 0:
      raise ValueError("SubstrateEvent.round_index 不能小于 0")
    object.__setattr__(self, "kind", self.kind.strip())
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  def to_dict(self) -> dict[str, Any]:
    """返回适合日志记录和 JSON 序列化的事件字典。"""
    return {
        "kind": self.kind,
        "round_index": self.round_index,
        "actor": self.actor,
        "target": self.target,
        "metadata": dict(self.metadata),
    }


@dataclasses.dataclass(frozen=True)
class SubstrateStepResult:
  """环境基底处理完一个同步轮次后的结果。

  属性：
    messages: 经过环境规则处理后实际允许投递的消息。
    rewards: 节点 ID 到本轮奖励的映射。
    events: 本轮产生的结构化环境事件。
    done: 环境是否要求立即结束本次实验。
    termination_reason: 环境结束实验时使用的原因文本。
    info: 不属于固定字段的附加环境信息。
  """

  messages: Sequence[AgentMessage] = ()
  rewards: Mapping[str, float] = dataclasses.field(default_factory=dict)
  events: Sequence[SubstrateEvent] = ()
  done: bool = False
  termination_reason: str | None = None
  info: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    if self.done and not self.termination_reason:
      object.__setattr__(self, "termination_reason", "substrate_done")
    object.__setattr__(self, "messages", tuple(self.messages))
    object.__setattr__(
        self,
        "rewards",
        MappingProxyType({
            node_id: float(reward) for node_id, reward in self.rewards.items()
        }),
    )
    object.__setattr__(self, "events", tuple(self.events))
    object.__setattr__(self, "info", MappingProxyType(dict(self.info)))


class Substrate(metaclass=abc.ABCMeta):
  """多智能体实验环境的抽象接口。

  Runtime 只负责调度节点和执行拓扑路由；Substrate 负责环境状态、
  消息变换、奖励、事件、局部环境观察和环境终止条件。
  """

  @abc.abstractmethod
  def reset(self, context: SubstrateResetContext) -> None:
    """使用一次新实验的上下文重置环境。

    参数：
      context: 全局任务、节点、共享上下文和拓扑快照。
    """
    raise NotImplementedError

  @abc.abstractmethod
  def observe(self, node_id: str) -> Mapping[str, Any]:
    """返回指定节点当前可见的环境观察。

    参数：
      node_id: 请求观察的节点 ID。

    返回：
      只包含该节点有权看到内容的结构化映射。
    """
    raise NotImplementedError

  @abc.abstractmethod
  def step(self, context: SubstrateStepContext) -> SubstrateStepResult:
    """应用一轮动作和候选消息，并推进环境状态。

    参数：
      context: 当前轮次、节点动作和拓扑路由后的候选消息。

    返回：
      实际投递消息、奖励、事件和终止信号。
    """
    raise NotImplementedError

  @abc.abstractmethod
  def state(self) -> Mapping[str, Any]:
    """返回适合记录的全局环境状态快照。"""
    raise NotImplementedError

  def close(self) -> None:
    """释放环境基底持有的模型、文件或其他资源。"""

  def __enter__(self) -> "Substrate":
    return self

  def __exit__(self, *args: Any, **kwargs: Any) -> None:
    del args, kwargs
    self.close()
