"""场景骨架。"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any, TypeVar

from meltingpot.utils.scenarios import population
from meltingpot.utils.substrates import substrate as substrate_lib

T = TypeVar("T")


def restrict_observation(
    observation: Mapping[str, T],
    permitted_observations: Collection[str],
) -> Mapping[str, T]:
  """把单个观察限制到允许的字段。

  参数：
    observation: 原始观察映射。
    permitted_observations: 允许暴露的观察字段名称集合。

  返回：
    只包含允许字段的新观察映射。
  """
  return {
      key: value
      for key, value in observation.items()
      if key in permitted_observations
  }


def partition(
    values: Sequence[T],
    is_focal: Sequence[bool],
) -> tuple[Sequence[T], Sequence[T]]:
  """把一组值分成焦点组和背景组。

  参数：
    values: 需要拆分的值序列。
    is_focal: 与 values 对齐的布尔序列；True 表示焦点组。

  返回：
    二元组，第一项是焦点组，第二项是背景组。
  """
  focal_values = []
  background_values = []
  for focal, value in zip(is_focal, values):
    if focal:
      focal_values.append(value)
    else:
      background_values.append(value)
  return tuple(focal_values), tuple(background_values)


def merge(
    focal_values: Sequence[T],
    background_values: Sequence[T],
    is_focal: Sequence[bool],
) -> Sequence[T]:
  """把焦点组和背景组按角色顺序合并回来。

  参数：
    focal_values: 焦点组值序列。
    background_values: 背景组值序列。
    is_focal: 输出位置标记；True 时从焦点组取值，否则从背景组取值。

  返回：
    按原始角色顺序排列的合并结果。
  """
  focal_iter = iter(focal_values)
  background_iter = iter(background_values)
  return tuple(
      next(focal_iter if focal else background_iter) for focal in is_focal
  )


class Scenario:
  """一个环境基底与可选背景智能体群体的组合。"""

  def __init__(
      self,
      *,
      substrate: substrate_lib.Substrate,
      background_population: population.Population | None,
      is_focal: Sequence[bool],
      permitted_observations: Collection[str],
      metadata: Mapping[str, Any] | None = None,
  ) -> None:
    """初始化场景。

    参数：
      substrate: 当前场景包装的环境基底。
      background_population: 背景智能体群体；没有背景智能体时为空。
      is_focal: 按玩家位置排列的焦点标记。
      permitted_observations: 允许焦点智能体看到的观察字段。
      metadata: 场景级元数据，供记录和扩展使用。
    """
    self.substrate = substrate
    self.background_population = background_population
    self.is_focal = tuple(is_focal)
    self.permitted_observations = frozenset(permitted_observations)
    self.metadata = dict(metadata or {})

  def close(self) -> None:
    """关闭场景持有的资源。"""
    if self.background_population is not None:
      self.background_population.close()
    self.substrate.close()

  def __enter__(self):
    return self

  def __exit__(self, *args, **kwargs):
    del args, kwargs
    self.close()
