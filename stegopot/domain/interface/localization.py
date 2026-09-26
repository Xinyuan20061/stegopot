"""秘密定位器的算法无关协议。"""

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from stegopot.domain.model.localization import DataKind, LocalizerSample


@runtime_checkable
class SecretLocalizer(Protocol):
  """从局部状态估计秘密后验概率，不自行定义主分数。"""

  @property
  def method(self) -> str:
    """返回写入分析报告的方法名称。"""
    ...

  @property
  def supported_data_kinds(self) -> frozenset[DataKind]:
    """返回该定位器明确支持的数据形态。"""
    ...

  def fit(
      self,
      training: Sequence[LocalizerSample],
      validation: Sequence[LocalizerSample],
  ) -> None:
    """只使用训练集拟合；验证集可用于固定超参数但不能变成训练数据。"""
    ...

  def predict_proba(
      self,
      samples: Sequence[LocalizerSample],
  ) -> Sequence[Mapping[str, float]]:
    """按样本顺序返回完整类别概率分布。"""
    ...

  def close(self) -> None:
    """释放定位器持有的计算资源。"""
    ...


class SecretLocalizerFactory(Protocol):
  """为真实分析和每次随机对照创建独立定位器。"""

  def __call__(self) -> SecretLocalizer:
    """返回尚未拟合的新定位器。"""
    ...

