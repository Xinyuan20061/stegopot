"""不绑定 PyTorch 的基础张量干预算子。"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Literal

from stegopot.domain.interface.probe import Probe
from stegopot.domain.model.intervention_runtime import InterventionContext


@dataclass(frozen=True)
class ReplaceOperator:
  """完全使用调用方提供的张量替换当前选择。"""

  replacement: Any = field(
      repr=False, metadata={"description": "用于替换目标选择的张量或标量。"})

  def __call__(self, value: Any, context: InterventionContext) -> Any:
    """返回 replacement；形状和设备由模型适配器校验。"""
    del value, context
    return self.replacement


@dataclass(frozen=True)
class ZeroOperator:
  """把目标张量乘零，供消融或控制实验使用。"""

  def __call__(self, value: Any, context: InterventionContext) -> Any:
    """返回与 value 广播兼容的零值。"""
    del context
    return value * 0


@dataclass(frozen=True)
class ScaleOperator:
  """按有限系数缩放目标张量。"""

  factor: float = field(metadata={"description": "目标张量的有限缩放系数。"})

  def __post_init__(self) -> None:
    if not math.isfinite(float(self.factor)):
      raise ValueError("factor 必须是有限数")
    object.__setattr__(self, "factor", float(self.factor))

  def __call__(self, value: Any, context: InterventionContext) -> Any:
    """返回 factor * value。"""
    del context
    return self.factor * value


@dataclass(frozen=True)
class AddOperator:
  """向目标张量添加调用方提供的增量。"""

  delta: Any = field(
      repr=False, metadata={"description": "添加到目标选择的张量或标量。"})

  def __call__(self, value: Any, context: InterventionContext) -> Any:
    """返回 value + delta。"""
    del context
    return value + self.delta


@dataclass(frozen=True)
class InterpolateOperator:
  """在当前张量和参考张量之间执行线性插值。"""

  source: Any = field(
      repr=False, metadata={"description": "线性插值使用的参考张量。"})
  alpha: float = field(metadata={"description": "参考张量的插值权重。"})

  def __post_init__(self) -> None:
    alpha = float(self.alpha)
    if not math.isfinite(alpha) or not 0.0 <= alpha <= 1.0:
      raise ValueError("alpha 必须位于 [0, 1]")
    object.__setattr__(self, "alpha", alpha)

  def __call__(self, value: Any, context: InterventionContext) -> Any:
    """返回 `(1-alpha)*value + alpha*source`。"""
    del context
    return (1.0 - self.alpha) * value + self.alpha * self.source


@dataclass(frozen=True)
class ProbeThresholdCondition:
  """把任意 Probe 的有限分数转换成条件干预布尔值。"""

  probe: Probe = field(
      repr=False, metadata={"description": "提供在线分数的 Probe 实例。"})
  threshold: float = field(metadata={"description": "触发条件使用的有限阈值。"})
  comparison: Literal["ge", "gt", "le", "lt"] = field(
      default="ge", metadata={"description": "分数与阈值的比较方式。"})

  def __post_init__(self) -> None:
    threshold = float(self.threshold)
    if not math.isfinite(threshold):
      raise ValueError("threshold 必须是有限数")
    if self.comparison not in {"ge", "gt", "le", "lt"}:
      raise ValueError("comparison 不受支持")
    object.__setattr__(self, "threshold", threshold)

  def __call__(self, value: Any, context: InterventionContext) -> bool:
    """调用 Probe.score，不向 Probe 传递完整实验上下文。"""
    del context
    score = float(self.probe.score(value).value)
    return {
        "ge": score >= self.threshold, "gt": score > self.threshold,
        "le": score <= self.threshold, "lt": score < self.threshold,
    }[self.comparison]
