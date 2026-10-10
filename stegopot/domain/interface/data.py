"""数据生成、变换、验证和保存协议。"""

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Protocol

from stegopot.domain.model.context import ExperimentContext
from stegopot.domain.model.data import DatasetBundle, Sample


class DatasetSource(Protocol):
  """按配置和实验上下文产生通用 Sample。"""

  @property
  def source_id(self) -> str:
    """返回可写入复现清单的数据源 ID/版本。"""
    ...
  def generate(self, count: int, context: ExperimentContext) -> Iterable[Sample]:
    """惰性产生至多 count 个样本。"""
    ...


class DatasetTransform(Protocol):
  """把一个样本转换成零个、一个或多个样本。"""

  @property
  def transform_id(self) -> str:
    """返回转换 ID/版本。"""
    ...

  def apply(self, sample: Sample, context: ExperimentContext) -> Iterable[Sample]:
    """返回转换后的样本序列。"""
    ...


class DatasetValidator(Protocol):
  """在切分前拒绝不满足实验约束的样本。"""

  @property
  def validator_id(self) -> str:
    """返回验证器 ID/版本。"""
    ...

  def validate(self, sample: Sample, context: ExperimentContext) -> Sequence[str]:
    """返回错误说明；空序列表示样本有效。"""
    ...


class DatasetStore(Protocol):
  """保存已验证数据集，不推断 input/target 语义。"""

  def write(self, dataset: DatasetBundle, context: ExperimentContext) -> Mapping[str, Any]:
    """保存 dataset 并返回可审计引用。"""
    ...
