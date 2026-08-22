"""场景注册表。

场景在环境基底之上定义一次实验条件：角色、焦点/背景智能体，
以及观察可见性。
"""

from __future__ import annotations

from collections.abc import Mapping

from stegopot.utils.scenarios import scenario_factory

SCENARIOS: dict[str, scenario_factory.ScenarioFactory] = {}


def register(name: str, factory: scenario_factory.ScenarioFactory) -> None:
  """注册一个场景工厂。

  参数：
    name: 场景名称，后续通过该名称查找工厂。
    factory: 负责构建该场景的工厂对象。
  """
  if name in SCENARIOS:
    raise ValueError(f"场景已注册：{name!r}")
  SCENARIOS[name] = factory


def get_factory(name: str) -> scenario_factory.ScenarioFactory:
  """返回已注册场景的工厂。

  参数：
    name: 要查找的场景名称。

  返回：
    与名称对应的场景工厂。
  """
  try:
    return SCENARIOS[name]
  except KeyError as exc:
    raise KeyError(f"未知场景：{name!r}") from exc


def list_scenarios() -> Mapping[str, scenario_factory.ScenarioFactory]:
  """返回所有已注册的场景。

  返回：
    场景名称到场景工厂的映射副本。
  """
  return dict(SCENARIOS)
