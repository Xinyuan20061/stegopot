"""Tool、Behavior、Timing 和结构化 Memory 的轻量秘密探针。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
import hashlib
import json
import math

from stegopot.domain.model.localization import DataKind, LocalizerSample
from stegopot.infrastructure.analysis.localizers._softmax import RegularizedSoftmax


class StructuredSecretProbe:
  """将固定 JSON 字段展平为哈希特征后拟合线性分类器。"""

  def __init__(
      self, *, dimension: int = 512, l2: float = 0.01,
      learning_rate: float = 0.1, epochs: int = 250,
  ) -> None:
    """初始化结构化探针。

    参数：
      dimension: 稳定哈希特征维度。
      l2: 逻辑回归 L2 正则强度。
      learning_rate: 批量梯度下降学习率。
      epochs: 最大训练轮数。
    """
    if dimension < 16:
      raise ValueError("dimension 不能小于 16")
    self.dimension = dimension
    self._model = RegularizedSoftmax(dimension=dimension, l2=l2,
                                     learning_rate=learning_rate, epochs=epochs)

  @property
  def method(self) -> str:
    """返回稳定方法名。"""
    return "structured_secret_probe"

  @property
  def supported_data_kinds(self) -> frozenset[DataKind]:
    """声明支持 JSON 结构化数据。"""
    return frozenset({DataKind.STRUCTURED, DataKind.NUMERIC_SEQUENCE})

  def fit(self, training: Sequence[LocalizerSample], validation: Sequence[LocalizerSample]) -> None:
    """使用固定字段特征拟合分类器。"""
    self._model.fit([self._features(item.value) for item in training],
                    [item.label for item in training],
                    [self._features(item.value) for item in validation],
                    [item.label for item in validation])

  def predict_proba(self, samples: Sequence[LocalizerSample]):
    """返回秘密类别概率。"""
    return self._model.predict_proba([self._features(item.value) for item in samples])

  def close(self) -> None:
    """纯 Python 探针没有外部资源。"""

  def _features(self, value: object) -> tuple[float, ...]:
    """把嵌套 JSON 转换为字段路径和值特征。"""
    try:
      copied = json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError) as exc:
      raise ValueError("结构化样本必须是有限 JSON 数据") from exc
    categorical: Counter[int] = Counter()
    numeric: Counter[int] = Counter()
    for path, item in _flatten(copied):
      if isinstance(item, bool) or item is None or isinstance(item, str):
        categorical[_bucket(f"{path}={item!r}", self.dimension)] += 1
      elif isinstance(item, (int, float)):
        numeric[_bucket(f"numeric:{path}", self.dimension)] += float(item)
      else:
        categorical[_bucket(f"{path}:{type(item).__name__}", self.dimension)] += 1
    result = [0.0] * self.dimension
    for index, count in categorical.items():
      result[index] += count
    for index, number in numeric.items():
      result[index] += math.copysign(math.log1p(abs(number)), number)
    norm = math.sqrt(sum(item * item for item in result)) or 1.0
    return tuple(item / norm for item in result)


def _flatten(value: object, path: str = "$"):
  """按排序后的字段路径遍历 JSON 值。"""
  if isinstance(value, Mapping):
    for key in sorted(value):
      yield from _flatten(value[key], f"{path}.{key}")
  elif isinstance(value, list):
    for index, item in enumerate(value):
      yield from _flatten(item, f"{path}[{index}]")
  else:
    yield path, value


def _bucket(value: str, dimension: int) -> int:
  """稳定映射结构化字段特征。"""
  return int.from_bytes(hashlib.sha256(value.encode("utf-8")).digest()[:8], "big") % dimension

