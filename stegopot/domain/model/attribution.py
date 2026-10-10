"""与任务语义无关的 Edge Attribution Patching 领域对象。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any

from stegopot.domain.model.reference import TensorRef
from stegopot.domain.model.trace import ActivationTrace


def _description(text: str) -> dict[str, str]:
  """返回统一的字段说明。"""
  return {"description": text}


@dataclass(frozen=True)
class EAPEdge:
  """一个由 writer activation 指向 reader input 的显式候选边。"""

  edge_id: str = field(metadata=_description("当前计算图内稳定且唯一的边 ID。"))
  source: TensorRef = field(metadata=_description("提供 activation difference 的 writer 位置。"))
  target: TensorRef = field(metadata=_description("提供 metric gradient 的 reader 输入位置。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict,
      metadata=_description("层、组件和图定义版本等不含张量的说明。"))

  def __post_init__(self) -> None:
    edge_id = self.edge_id.strip() if isinstance(self.edge_id, str) else ""
    if not edge_id:
      raise ValueError("EAPEdge.edge_id 必须是非空字符串")
    if self.source.key == self.target.key:
      raise ValueError("EAP edge 的 source 与 target 不能是同一 TensorRef")
    object.__setattr__(self, "edge_id", edge_id)
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  def to_dict(self) -> dict[str, Any]:
    """返回可写入配置或实验清单的结构。"""
    return {
        "edge_id": self.edge_id,
        "source": self.source.to_dict(),
        "target": self.target.to_dict(),
        "metadata": dict(self.metadata),
    }


@dataclass(frozen=True)
class EAPObservation:
  """EAP 一阶近似需要的参考运行与求梯度运行。"""

  reference_trace: ActivationTrace = field(
      repr=False, metadata=_description("提供参考 writer activation 的轨迹。"))
  evaluated_trace: ActivationTrace = field(
      repr=False, metadata=_description("提供当前 writer activation 和 reader gradient 的轨迹。"))
  reference_metric: float = field(metadata=_description("参考运行的任务标量。"))
  evaluated_metric: float = field(metadata=_description("求梯度运行的任务标量。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict,
      metadata=_description("配对 ID、方向和图版本等不含张量的信息。"))

  def __post_init__(self) -> None:
    reference_metric = float(self.reference_metric)
    evaluated_metric = float(self.evaluated_metric)
    if not math.isfinite(reference_metric) or not math.isfinite(evaluated_metric):
      raise ValueError("EAPObservation metric 必须是有限数")
    if self.reference_trace.model_id != self.evaluated_trace.model_id:
      raise ValueError("EAP 配对轨迹必须来自同一模型")
    object.__setattr__(self, "reference_metric", reference_metric)
    object.__setattr__(self, "evaluated_metric", evaluated_metric)
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  def to_manifest(self) -> dict[str, Any]:
    """返回不包含 activation 原值的审计清单。"""
    return {
        "schema_version": "stegopot.eap-observation/1",
        "reference_metric": self.reference_metric,
        "evaluated_metric": self.evaluated_metric,
        "reference_trace": self.reference_trace.to_manifest(),
        "evaluated_trace": self.evaluated_trace.to_manifest(),
        "metadata": dict(self.metadata),
    }


@dataclass(frozen=True)
class EAPScore:
  """一个候选边的一阶 counterfactual patching 估计。"""

  edge: EAPEdge = field(metadata=_description("被评分的显式候选边。"))
  score: float = field(
      metadata=_description("(evaluated-reference) 与 evaluated gradient 的内积。"))
  element_count: int = field(metadata=_description("参与内积的张量元素数量。"))

  def __post_init__(self) -> None:
    score = float(self.score)
    if not math.isfinite(score):
      raise ValueError("EAPScore.score 必须是有限数")
    if type(self.element_count) is not int or self.element_count < 1:
      raise ValueError("EAPScore.element_count 必须是正整数")
    object.__setattr__(self, "score", score)

  @property
  def magnitude(self) -> float:
    """返回用于默认排名的 attribution 绝对值。"""
    return abs(self.score)

  def to_dict(self) -> dict[str, Any]:
    """返回不含张量的标准评分记录。"""
    return {
        "edge": self.edge.to_dict(),
        "score": self.score,
        "magnitude": self.magnitude,
        "element_count": self.element_count,
    }


@dataclass(frozen=True)
class EAPResult:
  """按 attribution 绝对值降序排列的完整 EAP 结果。"""

  scores: Sequence[EAPScore] = field(metadata=_description("全部候选边的有序评分。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict,
      metadata=_description("公式方向、归约方式和算法版本。"))

  def __post_init__(self) -> None:
    scores = tuple(self.scores)
    identifiers = [item.edge.edge_id for item in scores]
    if len(set(identifiers)) != len(identifiers):
      raise ValueError("EAPResult 中的 edge_id 不能重复")
    if any(scores[index].magnitude < scores[index + 1].magnitude
           for index in range(len(scores) - 1)):
      raise ValueError("EAPResult.scores 必须按 magnitude 降序排列")
    object.__setattr__(self, "scores", scores)
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  def top(self, count: int) -> tuple[EAPScore, ...]:
    """返回前 count 个评分；count 必须为正整数。"""
    if type(count) is not int or count < 1:
      raise ValueError("count 必须是正整数")
    return tuple(self.scores[:count])

  def get(self, edge_id: str) -> EAPScore:
    """按 edge_id 返回唯一评分。"""
    for item in self.scores:
      if item.edge.edge_id == edge_id:
        return item
    raise KeyError(edge_id)

  def to_manifest(self) -> dict[str, Any]:
    """返回可审计、可复算且不包含张量原值的结果。"""
    return {
        "schema_version": "stegopot.eap-result/1",
        "scores": [item.to_dict() for item in self.scores],
        "metadata": dict(self.metadata),
    }
