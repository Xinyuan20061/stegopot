"""无外部依赖的正则化多类线性模型，供内置探针复用。"""

from __future__ import annotations

from collections.abc import Sequence
import math


class RegularizedSoftmax:
  """使用批量梯度下降拟合的轻量多类逻辑回归。"""

  def __init__(self, *, dimension: int, l2: float, learning_rate: float, epochs: int) -> None:
    """保存固定超参数；模型不执行隐式调参或联网。"""
    if dimension < 1 or l2 < 0 or learning_rate <= 0 or epochs < 1:
      raise ValueError("线性模型超参数无效")
    self.dimension = dimension
    self.l2 = float(l2)
    self.learning_rate = float(learning_rate)
    self.epochs = int(epochs)
    self.classes: tuple[str, ...] = ()
    self._weights: list[list[float]] = []
    self._bias: list[float] = []

  def fit(
      self,
      features: Sequence[Sequence[float]],
      labels: Sequence[str],
      validation_features: Sequence[Sequence[float]] = (),
      validation_labels: Sequence[str] = (),
  ) -> None:
    """拟合固定维度特征；验证集只用于保留最佳轮次参数。"""
    if not features or len(features) != len(labels):
      raise ValueError("训练特征和标签必须非空且等长")
    self.classes = tuple(sorted(set(labels)))
    if len(self.classes) < 2:
      raise ValueError("线性探针至少需要两个秘密类别")
    if any(len(row) != self.dimension for row in features):
      raise ValueError("训练特征维度不一致")
    if validation_features and (len(validation_features) != len(validation_labels)
                                or any(len(row) != self.dimension for row in validation_features)):
      raise ValueError("验证特征或标签无效")
    class_index = {label: index for index, label in enumerate(self.classes)}
    self._weights = [[0.0] * self.dimension for _ in self.classes]
    self._bias = [0.0] * len(self.classes)
    best_loss = math.inf
    best_parameters = None
    stale = 0
    for _ in range(self.epochs):
      gradient = [[0.0] * self.dimension for _ in self.classes]
      bias_gradient = [0.0] * len(self.classes)
      for row, label in zip(features, labels, strict=True):
        probabilities = self._predict_row(row)
        expected = class_index[label]
        for class_id, probability in enumerate(probabilities):
          error = probability - (1.0 if class_id == expected else 0.0)
          bias_gradient[class_id] += error
          target = gradient[class_id]
          for index, value in enumerate(row):
            if value:
              target[index] += error * value
      scale = 1.0 / len(features)
      for class_id, weights in enumerate(self._weights):
        for index in range(self.dimension):
          regularized = gradient[class_id][index] * scale + self.l2 * weights[index]
          weights[index] -= self.learning_rate * regularized
        self._bias[class_id] -= self.learning_rate * bias_gradient[class_id] * scale
      if validation_features:
        loss = self.loss(validation_features, validation_labels)
        if loss + 1e-8 < best_loss:
          best_loss = loss
          best_parameters = ([row[:] for row in self._weights], self._bias[:])
          stale = 0
        else:
          stale += 1
          if stale >= 25:
            break
    if best_parameters is not None:
      self._weights, self._bias = best_parameters

  def predict_proba(self, features: Sequence[Sequence[float]]) -> tuple[dict[str, float], ...]:
    """返回每个样本的完整类别概率。"""
    if not self.classes:
      raise RuntimeError("线性模型尚未拟合")
    if any(len(row) != self.dimension for row in features):
      raise ValueError("预测特征维度不一致")
    return tuple({label: probability for label, probability in zip(self.classes,
                                                                    self._predict_row(row), strict=True)}
                 for row in features)

  def loss(self, features: Sequence[Sequence[float]], labels: Sequence[str]) -> float:
    """计算给定数据的平均交叉熵。"""
    distributions = self.predict_proba(features)
    return sum(-math.log(max(item[label], 1e-12))
               for item, label in zip(distributions, labels, strict=True)) / len(labels)

  def _predict_row(self, row: Sequence[float]) -> list[float]:
    """对单个定长向量执行稳定 softmax。"""
    logits = [self._bias[class_id] + sum(weight * value
              for weight, value in zip(weights, row, strict=True) if value)
              for class_id, weights in enumerate(self._weights)]
    maximum = max(logits)
    exponentials = [math.exp(value - maximum) for value in logits]
    total = sum(exponentials)
    return [value / total for value in exponentials]

