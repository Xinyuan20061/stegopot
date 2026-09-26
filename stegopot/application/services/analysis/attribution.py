"""从显著定位候选和反事实结果构建研究级因果路径图。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib

from stegopot.domain.model.attribution import (
    CausalPathEdge,
    CausalPathGraph,
    CausalPathNode,
    InterventionResult,
    InterventionSpec,
)
from stegopot.domain.model.localization import LocalizationMap, ObservationAddress


def causal_contribution(
    baseline_recovery: float,
    intervened_recovery: float,
    chance_recovery: float,
) -> float:
  """计算 M(Z)=clip((R0-Ri)/(R0-Rchance), 0, 1)。"""
  values = (float(baseline_recovery), float(intervened_recovery), float(chance_recovery))
  if any(not 0.0 <= value <= 1.0 for value in values):
    raise ValueError("恢复率必须位于 [0, 1]")
  denominator = values[0] - values[2]
  if denominator <= 0:
    raise ValueError("baseline_recovery 必须高于 chance_recovery")
  return min(1.0, max(0.0, (values[0] - values[1]) / denominator))


def intervention_result(
    spec: InterventionSpec,
    *,
    baseline_recovery: float,
    intervened_recovery: float,
    chance_recovery: float,
) -> InterventionResult:
  """构造保留原始基线的统一干预结果。"""
  score = causal_contribution(baseline_recovery, intervened_recovery, chance_recovery)
  return InterventionResult(spec, baseline_recovery, intervened_recovery,
                            chance_recovery, score)


def build_path_graph(
    localization: LocalizationMap,
    interventions: Sequence[InterventionResult],
) -> CausalPathGraph:
  """只把通过 null test 的定位单元提升为因果候选。"""
  by_address = {item.spec.target.key: item for item in interventions}
  if len(by_address) != len(interventions):
    raise ValueError("同一定位地址不能声明多个未区分的干预结果")
  candidates = [item for item in localization.units if item.significant]
  candidate_keys = {item.unit.key for item in candidates}
  unknown = set(by_address) - candidate_keys
  if unknown:
    raise ValueError("干预只能针对通过 null test 的定位候选")
  nodes = []
  for item in candidates:
    evidence = by_address.get(item.unit.key)
    digest = hashlib.sha256(item.unit.key.encode("utf-8")).hexdigest()[:12]
    nodes.append(CausalPathNode(
        node_id=f"{item.unit.surface.value}.{digest}",
        address=item.unit,
        localization_score=item.metrics.score,
        causal_score=evidence.causal_score if evidence else None,
        significant=True,
        intervention_id=evidence.spec.intervention_id if evidence else None,
    ))
  nodes.sort(key=lambda item: (item.address.surface.value, item.address.agent_id or "",
                               item.node_id))
  causal_nodes = [item for item in nodes if item.causal_score is not None]
  ordered = [item for item in causal_nodes
             if isinstance(item.address.address.get("flow_order"), (int, float))]
  ordered.sort(key=lambda item: float(item.address.address["flow_order"]))
  edges = tuple(CausalPathEdge(source.node_id, target.node_id, "preregistered_flow_order")
                for source, target in zip(ordered, ordered[1:]))
  return CausalPathGraph(localization.analysis_id, localization.protocol_fingerprint,
                         tuple(nodes), edges, tuple(interventions))


def parse_interventions(
    records: Sequence[Mapping[str, object]],
) -> tuple[InterventionResult, ...]:
  """从离线重跑结果解析干预证据，不接受缺失 baseline 的记录。"""
  results = []
  for record in records:
    target = ObservationAddress.from_dict(record["target"])
    spec = InterventionSpec(
        intervention_id=str(record["intervention_id"]), target=target,
        method=str(record["method"]), source_sample_id=str(record["source_sample_id"]),
        donor_sample_id=(str(record["donor_sample_id"])
                         if record.get("donor_sample_id") is not None else None),
        metadata=record.get("metadata", {}),
    )
    results.append(intervention_result(
        spec,
        baseline_recovery=float(record["baseline_recovery"]),
        intervened_recovery=float(record["intervened_recovery"]),
        chance_recovery=float(record["chance_recovery"]),
    ))
  return tuple(results)
