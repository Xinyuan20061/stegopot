"""不改变消息内容的默认多智能体通信环境。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stegopot.domain.interface import Substrate
from stegopot.domain.interface import SubstrateEvent
from stegopot.domain.interface import SubstrateResetContext
from stegopot.domain.interface import SubstrateStepContext
from stegopot.domain.interface import SubstrateStepResult


class CommunicationSubstrate(Substrate):
  """按原样投递合法拓扑消息的默认环境。

  该实现不施加隐写、噪声、过滤或奖励规则，用于保持现有多智能体
  框架的行为不变，同时为后续环境扩展提供统一基线。
  """

  def __init__(self) -> None:
    """初始化一个尚未开始实验的通信环境。"""
    self._reset_context: SubstrateResetContext | None = None
    self._completed_rounds = 0
    self._delivered_message_count = 0
    self._last_rewards: dict[str, float] = {}

  def reset(self, context: SubstrateResetContext) -> None:
    """清空环境计数器并保存本次实验上下文。

    参数：
      context: 全局任务、节点、共享上下文和拓扑快照。
    """
    self._reset_context = context
    self._completed_rounds = 0
    self._delivered_message_count = 0
    self._last_rewards = {node_id: 0.0 for node_id in context.node_ids}

  def observe(self, node_id: str) -> Mapping[str, Any]:
    """返回指定节点可见的基础环境状态。

    参数：
      node_id: 请求观察的节点 ID。

    返回：
      当前已完成轮数、累计消息数和该节点上一轮奖励。
    """
    reset_context = self._require_initialized()
    if node_id not in reset_context.node_ids:
      raise KeyError(f"环境中不存在节点：{node_id}")
    return {
        "substrate": type(self).__name__,
        "completed_rounds": self._completed_rounds,
        "delivered_message_count": self._delivered_message_count,
        "last_reward": self._last_rewards[node_id],
    }

  def step(self, context: SubstrateStepContext) -> SubstrateStepResult:
    """验证并按原样放行本轮全部候选消息。

    参数：
      context: 当前轮次、节点动作和拓扑路由后的候选消息。

    返回：
      原始候选消息、零奖励和对应的消息投递事件。
    """
    reset_context = self._require_initialized()
    if context.round_index != self._completed_rounds:
      raise ValueError(
          "环境轮次不连续："
          f"期望 {self._completed_rounds}，实际 {context.round_index}"
      )

    known_nodes = set(reset_context.node_ids)
    unknown_actors = set(context.actions) - known_nodes
    if unknown_actors:
      raise ValueError(f"动作包含未知节点：{sorted(unknown_actors)}")
    for message in context.messages:
      if message.sender not in known_nodes:
        raise ValueError(f"消息发送者不在环境中：{message.sender}")
      if message.recipient not in known_nodes:
        raise ValueError(f"消息接收者不在环境中：{message.recipient}")

    rewards = {node_id: 0.0 for node_id in reset_context.node_ids}
    events = tuple(
        SubstrateEvent(
            kind="message_delivered",
            round_index=context.round_index,
            actor=message.sender,
            target=message.recipient,
            metadata={"message_id": message.message_id},
        )
        for message in context.messages
    )
    self._completed_rounds += 1
    self._delivered_message_count += len(context.messages)
    self._last_rewards = rewards
    return SubstrateStepResult(
        messages=context.messages,
        rewards=rewards,
        events=events,
        info={
            "completed_rounds": self._completed_rounds,
            "delivered_message_count": self._delivered_message_count,
        },
    )

  def state(self) -> Mapping[str, Any]:
    """返回不包含节点私密数据的环境状态快照。"""
    reset_context = self._require_initialized()
    return {
        "substrate": type(self).__name__,
        "task": reset_context.task,
        "node_ids": list(reset_context.node_ids),
        "completed_rounds": self._completed_rounds,
        "delivered_message_count": self._delivered_message_count,
        "last_rewards": dict(self._last_rewards),
    }

  def _require_initialized(self) -> SubstrateResetContext:
    """返回重置上下文；尚未 reset 时抛出清晰错误。"""
    if self._reset_context is None:
      raise RuntimeError("使用 Substrate 前必须先调用 reset")
    return self._reset_context
