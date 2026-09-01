"""基于公开关键词的轻量确定性检测基线。"""

from __future__ import annotations

from collections.abc import Collection

from stegopot.domain.interface import StegoDetector
from stegopot.domain.model import DetectionRequest
from stegopot.domain.model import DetectionResult


class KeywordStegoDetector(StegoDetector):
  """在公开文本中匹配一个或多个可疑关键词。

  该实现用于验证检测、审计和评估链路，不应被视为真实隐写检测算法。
  """

  def __init__(
      self,
      *,
      keywords: Collection[str],
      case_sensitive: bool = False,
      detector_id: str = "keyword-baseline",
  ) -> None:
    """初始化关键词检测器。

    参数：
      keywords: 任一词语命中时判定消息可疑的非空关键词集合。
      case_sensitive: 是否区分英文大小写。
      detector_id: 写入 DetectionResult 的检测器 ID。
    """
    normalized = tuple(
        keyword.strip()
        for keyword in keywords
        if isinstance(keyword, str) and keyword.strip()
    )
    if not normalized:
      raise ValueError("keywords 至少需要一个非空关键词")
    if not isinstance(detector_id, str) or not detector_id.strip():
      raise ValueError("detector_id 必须是非空字符串")
    self._keywords = normalized
    self._case_sensitive = bool(case_sensitive)
    self._detector_id = detector_id.strip()

  def detect(self, request: DetectionRequest) -> DetectionResult:
    """匹配公开消息中的关键词。

    参数：
      request: 当前公开消息检测请求。

    返回：
      命中关键词时分数为 1，否则为 0 的基线结果。
    """
    content = request.content
    comparable_content = (
        content if self._case_sensitive else content.casefold()
    )
    matched = tuple(
        keyword
        for keyword in self._keywords
        if (
            keyword if self._case_sensitive else keyword.casefold()
        ) in comparable_content
    )
    is_suspicious = bool(matched)
    return DetectionResult(
        message_id=request.message_id,
        detector_id=self._detector_id,
        is_suspicious=is_suspicious,
        score=1.0 if is_suspicious else 0.0,
        confidence=1.0,
        reason=(
            f"命中 {len(matched)} 个预设关键词。"
            if matched else "未命中预设关键词。"
        ),
        metadata={"matched_keywords": list(matched)},
    )
