"""隐写检测请求、结果、发现记录和分类指标。"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
import math
from types import MappingProxyType
from typing import Any


@dataclasses.dataclass(frozen=True)
class DetectionRequest:
  """提交给隐写检测器的一条公开消息。

  属性：
    message_id: 被检测消息的唯一 ID。
    sender: 公开消息的发送节点 ID。
    recipient: 公开消息的接收节点 ID。
    content: 检测器可以读取的公开消息正文。
    round_index: 消息产生的同步轮次，从 0 开始。
    metadata: 已经过环境过滤、允许公开的消息元数据。
    context: 任务、拓扑等允许提供给检测器的公开实验上下文。
  """

  message_id: str
  sender: str
  recipient: str
  content: str
  round_index: int
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)
  context: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    for field_name in ("message_id", "sender", "recipient"):
      value = getattr(self, field_name)
      if not isinstance(value, str) or not value.strip():
        raise ValueError(f"DetectionRequest.{field_name} 必须是非空字符串")
      object.__setattr__(self, field_name, value.strip())
    if not isinstance(self.content, str) or not self.content.strip():
      raise ValueError("DetectionRequest.content 必须是非空字符串")
    if self.round_index < 0:
      raise ValueError("DetectionRequest.round_index 不能小于 0")
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
    object.__setattr__(self, "context", MappingProxyType(dict(self.context)))

  def to_dict(self, *, include_context: bool = True) -> dict[str, Any]:
    """返回适合记录或交给审计节点的字典。

    参数：
      include_context: 是否包含实验公开上下文；审计观察通常不需要重复它。

    返回：
      只包含公开消息数据的可序列化字典。
    """
    data = {
        "message_id": self.message_id,
        "sender": self.sender,
        "recipient": self.recipient,
        "content": self.content,
        "round_index": self.round_index,
        "metadata": dict(self.metadata),
    }
    if include_context:
      data["context"] = dict(self.context)
    return data


@dataclasses.dataclass(frozen=True)
class DetectionResult:
  """检测器对一条公开消息给出的判定。

  属性：
    message_id: 与 DetectionRequest 对应的消息 ID。
    detector_id: 产生结果的检测器 ID。
    is_suspicious: 是否判定消息可能包含隐写内容。
    score: 隐写风险分数，取值范围为 0 到 1。
    confidence: 对当前判定的可选置信度，取值范围为 0 到 1。
    reason: 面向实验记录的简短判定理由。
    metadata: 检测器附加的公开诊断信息。
  """

  message_id: str
  detector_id: str
  is_suspicious: bool
  score: float
  confidence: float | None = None
  reason: str = ""
  metadata: Mapping[str, Any] = dataclasses.field(default_factory=dict)

  def __post_init__(self) -> None:
    for field_name in ("message_id", "detector_id"):
      value = getattr(self, field_name)
      if not isinstance(value, str) or not value.strip():
        raise ValueError(f"DetectionResult.{field_name} 必须是非空字符串")
      object.__setattr__(self, field_name, value.strip())
    if not isinstance(self.is_suspicious, bool):
      raise TypeError("DetectionResult.is_suspicious 必须是 bool")
    score = float(self.score)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
      raise ValueError("DetectionResult.score 必须位于 [0, 1] 区间")
    object.__setattr__(self, "score", score)
    if self.confidence is not None:
      confidence = float(self.confidence)
      if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError("DetectionResult.confidence 必须位于 [0, 1] 区间")
      object.__setattr__(self, "confidence", confidence)
    if not isinstance(self.reason, str):
      raise TypeError("DetectionResult.reason 必须是字符串")
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  def to_dict(self) -> dict[str, Any]:
    """返回适合日志记录和 JSON 序列化的检测结果。"""
    return {
        "message_id": self.message_id,
        "detector_id": self.detector_id,
        "is_suspicious": self.is_suspicious,
        "score": self.score,
        "confidence": self.confidence,
        "reason": self.reason,
        "metadata": dict(self.metadata),
    }


@dataclasses.dataclass(frozen=True)
class DetectionFinding:
  """提供给审计节点的一条公开消息及其检测结果。

  属性：
    request: 检测器读取的公开消息请求。
    result: 不包含中央真实标签的检测判定。
  """

  request: DetectionRequest
  result: DetectionResult

  def __post_init__(self) -> None:
    if self.request.message_id != self.result.message_id:
      raise ValueError("DetectionFinding 的请求和结果 message_id 必须一致")

  def to_dict(self) -> dict[str, Any]:
    """返回不包含实验真实标签的审计发现字典。"""
    return {
        "message": self.request.to_dict(include_context=False),
        "result": self.result.to_dict(),
    }


@dataclasses.dataclass(frozen=True)
class DetectionMetrics:
  """由中央实验标签计算得到的二分类检测指标。

  属性：
    true_positive: 正确检出隐写消息的数量。
    true_negative: 正确放行普通消息的数量。
    false_positive: 把普通消息误判为隐写的数量。
    false_negative: 漏检隐写消息的数量。
    failed: 检测器执行失败、无法形成判定的消息数量。
    total_detection_time_seconds: 包含失败尝试在内的全部检测调用累计耗时。
  """

  true_positive: int = 0
  true_negative: int = 0
  false_positive: int = 0
  false_negative: int = 0
  failed: int = 0
  total_detection_time_seconds: float = 0.0

  def __post_init__(self) -> None:
    for field_name in (
        "true_positive",
        "true_negative",
        "false_positive",
        "false_negative",
        "failed",
    ):
      if getattr(self, field_name) < 0:
        raise ValueError(f"DetectionMetrics.{field_name} 不能小于 0")
    if self.total_detection_time_seconds < 0:
      raise ValueError("total_detection_time_seconds 不能小于 0")

  @property
  def classified(self) -> int:
    """返回形成有效二分类判定的消息总数。"""
    return (
        self.true_positive
        + self.true_negative
        + self.false_positive
        + self.false_negative
    )

  @property
  def total(self) -> int:
    """返回包含失败调用在内的检测消息总数。"""
    return self.classified + self.failed

  @property
  def precision(self) -> float:
    """返回隐写判定的精确率。"""
    return _safe_divide(
        self.true_positive,
        self.true_positive + self.false_positive,
    )

  @property
  def recall(self) -> float:
    """返回隐写消息的召回率。"""
    return _safe_divide(
        self.true_positive,
        self.true_positive + self.false_negative,
    )

  @property
  def f1(self) -> float:
    """返回精确率和召回率的调和平均值。"""
    return _safe_divide(
        2.0 * self.precision * self.recall,
        self.precision + self.recall,
    )

  @property
  def accuracy(self) -> float:
    """返回全部有效判定中的准确率。"""
    return _safe_divide(
        self.true_positive + self.true_negative,
        self.classified,
    )

  @property
  def false_positive_rate(self) -> float:
    """返回普通消息被误报的比例。"""
    return _safe_divide(
        self.false_positive,
        self.false_positive + self.true_negative,
    )

  @property
  def false_negative_rate(self) -> float:
    """返回隐写消息被漏检的比例。"""
    return _safe_divide(
        self.false_negative,
        self.false_negative + self.true_positive,
    )

  @property
  def average_detection_time_seconds(self) -> float:
    """返回每次检测尝试的平均耗时。"""
    return _safe_divide(self.total_detection_time_seconds, self.total)

  def to_dict(self) -> dict[str, Any]:
    """返回包含计数和派生指标的可序列化字典。"""
    return {
        "true_positive": self.true_positive,
        "true_negative": self.true_negative,
        "false_positive": self.false_positive,
        "false_negative": self.false_negative,
        "failed": self.failed,
        "classified": self.classified,
        "total": self.total,
        "precision": self.precision,
        "recall": self.recall,
        "f1": self.f1,
        "accuracy": self.accuracy,
        "false_positive_rate": self.false_positive_rate,
        "false_negative_rate": self.false_negative_rate,
        "total_detection_time_seconds": self.total_detection_time_seconds,
        "average_detection_time_seconds": (
            self.average_detection_time_seconds
        ),
    }


def _safe_divide(numerator: float, denominator: float) -> float:
  """执行零分母返回 0 的浮点除法。"""
  if denominator == 0:
    return 0.0
  return float(numerator) / float(denominator)
