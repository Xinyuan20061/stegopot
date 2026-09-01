"""公开文本隐写检测器的稳定扩展接口。"""

from __future__ import annotations

import abc

from stegopot.domain.model import DetectionRequest
from stegopot.domain.model import DetectionResult


class StegoDetector(metaclass=abc.ABCMeta):
  """把公开消息转换为隐写风险判定的抽象接口。"""

  def reset(self) -> None:
    """开始一次新实验前清理检测器内部状态。"""

  @abc.abstractmethod
  def detect(self, request: DetectionRequest) -> DetectionResult:
    """检测一条公开消息。

    参数：
      request: 不包含秘密比特和安全材料的公开检测请求。

    返回：
      与 request.message_id 对应的风险分数和二分类判定。
    """
    raise NotImplementedError

  def close(self) -> None:
    """释放检测器持有的模型、连接或其他资源。"""
