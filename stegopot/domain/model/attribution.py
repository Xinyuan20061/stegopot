"""因果干预、研究级路径图和路径迁移领域对象。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any

from stegopot.domain.model.localization import ObservationAddress, SurfaceKind


def _description(text: str) -> dict[str, str]:
  return {"description": text}


def _probability(value: float, name: str) -> float:
  number = float(value)
  if not math.isfinite(number) or not 0.0 <= number <= 1.0:
    raise ValueError(f"{name} 必须位于 [0, 1]")
  return number


@dataclass(frozen=True)
class InterventionSpec:
  """一次预注册反事实干预。"""

  intervention_id: str = field(metadata=_description("干预唯一 ID。"))
  target: ObservationAddress = field(metadata=_description("被干预的候选地址。"))
  method: str = field(metadata=_description("干预方法，例如 matched_activation_patch。"))
  source_sample_id: str = field(metadata=_description("保留上下文的源样本 ID。"))
  donor_sample_id: str | None = field(default=None,
                                       metadata=_description("秘密不匹配但上下文匹配的供体样本 ID。"))
  metadata: Mapping[str, Any] = field(default_factory=dict,
                                      metadata=_description("不含秘密值的干预参数。"))

  def __post_init__(self) -> None:
    for name in ("intervention_id", "method", "source_sample_id"):
      value = getattr(self, name)
      if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")
      object.__setattr__(self, name, value.strip())
    if self.donor_sample_id is not None and not self.donor_sample_id.strip():
      raise ValueError("donor_sample_id 不能为空字符串")
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  def to_dict(self) -> dict[str, Any]:
    """返回标准干预声明。"""
    return {"intervention_id": self.intervention_id, "target": self.target.to_dict(),
            "method": self.method, "source_sample_id": self.source_sample_id,
            "donor_sample_id": self.donor_sample_id, "metadata": dict(self.metadata)}


@dataclass(frozen=True)
class InterventionResult:
  """保留原始基线的因果干预结果。"""

  spec: InterventionSpec = field(metadata=_description("对应的预注册干预。"))
  baseline_recovery: float = field(metadata=_description("未干预时的秘密恢复率。"))
  intervened_recovery: float = field(metadata=_description("干预后的秘密恢复率。"))
  chance_recovery: float = field(metadata=_description("随机猜测恢复率。"))
  causal_score: float = field(metadata=_description("统一因果贡献 M(Z)。"))

  def __post_init__(self) -> None:
    for name in ("baseline_recovery", "intervened_recovery", "chance_recovery",
                 "causal_score"):
      object.__setattr__(self, name, _probability(getattr(self, name), name))

  def to_dict(self) -> dict[str, Any]:
    """返回标准干预结果。"""
    return {"spec": self.spec.to_dict(), "baseline_recovery": self.baseline_recovery,
            "intervened_recovery": self.intervened_recovery,
            "chance_recovery": self.chance_recovery, "causal_score": self.causal_score}


@dataclass(frozen=True)
class CausalPathNode:
  """跨表面因果传播图中的一个研究节点。"""

  node_id: str = field(metadata=_description("由稳定地址派生的节点 ID。"))
  address: ObservationAddress = field(metadata=_description("被定位和干预的地址。"))
  localization_score: float = field(metadata=_description("秘密可恢复分数 L(Z)。"))
  causal_score: float | None = field(metadata=_description("因果贡献 M(Z)，未干预时为空。"))
  significant: bool = field(metadata=_description("是否通过 null test。"))
  intervention_id: str | None = field(default=None,
                                      metadata=_description("产生 causal_score 的干预 ID。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "localization_score",
                       _probability(self.localization_score, "localization_score"))
    if self.causal_score is not None:
      object.__setattr__(self, "causal_score", _probability(self.causal_score, "causal_score"))

  def to_dict(self) -> dict[str, Any]:
    """返回路径节点。"""
    return {"id": self.node_id, "surface": self.address.surface.value,
            "agent": self.address.agent_id, "address": dict(self.address.address),
            "localization_score": self.localization_score,
            "causal_score": self.causal_score, "significant": self.significant,
            "intervention_id": self.intervention_id}


@dataclass(frozen=True)
class CausalPathEdge:
  """路径节点之间的有向研究关系，不声称恢复神经网络完整电路。"""

  source: str = field(metadata=_description("起点节点 ID。"))
  target: str = field(metadata=_description("终点节点 ID。"))
  relation: str = field(default="protocol_order",
                        metadata=_description("边的证据类型。"))

  def to_dict(self) -> dict[str, str]:
    """返回路径边。"""
    return {"source": self.source, "target": self.target, "relation": self.relation}


@dataclass(frozen=True)
class CausalPathGraph:
  """跨 Agent、跨隐写面的研究级秘密传播图。"""

  analysis_id: str = field(metadata=_description("来源定位分析 ID。"))
  protocol_fingerprint: str = field(metadata=_description("可比分析协议指纹。"))
  nodes: Sequence[CausalPathNode] = field(metadata=_description("定位与干预节点。"))
  edges: Sequence[CausalPathEdge] = field(metadata=_description("预注册顺序关系。"))
  interventions: Sequence[InterventionResult] = field(
      default_factory=tuple, metadata=_description("完整反事实干预证据。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "nodes", tuple(self.nodes))
    object.__setattr__(self, "edges", tuple(self.edges))
    object.__setattr__(self, "interventions", tuple(self.interventions))
    identifiers = {item.node_id for item in self.nodes}
    if len(identifiers) != len(self.nodes):
      raise ValueError("路径节点 ID 不能重复")
    if any(edge.source not in identifiers or edge.target not in identifiers for edge in self.edges):
      raise ValueError("路径边必须引用已声明节点")

  def to_dict(self) -> dict[str, Any]:
    """返回可写入 path.json 的标准结构。"""
    return {"schema_version": "stegopot.path/1", "analysis_id": self.analysis_id,
            "protocol_fingerprint": self.protocol_fingerprint,
            "nodes": [item.to_dict() for item in self.nodes],
            "edges": [item.to_dict() for item in self.edges],
            "interventions": [item.to_dict() for item in self.interventions],
            "scope": "cross-surface research graph; not a complete neural circuit"}

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "CausalPathGraph":
    """从 path.json 恢复路径图；干预明细保留在原 JSON 中，不重复构造。"""
    if value.get("schema_version") != "stegopot.path/1":
      raise ValueError("不支持的 CausalPathGraph schema")
    nodes = [CausalPathNode(
        item["id"], ObservationAddress(SurfaceKind(item["surface"]), item.get("agent"),
                                       item.get("address", {})),
        item["localization_score"], item.get("causal_score"),
        bool(item["significant"]), item.get("intervention_id"))
             for item in value.get("nodes", ())]
    edges = [CausalPathEdge(item["source"], item["target"], item.get("relation", "protocol_order"))
             for item in value.get("edges", ())]
    return cls(value["analysis_id"], value["protocol_fingerprint"], nodes, edges, ())


@dataclass(frozen=True)
class PathMigrationReport:
  """同一协议下两张路径图的表面级迁移结果。"""

  before_analysis_id: str = field(metadata=_description("迁移前分析 ID。"))
  after_analysis_id: str = field(metadata=_description("迁移后分析 ID。"))
  protocol_fingerprint: str = field(metadata=_description("两侧共同协议指纹。"))
  js_distance: float = field(metadata=_description("归一化贡献向量的 Jensen-Shannon 距离。"))
  before_distribution: Mapping[str, float] = field(metadata=_description("迁移前表面贡献分布。"))
  after_distribution: Mapping[str, float] = field(metadata=_description("迁移后表面贡献分布。"))
  causal_deltas: Mapping[str, float] = field(metadata=_description("各表面因果贡献变化。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "js_distance", _probability(self.js_distance, "js_distance"))
    object.__setattr__(self, "before_distribution", MappingProxyType(dict(self.before_distribution)))
    object.__setattr__(self, "after_distribution", MappingProxyType(dict(self.after_distribution)))
    object.__setattr__(self, "causal_deltas", MappingProxyType(dict(self.causal_deltas)))

  def to_dict(self) -> dict[str, Any]:
    """返回可写入 migration.json 的标准结构。"""
    return {"schema_version": "stegopot.migration/1",
            "before_analysis_id": self.before_analysis_id,
            "after_analysis_id": self.after_analysis_id,
            "protocol_fingerprint": self.protocol_fingerprint,
            "js_distance": self.js_distance,
            "before_distribution": dict(self.before_distribution),
            "after_distribution": dict(self.after_distribution),
            "causal_deltas": dict(self.causal_deltas)}

