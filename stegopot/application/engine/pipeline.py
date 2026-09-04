"""组合环境、公开信道、检测器和奖励，统一执行信息边界。"""

from collections.abc import Mapping, Sequence
import dataclasses
import math
from typing import Any

from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.channel import ChannelTransform
from stegopot.domain.interface.detector import StegoDetector
from stegopot.domain.interface.experiment import RewardFunction
from stegopot.domain.interface.substrate import (
    Substrate, SubstrateEvent, SubstrateResetContext, SubstrateStepContext, SubstrateStepResult,
)
from stegopot.domain.model.detection import DetectionRequest, DetectionResult
from stegopot.domain.model.experiment import json_copy
from stegopot.domain.model.message import AgentMessage


class ExperimentPipeline(Substrate):
  """只通过领域契约组合插件，不导入任何具体供应商或记录器。"""

  def __init__(
      self, inner: Substrate, *, audit: AuditSink,
      node_contexts: Mapping[str, Mapping[str, Any]],
      channels: Sequence[tuple[str, ChannelTransform]] = (),
      detectors: Sequence[tuple[str, StegoDetector]] = (),
      rewards: Sequence[tuple[str, RewardFunction]] = (),
  ) -> None:
    """创建每次试验独享的环境管线。

    参数：
      inner: 负责世界状态的基础环境，必须由组合根注入。
      audit: 受宿主管理的审计接口，异常不可静默忽略。
      node_contexts: 显式按节点授权的私有数据，不给检测器或其他节点。
      channels: 按配置顺序执行的具名公开正文变换器。
      detectors: 只检查最终公开正文的具名检测器。
      rewards: 根据公开轮次转移计算反馈的具名奖励函数。
    """
    self._inner = inner
    self._audit = audit
    self._private = json_copy(node_contexts)
    self._channels = tuple(channels)
    self._detectors = tuple(detectors)
    self._rewards = tuple(rewards)
    self._ids: set[str] = set()
    self._feedback: dict[str, float] = {}
    self._public = []

  def reset(self, context: SubstrateResetContext) -> None:
    """以 context 重置环境；私有观察必须引用已注册节点。"""
    self._ids = set(context.node_ids)
    if set(self._private) - self._ids:
      raise ValueError("私有上下文引用未知节点")
    self._feedback = {}
    self._public = []
    self._inner.reset(context)
    for _, detector in self._detectors:
      detector.reset()

  def observe(self, node_id: str) -> Mapping[str, Any]:
    """给 node_id 投影私有数据和自身奖励，绝不附加计划、种子或中央真值。"""
    if node_id not in self._ids:
      raise ValueError("未知观察主体")
    value = dict(self._inner.observe(node_id))
    if "framework" in value:
      raise ValueError("环境不得覆盖 framework 保留观察字段")
    value["framework"] = {"private": json_copy(self._private.get(node_id, {}))}
    if node_id in self._feedback:
      value["framework"]["reward"] = self._feedback[node_id]
    # 观察者通过授权的配置请求转录，而不是收到内部状态或干预前的消息。
    if self._private.get(node_id, {}).get("observe_public_channel") is True:
      value["framework"]["public_channel"] = json_copy(self._public)
    return value

  def step(self, context: SubstrateStepContext) -> SubstrateStepResult:
    """推进 context，再依次完成身份校验、元数据剥离、干预、检测和奖励。"""
    result = self._inner.step(context)
    candidates = {message.message_id: message for message in context.messages}
    delivered = []
    events = list(result.events)
    seen = set()
    for message in result.messages:
      original = candidates.get(message.message_id)
      if original is None or message.message_id in seen:
        raise ValueError("环境伪造或重复了候选消息")
      self._validate_identity(original, message)
      seen.add(message.message_id)
      current = dataclasses.replace(message, metadata={})
      for name, channel in self._channels:
        before = current
        current = channel.transform(current)
        if current is not None:
          self._validate_identity(before, current)
          if current.metadata:
            raise ValueError("公开信道插件不得附加元数据")
        self._audit.emit({"kind": "channel.transformed", "round_index": context.round_index,
                          "data": {"component": name, "input": before.to_dict(),
                                   "output": None if current is None else current.to_dict()}})
        if current is None:
          break
      if current is not None:
        delivered.append(current)
    self._public.extend(message.to_dict() for message in delivered)
    for message in delivered:
      for name, detector in self._detectors:
        request = DetectionRequest(
            message_id=message.message_id, sender=message.sender, recipient=message.recipient,
            content=message.content, round_index=message.round_index, metadata={}, context={},
        )
        finding = detector.detect(request)
        if not isinstance(finding, DetectionResult) or finding.message_id != message.message_id:
          raise ValueError("检测器返回了错误的结果类型或消息 ID")
        events.append(SubstrateEvent("detector.result", context.round_index, metadata={
            "component": name, "finding": finding.to_dict(),
        }))
    totals = dict(result.rewards)
    transition = {"round_index": context.round_index,
                  "messages": [message.to_dict() for message in delivered],
                  "actions": {key: {"kind": value.kind,
                                    "target": value.target} for key, value in context.actions.items()}}
    for name, reward in self._rewards:
      values = dict(reward.score(json_copy(transition)))
      self._validate_rewards(values)
      for node, value in values.items():
        totals[node] = totals.get(node, 0.0) + value
      events.append(SubstrateEvent("reward.computed", context.round_index,
                                   metadata={"component": name, "rewards": values}))
    self._validate_rewards(totals)
    self._feedback = totals
    return SubstrateStepResult(messages=delivered, rewards=totals, events=events,
                               done=result.done, termination_reason=result.termination_reason,
                               info=dict(result.info))

  def state(self) -> Mapping[str, Any]:
    """返回中央研究状态；不会自动进入任何节点的观察。"""
    return {"environment": self._inner.state(), "delivered_count": len(self._public)}

  def close(self) -> None:
    """资源统一由组合根的生命周期栈关闭，避免共享客户端被重复关闭。"""

  @staticmethod
  def _validate_identity(before: AgentMessage, after: AgentMessage) -> None:
    """验证 before/after 属于同一投递身份，插件只能变换正文。"""
    if not isinstance(after, AgentMessage):
      raise TypeError("信道必须返回 AgentMessage 或 None")
    fields = ("message_id", "sender", "recipient", "round_index")
    if any(getattr(before, key) != getattr(after, key) for key in fields):
      raise ValueError("信道不能改变消息 ID、发送者、接收者或轮次")

  def _validate_rewards(self, values: Mapping[str, float]) -> None:
    """验证 values 只向现有节点分配有限数值，不允许 NaN 污染审计。"""
    if set(values) - self._ids:
      raise ValueError("奖励引用未知节点")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in values.values()):
      raise ValueError("奖励必须是有限数值")
