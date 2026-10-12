"""可复用的 SAE 重构和特征干预算子。"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Literal

from stegopot.domain.interface.sae import SAEModel
from stegopot.domain.model.intervention_runtime import Intervention, InterventionContext
from stegopot.domain.model.reference import TensorRef


@dataclass(frozen=True)
class SAEReconstructionOperator:
  """用 SAE 重构结果替换目标激活，用于测量 SAE 插入效应。"""

  sae: SAEModel = field(
      repr=False, metadata={"description": "执行重构的已加载 SAE。"})

  def __call__(self, value: Any, context: InterventionContext) -> Any:
    """返回保持输入形状、设备和数据类型的重构激活。"""
    del context
    return self.sae.reconstruct(value)


@dataclass(frozen=True)
class SAEFeatureInterventionOperator:
  """在 SAE 特征空间执行无任务语义的通用标量干预。"""

  sae: SAEModel = field(
      repr=False, metadata={"description": "提供编码和解码能力的已加载 SAE。"})
  feature_indices: tuple[int, ...] = field(
      metadata={"description": "需要同时修改的零基 SAE 特征索引。"})
  mode: Literal["zero", "set", "scale", "add"] = field(
      default="zero", metadata={"description": "特征值的修改方式。"})
  value: float = field(
      default=0.0, metadata={"description": "set、scale 或 add 使用的有限标量。"})
  preserve_error: bool = field(
      default=True,
      metadata={"description": "是否保留 SAE 未能重构的原始激活误差。"})

  def __post_init__(self) -> None:
    indices = tuple(self.feature_indices)
    if not indices or any(type(item) is not int or item < 0 for item in indices):
      raise ValueError("feature_indices 必须包含非负整数")
    if len(set(indices)) != len(indices):
      raise ValueError("feature_indices 不能重复")
    if any(item >= self.sae.manifest.feature_width for item in indices):
      raise IndexError("SAE 特征索引超出范围")
    if self.mode not in {"zero", "set", "scale", "add"}:
      raise ValueError("不支持的 SAE 特征干预模式")
    if not math.isfinite(float(self.value)):
      raise ValueError("value 必须是有限数")
    object.__setattr__(self, "feature_indices", indices)
    object.__setattr__(self, "value", float(self.value))

  def __call__(self, activation: Any, context: InterventionContext) -> Any:
    """编码、修改、解码，并按配置保留 SAE 重构误差。"""
    del context
    features = self.sae.encode(activation)
    baseline = self.sae.decode(features)
    modified = features.clone()
    selection = (..., list(self.feature_indices))
    if self.mode == "zero":
      modified[selection] = 0
    elif self.mode == "set":
      modified[selection] = self.value
    elif self.mode == "scale":
      modified[selection] = modified[selection] * self.value
    else:
      modified[selection] = modified[selection] + self.value
    changed = self.sae.decode(modified)
    changed = changed.to(device=activation.device, dtype=activation.dtype)
    if not self.preserve_error:
      return changed
    baseline = baseline.to(device=activation.device, dtype=activation.dtype)
    return activation + (changed - baseline)


def build_sae_feature_intervention(
    *, intervention_id: str, target: TensorRef, sae: SAEModel,
    feature_indices: tuple[int, ...], mode: Literal["zero", "set", "scale", "add"] = "zero",
    value: float = 0.0, preserve_error: bool = True, priority: int = 0,
) -> Intervention:
  """把 SAE 特征操作装配成模型运行时可直接执行的干预。

  参数：
    intervention_id: 当前实验内稳定且唯一的干预 ID。
    target: 基础模型中输入 SAE 的激活位置。
    sae: 已验证与 target 兼容的 SAE。
    feature_indices: 需要修改的零基 SAE 特征索引。
    mode: zero、set、scale 或 add。
    value: 非 zero 模式使用的有限标量。
    preserve_error: 是否保留 SAE 重构误差，隔离选中特征的因果效应。
    priority: 同一目标存在多个干预时的升序执行优先级。
  """
  operator = SAEFeatureInterventionOperator(
      sae=sae, feature_indices=feature_indices, mode=mode, value=value,
      preserve_error=preserve_error)
  return Intervention(
      intervention_id=intervention_id, target=target, operator=operator,
      priority=priority, metadata={
          "operator": "sae_feature", "sae_id": sae.sae_id,
          "feature_indices": list(feature_indices), "mode": mode,
          "value": float(value), "preserve_error": preserve_error,
      })
