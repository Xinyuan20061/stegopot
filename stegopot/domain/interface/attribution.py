"""通用因果归因协议。"""

from typing import Protocol

from stegopot.domain.model.attribution import EAPObservation, EAPResult


class EdgeAttributor(Protocol):
  """把显式配对轨迹映射为候选边评分。"""

  @property
  def attribution_id(self) -> str:
    """返回算法及实现版本 ID。"""
    ...

  def score(self, observation: EAPObservation) -> EAPResult:
    """计算全部显式候选边的 attribution。"""
    ...


__all__ = ["EdgeAttributor"]
