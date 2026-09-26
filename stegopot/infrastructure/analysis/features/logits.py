"""有限 Top-K logits 特征提取。"""

from collections.abc import Sequence
import math


def top_k_logit_features(logits: Sequence[float], *, top_k: int = 20) -> tuple[float, ...]:
  """返回排序后的 Top-K 值、间隔和归一化概率，避免记录完整词表。"""
  values = tuple(float(item) for item in logits)
  if not values or any(not math.isfinite(item) for item in values):
    raise ValueError("logits 必须是非空有限数序列")
  if top_k < 1:
    raise ValueError("top_k 必须为正数")
  selected = sorted(values, reverse=True)[:top_k]
  maximum = selected[0]
  exponentials = [math.exp(item - maximum) for item in selected]
  total = sum(exponentials)
  probabilities = [item / total for item in exponentials]
  gaps = [selected[0] - item for item in selected]
  return tuple(selected + gaps + probabilities)

