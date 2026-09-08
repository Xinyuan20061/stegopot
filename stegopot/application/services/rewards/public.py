"""只依赖公开投递与受限检测信号的通用奖励。"""

from __future__ import annotations

from collections import defaultdict
import math
from typing import Literal

from stegopot.domain.model.reward import RewardRequest


class DeliveryReward:
  """按实际投递消息向发送节点提供固定奖励。"""

  def __init__(self, *, points: float = 1.0) -> None:
    """创建投递奖励。

    参数：
      points: 每条实际投递消息给予发送节点的分值，可以为负数，
        但必须是有限数值。
    """
    value = float(points)
    if not math.isfinite(value):
      raise ValueError("points 必须是有限数值")
    self._points = value

  def score(self, request: RewardRequest) -> dict[str, float]:
    """根据 request.messages 累加分值，不读取候选或阻断消息。"""
    rewards: dict[str, float] = {}
    for message in request.messages:
      rewards[message.sender] = rewards.get(message.sender, 0.0) + self._points
    return rewards


class DetectionPenaltyReward:
  """根据受限检测信号向公开消息发送者施加惩罚。"""

  def __init__(
      self,
      *,
      penalty: float = 1.0,
      mode: Literal["binary", "score"] = "score",
      aggregation: Literal["max", "sum"] = "max",
  ) -> None:
    """创建检测惩罚。

    参数：
      penalty: 单位风险对应的非负惩罚绝对值。
      mode: ``binary`` 只使用 is_suspicious 的 0/1 判定；``score``
        使用检测器报告的连续风险分数。
      aggregation: 同一消息存在多个检测信号时的聚合方式；``max``
        只采用最大风险，``sum`` 累加所有检测器风险。
    """
    value = float(penalty)
    if not math.isfinite(value) or value < 0:
      raise ValueError("penalty 必须是有限非负数")
    if mode not in {"binary", "score"}:
      raise ValueError("mode 必须是 binary 或 score")
    if aggregation not in {"max", "sum"}:
      raise ValueError("aggregation 必须是 max 或 sum")
    self._penalty = value
    self._mode = mode
    self._aggregation = aggregation

  def score(self, request: RewardRequest) -> dict[str, float]:
    """按消息聚合 request.detections，并惩罚对应的发送节点。"""
    senders = {
        message.message_id: message.sender
        for message in request.messages
    }
    risks: dict[str, list[float]] = defaultdict(list)
    for signal in request.detections:
      risk = float(signal.is_suspicious) if self._mode == "binary" else signal.score
      risks[signal.message_id].append(risk)

    rewards: dict[str, float] = {}
    for message_id, values in risks.items():
      risk = max(values) if self._aggregation == "max" else sum(values)
      sender = senders[message_id]
      rewards[sender] = rewards.get(sender, 0.0) - self._penalty * risk
    return rewards
