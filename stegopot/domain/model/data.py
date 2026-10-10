"""通用实验样本、切分策略和数据集工件。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass(frozen=True)
class Sample:
  """不预设秘密、标签或任务类型的通用实验样本。"""

  sample_id: str = field(metadata=_description("样本稳定 ID。"))
  input: Any = field(repr=False, metadata=_description("交给 Scenario 的输入对象。"))
  target: Any | None = field(
      default=None, repr=False, metadata=_description("可选中央目标；不会自动暴露给模型。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("数据版本、分组和来源等非敏感元数据。"))

  def __post_init__(self) -> None:
    if not isinstance(self.sample_id, str) or not self.sample_id.strip():
      raise ValueError("sample_id 必须是非空字符串")
    object.__setattr__(self, "sample_id", self.sample_id.strip())
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class SplitPolicy:
  """确定性数据集切分参数。"""

  train_ratio: float = field(default=0.7, metadata=_description("训练集比例。"))
  validation_ratio: float = field(default=0.15, metadata=_description("验证集比例。"))
  test_ratio: float = field(default=0.15, metadata=_description("测试集比例。"))
  seed: int = field(default=0, metadata=_description("确定性打乱种子。"))
  group_key: str | None = field(
      default=None, metadata=_description("可选 metadata 分组键，同组样本不得跨切分。"))

  def __post_init__(self) -> None:
    ratios = tuple(float(item) for item in (
        self.train_ratio, self.validation_ratio, self.test_ratio))
    if any(not math.isfinite(item) or item < 0 for item in ratios):
      raise ValueError("切分比例必须是非负有限数")
    if not math.isclose(sum(ratios), 1.0, abs_tol=1e-9):
      raise ValueError("训练、验证和测试比例之和必须为 1")
    if self.group_key is not None and not self.group_key.strip():
      raise ValueError("group_key 不能是空字符串")
    object.__setattr__(self, "train_ratio", ratios[0])
    object.__setattr__(self, "validation_ratio", ratios[1])
    object.__setattr__(self, "test_ratio", ratios[2])


@dataclass(frozen=True)
class DatasetBundle:
  """通过生成、变换、验证和切分后的不可变数据集。"""

  dataset_id: str = field(metadata=_description("内容和流水线派生的数据集 ID。"))
  train: Sequence[Sample] = field(metadata=_description("训练样本。"))
  validation: Sequence[Sample] = field(metadata=_description("验证样本。"))
  test: Sequence[Sample] = field(metadata=_description("测试样本。"))
  fingerprint: str = field(metadata=_description("样本 ID、流水线和切分参数摘要。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("来源插件和数据版本等复现信息。"))

  def __post_init__(self) -> None:
    if not self.dataset_id or len(self.fingerprint) != 64:
      raise ValueError("dataset_id 不能为空且 fingerprint 必须为 SHA-256")
    partitions = (tuple(self.train), tuple(self.validation), tuple(self.test))
    identifiers = [item.sample_id for group in partitions for item in group]
    if len(set(identifiers)) != len(identifiers):
      raise ValueError("DatasetBundle 的样本不能跨切分重复")
    object.__setattr__(self, "train", partitions[0])
    object.__setattr__(self, "validation", partitions[1])
    object.__setattr__(self, "test", partitions[2])
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  @property
  def samples(self) -> tuple[Sample, ...]:
    """按 train、validation、test 顺序返回全部样本。"""
    return (*self.train, *self.validation, *self.test)
