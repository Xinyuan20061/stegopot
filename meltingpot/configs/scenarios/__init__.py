"""场景配置骨架。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses


@dataclasses.dataclass(frozen=True)
class ScenarioConfig:
  """单个实验场景的配置。

  属性：
    name: 场景配置名称，通常用于注册和引用。
    substrate: 该场景使用的环境基底名称。
    roles: 按玩家位置排列的角色列表。
    focal_agents: 该场景中被重点评估的智能体名称。
    background_agents: 用于填充背景角色的智能体名称。
    observation_visibility: 各角色或智能体可见的观察字段。
    tags: 场景标签，用于筛选和分组实验。
    description: 场景的人类可读说明。
  """

  name: str
  substrate: str
  roles: Sequence[str]
  focal_agents: Sequence[str]
  background_agents: Sequence[str] = ()
  observation_visibility: Mapping[str, Sequence[str]] = dataclasses.field(
      default_factory=dict
  )
  tags: frozenset[str] = frozenset()
  description: str = ""


SCENARIO_CONFIGS: dict[str, ScenarioConfig] = {}
