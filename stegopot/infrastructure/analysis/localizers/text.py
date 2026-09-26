"""公开 Token/Text、CoT 和文本 Memory 的 n-gram 秘密探针。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
import hashlib
import math
import re

from stegopot.domain.model.localization import DataKind, LocalizerSample
from stegopot.infrastructure.analysis.localizers._softmax import RegularizedSoftmax


class TextSecretProbe:
  """使用确定性哈希字符/词 n-gram 和正则化逻辑回归。"""

  def __init__(
      self, *, dimension: int = 1024, char_min: int = 2, char_max: int = 4,
      token_min: int = 1, token_max: int = 2, l2: float = 0.01,
      learning_rate: float = 0.15, epochs: int = 250,
  ) -> None:
    """初始化文本探针。

    参数：
      dimension: 哈希特征维度。
      char_min: 最短字符 n-gram 长度。
      char_max: 最长字符 n-gram 长度。
      token_min: 最短 token n-gram 长度。
      token_max: 最长 token n-gram 长度。
      l2: 逻辑回归 L2 正则强度。
      learning_rate: 批量梯度下降学习率。
      epochs: 最大训练轮数。
    """
    if dimension < 16 or not 1 <= char_min <= char_max or not 1 <= token_min <= token_max:
      raise ValueError("TextSecretProbe n-gram 或维度参数无效")
    self.dimension = dimension
    self.char_range = (char_min, char_max)
    self.token_range = (token_min, token_max)
    self._model = RegularizedSoftmax(dimension=dimension, l2=l2,
                                     learning_rate=learning_rate, epochs=epochs)

  @property
  def method(self) -> str:
    """返回稳定方法名。"""
    return "text_ngram_secret_probe"

  @property
  def supported_data_kinds(self) -> frozenset[DataKind]:
    """声明支持文本和离散序列。"""
    return frozenset({DataKind.TEXT, DataKind.CATEGORICAL_SEQUENCE})

  def fit(self, training: Sequence[LocalizerSample], validation: Sequence[LocalizerSample]) -> None:
    """在固定 n-gram 特征上拟合线性分类器。"""
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
    """提取归一化哈希 n-gram，不使用 Python 随机 hash。"""
    if not isinstance(value, str):
      raise TypeError("TextSecretProbe 的样本值必须是字符串")
    normalized = " ".join(value.lower().split())
    tokens = re.findall(r"\w+|[^\w\s]", normalized, flags=re.UNICODE)
    counts: Counter[int] = Counter()
    for size in range(self.char_range[0], self.char_range[1] + 1):
      counts.update(_bucket(f"c:{normalized[index:index + size]}", self.dimension)
                    for index in range(max(0, len(normalized) - size + 1)))
    for size in range(self.token_range[0], self.token_range[1] + 1):
      counts.update(_bucket(f"t:{' '.join(tokens[index:index + size])}", self.dimension)
                    for index in range(max(0, len(tokens) - size + 1)))
    norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
    result = [0.0] * self.dimension
    for index, count in counts.items():
      result[index] = count / norm
    return tuple(result)


def _bucket(value: str, dimension: int) -> int:
  """将文本特征稳定映射到定长桶。"""
  digest = hashlib.sha256(value.encode("utf-8")).digest()
  return int.from_bytes(digest[:8], "big") % dimension

