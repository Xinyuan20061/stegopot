"""智能体策略接口。"""

from __future__ import annotations

import abc
from typing import Any, Generic, TypeVar

State = TypeVar("State")
Action = Any
Observation = Any


class Policy(Generic[State], metaclass=abc.ABCMeta):
  """抽象策略：输入观察和状态，输出动作和下一状态。"""

  @abc.abstractmethod
  def initial_state(self) -> State:
    """返回初始内部状态。

    返回：
      智能体在回合开始时使用的状态对象。
    """
    raise NotImplementedError

  @abc.abstractmethod
  def step(
      self,
      observation: Observation,
      prev_state: State,
  ) -> tuple[Action, State]:
    """返回下一步动作和下一步内部状态。

    参数：
      observation: 当前环境给该智能体的观察。
      prev_state: 该智能体上一步返回的内部状态。

    返回：
      二元组，包含动作和下一步内部状态。
    """
    raise NotImplementedError

  def close(self) -> None:
    """释放策略持有的资源。"""

  def __enter__(self):
    return self

  def __exit__(self, *args, **kwargs):
    del args, kwargs
    self.close()
