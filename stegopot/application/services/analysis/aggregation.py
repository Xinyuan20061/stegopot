"""地址级定位结果的表面聚合。"""

from collections import defaultdict
from collections.abc import Sequence

from stegopot.domain.model.localization import LocalizationResult, SurfaceSummary


def aggregate_surfaces(
    results: Sequence[LocalizationResult], *, top_k: int,
) -> tuple[SurfaceSummary, ...]:
  """按预注册 Top-K 平均聚合表面，保留峰值、显著占比和单元数。"""
  if top_k < 1:
    raise ValueError("top_k 必须为正数")
  grouped = defaultdict(list)
  for item in results:
    grouped[item.unit.surface].append(item)
  summaries = []
  for surface, units in sorted(grouped.items(), key=lambda item: item[0].value):
    scores = sorted((item.metrics.score for item in units), reverse=True)
    selected = scores[:top_k]
    summaries.append(SurfaceSummary(
        surface=surface,
        peak_score=scores[0],
        top_k_mean=sum(selected) / len(selected),
        significant_unit_ratio=sum(item.significant for item in units) / len(units),
        unit_count=len(units),
        top_k=top_k,
    ))
  return tuple(summaries)

