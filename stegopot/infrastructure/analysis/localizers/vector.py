"""Activation、KV、Embedding 和 Logit 特征的线性秘密探针。"""

from __future__ import annotations

from collections.abc import Sequence
import math

from stegopot.domain.model.localization import DataKind, LocalizerSample
from stegopot.infrastructure.analysis.localizers._softmax import RegularizedSoftmax


class LinearSecretProbe:
  """标准化向量后使用 L2 正则化多类逻辑回归。"""

  def __init__(
      self, *, l2: float = 0.01, learning_rate: float = 0.1, epochs: int = 250,
  ) -> None:
    """初始化探针。

    参数：
      l2: 权重 L2 正则强度，不能为负。
      learning_rate: 批量梯度下降学习率。
      epochs: 最大训练轮数，验证损失连续不改善时会提前停止。
    """
    self._parameters = dict(l2=l2, learning_rate=learning_rate, epochs=epochs)
    self._mean: tuple[float, ...] = ()
    self._scale: tuple[float, ...] = ()
    self._model: RegularizedSoftmax | None = None

  @property
  def method(self) -> str:
    """返回稳定方法名。"""
    return "linear_secret_probe"

  @property
  def supported_data_kinds(self) -> frozenset[DataKind]:
    """声明仅支持定长向量。"""
    return frozenset({DataKind.VECTOR, DataKind.NUMERIC_SEQUENCE})

  def fit(self, training: Sequence[LocalizerSample], validation: Sequence[LocalizerSample]) -> None:
    """从训练 split 计算标准化参数并拟合正则化线性模型。"""
    vectors = tuple(_vector(item.value) for item in training)
    if not vectors or len({len(item) for item in vectors}) != 1:
      raise ValueError("LinearSecretProbe 需要非空等长向量")
    dimension = len(vectors[0])
    self._mean = tuple(sum(row[index] for row in vectors) / len(vectors)
                       for index in range(dimension))
    variance = tuple(sum((row[index] - self._mean[index]) ** 2 for row in vectors) / len(vectors)
                     for index in range(dimension))
    self._scale = tuple(math.sqrt(value) if value > 1e-12 else 1.0 for value in variance)
    self._model = RegularizedSoftmax(dimension=dimension, **self._parameters)
    self._model.fit(
        [self._transform(row) for row in vectors], [item.label for item in training],
        [self._transform(_vector(item.value)) for item in validation],
        [item.label for item in validation],
    )

  def predict_proba(self, samples: Sequence[LocalizerSample]):
    """返回样本的秘密类别后验概率。"""
    if self._model is None:
      raise RuntimeError("LinearSecretProbe 尚未拟合")
    return self._model.predict_proba([self._transform(_vector(item.value)) for item in samples])

  def close(self) -> None:
    """释放模型参数引用。"""
    self._model = None

  def _transform(self, value: Sequence[float]) -> tuple[float, ...]:
    """使用训练 split 的统计量标准化向量。"""
    if len(value) != len(self._mean):
      raise ValueError("向量维度与训练数据不一致")
    return tuple((item - mean) / scale
                 for item, mean, scale in zip(value, self._mean, self._scale, strict=True))


def _vector(value: object) -> tuple[float, ...]:
  """严格解析有限数值向量。"""
  if not isinstance(value, (list, tuple)) or not value:
    raise TypeError("向量观测必须是非空 list/tuple")
  result = tuple(float(item) for item in value)
  if any(not math.isfinite(item) for item in result):
    raise ValueError("向量不能包含非有限数")
  return result

