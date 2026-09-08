"""智能体策略接口。"""

from __future__ import annotations

import abc
from typing import Any, Generic, TypeVar

from stegopot.domain.model import AgentAction

State = TypeVar("State")
Observation = Any


class Policy(Generic[State], metaclass=abc.ABCMeta):
  """抽象策略：输入观察和状态，输出动作和下一状态。"""

  @abc.abstractmethod
  def initial_state(self) -> State:
    """返回初始内部状态。

    返回：
      智能体在 Session 开始时使用的不透明状态对象。状态不得持有需要宿主
      关闭的资源；当 Session 允许延续时，宿主会原样传给下一 Episode。
    """
    raise NotImplementedError

  @abc.abstractmethod
  def step(
      self,
      observation: Observation,
      prev_state: State,
  ) -> tuple[AgentAction, State]:
    """返回下一步动作和下一步内部状态。

    参数：
      observation: 当前环境给该智能体的观察。
      prev_state: 该智能体上一步返回的内部状态；同一 Session 的下一
        Episode 也可能把它作为首轮状态传回。

    返回：
      二元组，包含动作和下一步内部状态。状态只能描述策略记忆，不能依赖
      当前 Episode 的 Substrate、收件箱或组件会话生命周期。
    """
    raise NotImplementedError

  def close(self) -> None:
    """释放策略持有的资源。"""

  def __enter__(self):
    return self

  def __exit__(self, *args, **kwargs):
    del args, kwargs
    self.close()
