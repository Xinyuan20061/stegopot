"""用于构建场景的工厂。"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import Any

from stegopot.utils.policies import policy_factory
from stegopot.utils.scenarios import population
from stegopot.utils.scenarios import scenario
from stegopot.utils.substrates import substrate_factory


class ScenarioFactory:
  """根据环境基底和策略工厂构建场景。"""

  def __init__(
      self,
      *,
      substrate: substrate_factory.SubstrateFactory,
      policies: Mapping[str, policy_factory.PolicyFactory] | None = None,
      names_by_role: Mapping[str, Collection[str]] | None = None,
      roles: Sequence[str],
      is_focal: Sequence[bool],
      permitted_observations: Collection[str],
      metadata: Mapping[str, Any] | None = None,
  ) -> None:
    """初始化场景工厂。

    参数：
      substrate: 用于构建环境基底的工厂。
      policies: 背景策略名称到策略工厂的映射。
      names_by_role: 背景角色到可采样策略名称集合的映射。
      roles: 按玩家位置排列的角色列表。
      is_focal: 按玩家位置排列的焦点标记。
      permitted_observations: 允许焦点智能体看到的观察字段。
      metadata: 场景级元数据，供记录和扩展使用。
    """
    if len(roles) != len(is_focal):
      raise ValueError("roles and is_focal must be the same length")
    self._substrate = substrate
    self._policies = dict(policies or {})
    self._names_by_role = {
        role: tuple(names) for role, names in (names_by_role or {}).items()
    }
    self._roles = tuple(roles)
    self._is_focal = tuple(is_focal)
    self._permitted_observations = frozenset(permitted_observations)
    self._metadata = dict(metadata or {})

  def focal_player_roles(self) -> Sequence[str]:
    """返回分配给焦点玩家的角色。

    返回：
      按焦点玩家位置排列的角色列表。
    """
    return tuple(
        role for role, focal in zip(self._roles, self._is_focal) if focal
    )

  def build(self) -> scenario.Scenario:
    """构建场景外壳。

    返回：
      新创建的场景实例。
    """
    background_roles = tuple(
        role for role, focal in zip(self._roles, self._is_focal) if not focal
    )
    background_population = None
    if background_roles:
      background_population = population.Population(
          policies={
              name: factory.build()
              for name, factory in self._policies.items()
          },
          names_by_role=self._names_by_role,
          roles=background_roles,
      )
    return scenario.Scenario(
        substrate=self._substrate.build(self._roles),
        background_population=background_population,
        is_focal=self._is_focal,
        permitted_observations=self._permitted_observations,
        metadata=self._metadata,
    )
