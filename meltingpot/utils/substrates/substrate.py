"""基础环境基底接口。"""

from __future__ import annotations

import abc
from collections.abc import Mapping, Sequence
import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class StepResult:
  """环境基底重置或前进时返回的结果。

  属性：
    observations: 按玩家位置排列的观察序列。
    rewards: 按玩家位置排列的奖励序列。
    done: 当前回合是否已经结束。
    info: 附加信息，例如事件、日志或调试数据。
  """

  observations: Sequence[Any]
  rewards: Sequence[float] = ()
  done: bool = False
  info: Mapping[str, Any] = dataclasses.field(default_factory=dict)


class Substrate(metaclass=abc.ABCMeta):
  """实验环境的抽象基类。"""

  @abc.abstractmethod
  def reset(self) -> StepResult:
    """开始一个新的回合。

    返回：
      初始步骤结果。
    """
    raise NotImplementedError

  @abc.abstractmethod
  def step(self, actions: Sequence[Any]) -> StepResult:
    """应用每个玩家的动作，并推进环境。

    参数：
      actions: 按玩家位置排列的动作序列。

    返回：
      推进后的步骤结果。
    """
    raise NotImplementedError

  def close(self) -> None:
    """释放环境基底持有的资源。"""

  def __enter__(self):
    return self

  def __exit__(self, *args, **kwargs):
    del args, kwargs
    self.close()
