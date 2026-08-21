"""自定义拓扑多智能体同步运行器。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses
from types import MappingProxyType
from typing import Any, Literal

from meltingpot.utils.multi_agent.message import AgentMessage
from meltingpot.utils.multi_agent.message import MessageRouter
from meltingpot.utils.multi_agent.message import MessageRoutingError
from meltingpot.utils.multi_agent.node import AgentNode
from meltingpot.utils.multi_agent.node import NodeExecutionError
from meltingpot.utils.multi_agent.observation import DefaultObservationBuilder
from meltingpot.utils.multi_agent.observation import ObservationBuilder
from meltingpot.utils.multi_agent.observation import ObservationContext
from meltingpot.utils.multi_agent.topology import AgentTopology
from meltingpot.utils.policies.action import AgentAction

TerminationMode = Literal["max_rounds", "any_final", "all_final"]


@dataclasses.dataclass(frozen=True)
class RuntimeConfig:
  """多智能体运行器配置。

  属性：
    max_rounds: 单次运行允许的最大同步轮次数，必须大于 0。
    termination_mode: 提前结束方式。``any_final`` 表示任一节点提交
      final_answer 后结束；``all_final`` 表示全部节点都提交后结束；
      ``max_rounds`` 表示仅受最大轮数限制。
    strict_routing: 为 True 时，非法消息目标会立即终止运行；为 False
      时记录错误并丢弃该消息。
    fail_fast: 为 True 时，节点执行异常会立即终止运行；为 False 时
      把异常记录成等待动作，并继续调度其他节点。
    deactivate_on_final: 节点提交 final_answer 后是否停止继续调度。
  """

  max_rounds: int = 5
  termination_mode: TerminationMode = "all_final"
  strict_routing: bool = True
  fail_fast: bool = True
  deactivate_on_final: bool = True

  def __post_init__(self) -> None:
    if self.max_rounds <= 0:
      raise ValueError("max_rounds 必须大于 0")
    if self.termination_mode not in {
        "max_rounds", "any_final", "all_final"
    }:
      raise ValueError(f"不支持的 termination_mode：{self.termination_mode}")


@dataclasses.dataclass(frozen=True)
class NodeStepRecord:
  """一个节点在一轮中的决策记录。

  属性：
    node_id: 执行决策的节点 ID。
    observation: 本轮传给该节点的局部观察。
    action: 节点输出的动作。
    error: 非快速失败模式下捕获的错误文本；正常时为空。
  """

  node_id: str
  observation: Any
  action: AgentAction
  error: str | None = None

  def to_dict(self) -> dict[str, Any]:
    """返回适合日志记录和 JSON 序列化的步骤字典。"""
    return {
        "node_id": self.node_id,
        "observation": self.observation,
        "action": _action_to_dict(self.action),
        "error": self.error,
    }


@dataclasses.dataclass(frozen=True)
class RoundRecord:
  """一个同步轮次的完整记录。

  属性：
    round_index: 当前轮次，从 0 开始。
    steps: 本轮各节点的决策记录。
    delivered_messages: 本轮产生、将在下一轮被观察到的消息。
    routing_errors: 非严格路由模式下捕获的错误文本。
  """

  round_index: int
  steps: Sequence[NodeStepRecord]
  delivered_messages: Sequence[AgentMessage]
  routing_errors: Sequence[str] = ()

  def __post_init__(self) -> None:
    object.__setattr__(self, "steps", tuple(self.steps))
    object.__setattr__(
        self, "delivered_messages", tuple(self.delivered_messages)
    )
    object.__setattr__(self, "routing_errors", tuple(self.routing_errors))

  def to_dict(self) -> dict[str, Any]:
    """返回适合日志记录和 JSON 序列化的轮次字典。"""
    return {
        "round_index": self.round_index,
        "steps": [step.to_dict() for step in self.steps],
        "delivered_messages": [
            message.to_dict() for message in self.delivered_messages
        ],
        "routing_errors": list(self.routing_errors),
    }


@dataclasses.dataclass(frozen=True)
class RunResult:
  """一次多智能体运行的最终结果。

  属性：
    task: 本次运行的全局任务文本。
    topology: 本次运行使用的拓扑快照。
    rounds: 全部已完成轮次的记录。
    messages: 按发送顺序排列的完整消息转录。
    final_answers: 节点 ID 到最终答案正文的映射。
    termination_reason: 运行结束原因。
  """

  task: str
  topology: Mapping[str, Any]
  rounds: Sequence[RoundRecord]
  messages: Sequence[AgentMessage]
  final_answers: Mapping[str, str]
  termination_reason: str

  def __post_init__(self) -> None:
    object.__setattr__(self, "topology", MappingProxyType(dict(self.topology)))
    object.__setattr__(self, "rounds", tuple(self.rounds))
    object.__setattr__(self, "messages", tuple(self.messages))
    object.__setattr__(
        self, "final_answers", MappingProxyType(dict(self.final_answers))
    )

  @property
  def completed_rounds(self) -> int:
    """返回实际完成的同步轮次数。"""
    return len(self.rounds)

  def to_dict(self) -> dict[str, Any]:
    """返回适合写入 JSON 文件的完整运行结果。"""
    return {
        "task": self.task,
        "topology": dict(self.topology),
        "rounds": [round_record.to_dict() for round_record in self.rounds],
        "messages": [message.to_dict() for message in self.messages],
        "final_answers": dict(self.final_answers),
        "termination_reason": self.termination_reason,
        "completed_rounds": self.completed_rounds,
    }


class MultiAgentRuntime:
  """在自定义有向拓扑上同步调度多个智能体节点。

  每轮先让所有活跃节点基于上一轮收件箱独立决策，再统一路由
  本轮消息。因此节点添加顺序不会让同轮内的后执行节点提前看到消息。
  """

  def __init__(
      self,
      *,
      nodes: Mapping[str, AgentNode],
      topology: AgentTopology,
      config: RuntimeConfig | None = None,
      observation_builder: ObservationBuilder | None = None,
  ) -> None:
    """初始化多智能体运行器。

    参数：
      nodes: 节点 ID 到 AgentNode 的映射。
      topology: 定义节点间可通信有向边的拓扑。
      config: 轮数、终止和错误处理配置。
      observation_builder: 自定义局部观察构造器；为空时使用默认实现。
    """
    self._nodes = dict(nodes)
    self._topology = topology.copy()
    self._config = config or RuntimeConfig()
    self._observation_builder = (
        observation_builder or DefaultObservationBuilder()
    )
    self._validate_nodes()
    self._router = MessageRouter(self._topology)

  @property
  def topology(self) -> AgentTopology:
    """返回运行器持有的拓扑副本。"""
    return self._topology.copy()

  def run(
      self,
      task: str,
      *,
      shared_context: Mapping[str, Any] | None = None,
  ) -> RunResult:
    """运行一次完整的多智能体交互。

    参数：
      task: 全部节点共同接收的任务文本。
      shared_context: 全部节点都可见的结构化背景信息。

    返回：
      包含轮次、消息转录、最终答案和终止原因的运行结果。
    """
    if not isinstance(task, str) or not task.strip():
      raise ValueError("task 必须是非空字符串")
    context = MappingProxyType(dict(shared_context or {}))
    self._reset_nodes()
    self._router.reset()

    inboxes: dict[str, list[AgentMessage]] = {
        node_id: [] for node_id in self._topology.nodes
    }
    previous_actions: dict[str, AgentAction | None] = {
        node_id: None for node_id in self._topology.nodes
    }
    final_answers: dict[str, str] = {}
    transcript: list[AgentMessage] = []
    round_records: list[RoundRecord] = []
    termination_reason = "max_rounds"

    for round_index in range(self._config.max_rounds):
      step_records: list[NodeStepRecord] = []
      actions: dict[str, AgentAction] = {}

      for node_id in self._topology.nodes:
        if self._is_inactive(node_id, final_answers):
          continue
        node = self._nodes[node_id]
        observation = self._observation_builder.build(ObservationContext(
            node=node,
            topology=self._topology,
            task=task.strip(),
            shared_context=context,
            round_index=round_index,
            inbox=tuple(inboxes[node_id]),
            previous_action=previous_actions[node_id],
        ))
        action, error = self._execute_node(node, observation)
        actions[node_id] = action
        previous_actions[node_id] = action
        step_records.append(NodeStepRecord(
            node_id=node_id,
            observation=observation,
            action=action,
            error=error,
        ))
        if action.kind == "final_answer":
          final_answers[node_id] = action.content or ""

      next_inboxes: dict[str, list[AgentMessage]] = {
          node_id: [] for node_id in self._topology.nodes
      }
      delivered_messages: list[AgentMessage] = []
      routing_errors: list[str] = []
      for sender, action in actions.items():
        try:
          routed = self._router.route(
              sender=sender,
              action=action,
              round_index=round_index,
          )
        except MessageRoutingError as exc:
          if self._config.strict_routing:
            raise
          routing_errors.append(str(exc))
          continue
        for message in routed:
          next_inboxes[message.recipient].append(message)
          delivered_messages.append(message)
          transcript.append(message)

      round_records.append(RoundRecord(
          round_index=round_index,
          steps=step_records,
          delivered_messages=delivered_messages,
          routing_errors=routing_errors,
      ))
      inboxes = next_inboxes

      early_reason = self._termination_reason(final_answers)
      if early_reason is not None:
        termination_reason = early_reason
        break

    return RunResult(
        task=task.strip(),
        topology=self._topology.to_dict(),
        rounds=round_records,
        messages=transcript,
        final_answers=final_answers,
        termination_reason=termination_reason,
    )

  def close(self) -> None:
    """关闭全部节点及其策略资源。"""
    for node in self._nodes.values():
      node.close()

  def _validate_nodes(self) -> None:
    """验证节点映射和拓扑完全对应。"""
    if not self._topology.nodes:
      raise ValueError("多智能体运行器至少需要一个节点")
    topology_nodes = set(self._topology.nodes)
    mapping_nodes = set(self._nodes)
    if topology_nodes != mapping_nodes:
      missing = sorted(topology_nodes - mapping_nodes)
      extra = sorted(mapping_nodes - topology_nodes)
      raise ValueError(
          f"节点映射与拓扑不一致，缺少={missing}，多余={extra}"
      )
    for node_id, node in self._nodes.items():
      if node.node_id != node_id:
        raise ValueError(
            f"节点映射键 {node_id} 与 AgentNode.node_id {node.node_id} 不一致"
        )

  def _reset_nodes(self) -> None:
    """按拓扑顺序重置全部节点。"""
    for node_id in self._topology.nodes:
      self._nodes[node_id].reset()

  def _execute_node(
      self,
      node: AgentNode,
      observation: Any,
  ) -> tuple[AgentAction, str | None]:
    """执行节点，并根据配置处理策略异常。"""
    try:
      return node.act(observation), None
    except Exception as exc:  # pylint: disable=broad-exception-caught
      if self._config.fail_fast:
        raise NodeExecutionError(
            f"节点 {node.node_id} 在决策时失败：{exc}"
        ) from exc
      error = f"{type(exc).__name__}: {exc}"
      return AgentAction.wait(metadata={"execution_error": error}), error

  def _is_inactive(
      self,
      node_id: str,
      final_answers: Mapping[str, str],
  ) -> bool:
    """判断已经提交最终答案的节点是否应停止调度。"""
    return self._config.deactivate_on_final and node_id in final_answers

  def _termination_reason(
      self,
      final_answers: Mapping[str, str],
  ) -> str | None:
    """根据当前最终答案集合判断是否提前结束。"""
    if self._config.termination_mode == "any_final" and final_answers:
      return "any_final_answer"
    if (
        self._config.termination_mode == "all_final"
        and len(final_answers) == len(self._nodes)
    ):
      return "all_final_answers"
    return None

  def __enter__(self) -> "MultiAgentRuntime":
    return self

  def __exit__(self, *args: Any, **kwargs: Any) -> None:
    del args, kwargs
    self.close()


def _action_to_dict(action: AgentAction) -> dict[str, Any]:
  """把动作转换成可序列化字典。"""
  return {
      "kind": action.kind,
      "content": action.content,
      "target": action.target,
      "metadata": dict(action.metadata),
  }
