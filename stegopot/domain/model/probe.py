"""Probe 输入位置、数据样本和评分的通用对象。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal

from stegopot.domain.model.reference import TensorRef


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass(frozen=True)
class ProbeInputSpec:
  """定义 Probe 从哪一层表示以及如何池化。"""

  ref: TensorRef = field(metadata=_description("Probe 使用的内部张量位置。"))
  pooling: Literal["none", "last_token", "mean_tokens", "flatten"] = field(
      default="last_token", metadata=_description("把激活转换为 Probe 特征的池化方式。"))

  def __post_init__(self) -> None:
    if self.pooling not in {"none", "last_token", "mean_tokens", "flatten"}:
      raise ValueError("不支持的 Probe pooling")


@dataclass(frozen=True)
class ProbeExample:
  """一个激活特征与中央标签组成的 Probe 样本。"""

  sample_id: str = field(metadata=_description("来源实验样本 ID。"))
  features: Any = field(repr=False, metadata=_description("池化后的表示；框架不假设向量库。"))
  label: Any = field(repr=False, metadata=_description("只在 Probe 数据边界可见的中央标签。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("轨迹、层和数据切分来源。"))

  def __post_init__(self) -> None:
    if not self.sample_id:
      raise ValueError("sample_id 不能为空")
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

@dataclass(frozen=True)
class ProbeDataset:
  """同一 TensorRef 和池化规则下的 Probe 数据集。"""

  input_spec: ProbeInputSpec = field(metadata=_description("全部样本共享的表示选择规则。"))
  examples: Sequence[ProbeExample] = field(metadata=_description("Probe 训练或评价样本。"))
  split: str = field(default="unspecified", metadata=_description("train、validation、test 或自定义切分名。"))

  def __post_init__(self) -> None:
    examples = tuple(self.examples)
    if not examples or len({item.sample_id for item in examples}) != len(examples):
      raise ValueError("ProbeDataset 需要非空且 sample_id 唯一的样本")
    if not self.split:
      raise ValueError("split 不能为空")
    object.__setattr__(self, "examples", examples)


@dataclass(frozen=True)
class ProbeScore:
  """在线或离线 Probe 的标准化输出。"""

  value: float = field(metadata=_description("由 Probe 定义语义的有限分数。"))
  prediction: Any | None = field(default=None, metadata=_description("可选预测类别或结构。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("阈值、模型版本和校准信息。"))

  def __post_init__(self) -> None:
    import math
    value = float(self.value)
    if not math.isfinite(value):
      raise ValueError("ProbeScore.value 必须是有限数")
    object.__setattr__(self, "value", value)
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
