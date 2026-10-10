"""把 EAP 候选边转换为真实 residual edge intervention。"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any

from stegopot.domain.model.attribution import EAPEdge, EAPObservation
from stegopot.domain.model.intervention_runtime import Intervention, InterventionContext


@dataclass(frozen=True)
class EdgeDeltaOperator:
  """在 reader 输入上添加 reference-evaluated writer delta。"""

  delta: Any = field(
      repr=False, metadata={"description": "已分离计算图的 writer counterfactual delta。"})
  alpha: float = field(
      default=1.0, metadata={"description": "应用 delta 的有限缩放系数。"})

  def __post_init__(self) -> None:
    alpha = float(self.alpha)
    if not math.isfinite(alpha) or not 0.0 <= alpha <= 1.0:
      raise ValueError("alpha 必须位于 [0, 1]")
    object.__setattr__(self, "alpha", alpha)

  def __call__(self, value: Any, context: InterventionContext) -> Any:
    """把 delta 移到 reader 的设备和精度后相加。"""
    del context
    moved = self.delta.to(device=value.device, dtype=value.dtype)
    if moved.shape != value.shape:
      raise ValueError(
          f"edge delta 与 reader 选择形状不一致：{tuple(moved.shape)} vs {tuple(value.shape)}")
    return value + self.alpha * moved


def build_edge_patch(
    edge: EAPEdge, observation: EAPObservation, *, alpha: float = 1.0,
    intervention_id: str | None = None,
) -> Intervention:
  """构造把 evaluated edge 推向 reference edge 的真实干预。

  参数：
    edge: 已验证为 residual-additive 的 writer 到 reader 候选边。
    observation: 同一输入位置上的参考运行与求梯度运行。
    alpha: 0 表示不修改，1 表示完整 counterfactual edge patch。
    intervention_id: 可选稳定 ID；默认由 edge_id 和 alpha 生成。

  返回：
    作用于 edge.target 的 Intervention。
  """
  torch = _import_torch()
  reference = observation.reference_trace.get(edge.source).value
  evaluated = observation.evaluated_trace.get(edge.source).value
  if not torch.is_tensor(reference) or not torch.is_tensor(evaluated):
    raise TypeError("edge patch 需要内存中的 PyTorch Tensor activation")
  reference = reference.detach().to(device=evaluated.device, dtype=evaluated.dtype)
  if reference.shape != evaluated.shape:
    raise ValueError("reference 与 evaluated writer activation 形状不一致")
  delta = (reference - evaluated.detach()).clone()
  identifier = intervention_id or f"eap:{edge.edge_id}:alpha={float(alpha):g}"
  return Intervention(
      identifier, edge.target, EdgeDeltaOperator(delta, alpha),
      metadata={"edge_id": edge.edge_id, "alpha": float(alpha),
                "direction": "reference_into_evaluated"})


def _import_torch():
  """惰性加载白盒可选依赖。"""
  try:
    import torch
  except ImportError as exc:
    raise RuntimeError("使用 EAP edge patch 需要安装 PyTorch") from exc
  return torch
