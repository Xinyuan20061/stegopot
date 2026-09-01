"""用于离线测试的可预测隐写检测器。"""

from __future__ import annotations

from collections.abc import Mapping

from stegopot.domain.interface import StegoDetector
from stegopot.domain.model import DetectionRequest
from stegopot.domain.model import DetectionResult


class MockStegoDetector(StegoDetector):
  """根据消息 ID 的预设分数返回确定性检测结果。"""

  def __init__(
      self,
      *,
      scores: Mapping[str, float] | None = None,
      default_score: float = 0.0,
      threshold: float = 0.5,
      detector_id: str = "mock-detector",
  ) -> None:
    """初始化 Mock 检测器。

    参数：
      scores: 消息 ID 到风险分数的映射。
      default_score: 未在 scores 中出现的消息使用的风险分数。
      threshold: 风险分数达到该值时判定为可疑。
      detector_id: 写入 DetectionResult 的检测器 ID。
    """
    self._scores = {
        str(message_id): self._validate_score(score)
        for message_id, score in (scores or {}).items()
    }
    self._default_score = self._validate_score(default_score)
    self._threshold = self._validate_score(threshold)
    if not isinstance(detector_id, str) or not detector_id.strip():
      raise ValueError("detector_id 必须是非空字符串")
    self._detector_id = detector_id.strip()
    self.requests: list[DetectionRequest] = []

  def reset(self) -> None:
    """清空上一轮实验保存的检测请求。"""
    self.requests.clear()

  def detect(self, request: DetectionRequest) -> DetectionResult:
    """按消息 ID 查找预设风险分数。

    参数：
      request: 当前公开消息检测请求。

    返回：
      由预设分数和 threshold 产生的确定性结果。
    """
    self.requests.append(request)
    score = self._scores.get(request.message_id, self._default_score)
    is_suspicious = score >= self._threshold
    return DetectionResult(
        message_id=request.message_id,
        detector_id=self._detector_id,
        is_suspicious=is_suspicious,
        score=score,
        confidence=1.0,
        reason="Mock 检测器按预设分数判定。",
    )

  @staticmethod
  def _validate_score(value: float) -> float:
    """验证并返回 0 到 1 范围内的分数。"""
    score = float(value)
    if not 0.0 <= score <= 1.0:
      raise ValueError("检测分数和阈值必须位于 [0, 1] 区间")
    return score
