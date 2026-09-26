"""在完全相同协议下比较两张因果路径图。"""

from collections import defaultdict
import math

from stegopot.domain.model.attribution import CausalPathGraph, PathMigrationReport


def compare_path_graphs(
    before: CausalPathGraph,
    after: CausalPathGraph,
) -> PathMigrationReport:
  """验证协议一致后计算表面贡献变化与 Jensen-Shannon 距离。"""
  if before.protocol_fingerprint != after.protocol_fingerprint:
    raise ValueError("两张路径图的协议指纹不同，不能解释为路径迁移")
  before_raw = _surface_contributions(before)
  after_raw = _surface_contributions(after)
  keys = sorted(set(before_raw) | set(after_raw))
  before_distribution = _normalize(before_raw, keys)
  after_distribution = _normalize(after_raw, keys)
  midpoint = {key: (before_distribution[key] + after_distribution[key]) / 2 for key in keys}
  divergence = (_kl(before_distribution, midpoint) + _kl(after_distribution, midpoint)) / 2
  distance = min(1.0, math.sqrt(max(0.0, divergence)))
  deltas = {key: after_raw.get(key, 0.0) - before_raw.get(key, 0.0) for key in keys}
  return PathMigrationReport(
      before.analysis_id, after.analysis_id, before.protocol_fingerprint,
      distance, before_distribution, after_distribution, deltas)


def _surface_contributions(graph: CausalPathGraph) -> dict[str, float]:
  """按表面汇总有干预证据的节点因果贡献。"""
  grouped = defaultdict(float)
  for item in graph.nodes:
    if item.causal_score is not None:
      grouped[item.address.surface.value] += item.causal_score
  if not grouped:
    raise ValueError("路径图没有可比较的 causal_score")
  return dict(grouped)


def _normalize(values: dict[str, float], keys: list[str]) -> dict[str, float]:
  """将非负表面贡献归一化为概率分布。"""
  total = sum(values.values())
  if total <= 0:
    raise ValueError("表面因果贡献总和必须大于 0")
  return {key: values.get(key, 0.0) / total for key in keys}


def _kl(left: dict[str, float], right: dict[str, float]) -> float:
  """使用以 2 为底的 KL 散度，使 JS 距离位于 [0, 1]。"""
  return sum(value * math.log2(value / right[key])
             for key, value in left.items() if value > 0)

