"""用于协调多个策略的智能体群体骨架。"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
import random
from typing import Any

from meltingpot.utils.policies import policy as policy_lib


class Population:
  """按角色填充、并在每个回合中采样的一组策略。"""

  def __init__(
      self,
      *,
      policies: Mapping[str, policy_lib.Policy],
      names_by_role: Mapping[str, Collection[str]],
      roles: Sequence[str],
  ) -> None:
    """初始化智能体群体。

    参数：
      policies: 策略名称到策略实例的映射。
      names_by_role: 角色到可用策略名称集合的映射。
      roles: 按玩家位置排列的角色列表。
    """
    self._policies = dict(policies)
    self._names_by_role = {
        role: tuple(names) for role, names in names_by_role.items()
    }
    self._roles = tuple(roles)
    self._names: tuple[str, ...] = ()
    self._states: list[Any] = []
    self._pending_observations: Sequence[Any] | None = None

  def close(self) -> None:
    """关闭智能体群体持有的所有策略。"""
    for policy in self._policies.values():
      policy.close()

  def reset(self) -> None:
    """为当前角色采样策略，并重置它们的状态。"""
    self._names = tuple(
        random.choice(self._names_by_role[role]) for role in self._roles
    )
    self._states = [
        self._policies[name].initial_state() for name in self._names
    ]
    self._pending_observations = None

  def names(self) -> Sequence[str]:
    """返回当前回合中采样到的策略名称。

    返回：
      按玩家位置排列的策略名称。
    """
    return self._names

  def step(self, observations: Sequence[Any]) -> Sequence[Any]:
    """让所有已采样的策略前进一步。

    参数：
      observations: 按玩家位置排列的观察序列。

    返回：
      按玩家位置排列的动作序列。
    """
    if not self._names:
      self.reset()
    if len(observations) != len(self._names):
      raise ValueError("观察数量必须与智能体群体规模一致")
    actions = []
    for index, (name, observation) in enumerate(zip(self._names, observations)):
      action, next_state = self._policies[name].step(
          observation=observation,
          prev_state=self._states[index],
      )
      self._states[index] = next_state
      actions.append(action)
    return tuple(actions)

  def send_timestep(self, observations: Sequence[Any]) -> None:
    """保存观察，供后续 await_action 调用使用。

    参数：
      observations: 按玩家位置排列的观察序列。
    """
    if self._pending_observations is not None:
      raise RuntimeError("上一个时间步尚未被消费")
    self._pending_observations = tuple(observations)

  def await_action(self) -> Sequence[Any]:
    """消费待处理观察，并返回动作。

    返回：
      按玩家位置排列的动作序列。
    """
    if self._pending_observations is None:
      raise RuntimeError("尚未发送时间步")
    observations = self._pending_observations
    self._pending_observations = None
    return self.step(observations)

  def __enter__(self):
    return self

  def __exit__(self, *args, **kwargs):
    del args, kwargs
    self.close()
