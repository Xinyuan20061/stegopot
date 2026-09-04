"""不改变内部策略的定轮次调用适配器。"""

from typing import Any

from stegopot.domain.interface.policy import Policy
from stegopot.domain.model.action import AgentAction


class RoundPolicy(Policy):
  """仅在一个明确轮次调用内部策略，其余轮次返回等待动作。"""

  def __init__(self, inner: Policy, *, active_round: int) -> None:
    """设置 inner 被调用的 active_round，轮次从零开始。"""
    if active_round < 0:
      raise ValueError("active_round 不能为负数")
    self._inner = inner
    self._active_round = active_round

  def initial_state(self) -> Any:
    """返回内部策略的初始状态。"""
    return self._inner.initial_state()

  def step(self, observation: Any, prev_state: Any) -> tuple[AgentAction, Any]:
    """根据 observation 的轮次决定执行或等待；prev_state 原样传递。"""
    if observation["round_index"] != self._active_round:
      return AgentAction.wait(), prev_state
    return self._inner.step(observation, prev_state)

  def close(self) -> None:
    """释放内部策略拥有的资源。"""
    self._inner.close()


class FixedActionPolicy(Policy):
  """返回固定动作，仅用于明确标注的对照重放，不冒充模型生成。"""

  def __init__(self, action: AgentAction) -> None:
    """保存待重放的 action；调用者负责用 RoundPolicy 限制执行轮次。"""
    self._action = action

  def initial_state(self) -> None:
    """固定动作不持有历史状态。"""
    return None

  def step(self, observation: Any, prev_state: Any) -> tuple[AgentAction, None]:
    """忽略 observation 和 prev_state，返回预先记录的动作。"""
    return self._action, None
