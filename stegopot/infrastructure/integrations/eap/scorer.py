"""标准一阶 Edge Attribution Patching 评分器。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from stegopot.domain.model.attribution import (
    EAPEdge,
    EAPObservation,
    EAPResult,
    EAPScore,
)


class EAPAnalyzer:
  """计算 `(evaluated-reference)^T gradient` 并按绝对值排名。"""

  def __init__(
      self, edges: Sequence[EAPEdge], *, reduction: Literal["sum", "mean"] = "sum",
      analyzer_id: str = "core.eap",
  ) -> None:
    """初始化评分器。

    参数：
      edges: 已由模型图适配器定义的 writer 到 reader 候选边。
      reduction: 对逐元素乘积执行求和或求平均。
      analyzer_id: 作为 Research Analyzer 使用时写入记录的稳定 ID。
    """
    values = tuple(edges)
    if not values:
      raise ValueError("EAP 至少需要一条候选边")
    if len({item.edge_id for item in values}) != len(values):
      raise ValueError("EAP 候选 edge_id 不能重复")
    if reduction not in {"sum", "mean"}:
      raise ValueError("reduction 只支持 sum 或 mean")
    if not isinstance(analyzer_id, str) or not analyzer_id.strip():
      raise ValueError("analyzer_id 必须是非空字符串")
    self.edges = values
    self.reduction = reduction
    self._analyzer_id = analyzer_id.strip()

  @property
  def analyzer_id(self) -> str:
    """返回 Research Engine 使用的分析器 ID。"""
    return self._analyzer_id

  @property
  def attribution_id(self) -> str:
    """返回算法及符号约定版本。"""
    return "stegopot.eap/1"

  def analyze(self, sample: Any, output: Any, context: Any) -> EAPResult:
    """从 Scenario 输出的 EAPObservation 计算评分。"""
    del sample, context
    if not isinstance(output, EAPObservation):
      raise TypeError("core.eap analyzer 要求 Scenario 输出 EAPObservation")
    return self.score(output)

  def score(self, observation: EAPObservation) -> EAPResult:
    """计算全部边的一阶 patching disruption 估计。"""
    torch = _import_torch()
    scores = []
    for edge in self.edges:
      reference = observation.reference_trace.get(edge.source).value
      evaluated = observation.evaluated_trace.get(edge.source).value
      gradient = observation.evaluated_trace.get(edge.target).gradient
      if gradient is None:
        raise RuntimeError(f"目标位置尚未获得梯度：{edge.target.key}")
      if not all(torch.is_tensor(item) for item in (reference, evaluated, gradient)):
        raise TypeError("EAP 只能对内存中的 PyTorch Tensor 评分")
      reference = reference.detach().to(device=evaluated.device, dtype=evaluated.dtype)
      gradient = gradient.detach().to(device=evaluated.device, dtype=evaluated.dtype)
      if reference.shape != evaluated.shape or gradient.shape != evaluated.shape:
        raise ValueError(
            f"边 {edge.edge_id} 的 source delta 与 target gradient 形状不一致："
            f"{tuple(evaluated.shape)} vs {tuple(gradient.shape)}")
      product = (evaluated.detach() - reference).float() * gradient.float()
      value = product.sum() if self.reduction == "sum" else product.mean()
      scores.append(EAPScore(edge, float(value.item()), int(product.numel())))
    scores.sort(key=lambda item: (-item.magnitude, item.edge.edge_id))
    return EAPResult(scores, {
        "attribution_id": self.attribution_id,
        "formula": "(evaluated_source-reference_source) dot evaluated_target_gradient",
        "estimated_effect": "evaluated_metric-patched_metric",
        "reduction": self.reduction,
        "edge_count": len(scores),
    })


def _import_torch():
  """惰性加载白盒可选依赖。"""
  try:
    import torch
  except ImportError as exc:
    raise RuntimeError("使用 EAP 需要安装 PyTorch") from exc
  return torch
