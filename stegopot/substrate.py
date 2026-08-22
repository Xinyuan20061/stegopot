"""环境基底注册表。

环境基底定义实验中的基础交互规则。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from stegopot.utils.substrates import substrate as substrate_lib
from stegopot.utils.substrates import substrate_factory

SUBSTRATES: dict[str, substrate_factory.SubstrateFactory] = {}


def register(name: str, factory: substrate_factory.SubstrateFactory) -> None:
  """注册一个环境基底工厂。

  参数：
    name: 环境基底名称，后续通过该名称查找工厂。
    factory: 负责构建该环境基底的工厂对象。
  """
  if name in SUBSTRATES:
    raise ValueError(f"环境基底已注册：{name!r}")
  SUBSTRATES[name] = factory


def get_factory(name: str) -> substrate_factory.SubstrateFactory:
  """返回已注册环境基底的工厂。

  参数：
    name: 要查找的环境基底名称。

  返回：
    与名称对应的环境基底工厂。
  """
  try:
    return SUBSTRATES[name]
  except KeyError as exc:
    raise KeyError(f"未知环境基底：{name!r}") from exc


def build(name: str, *, roles: Sequence[str]) -> substrate_lib.Substrate:
  """构建一个已注册的环境基底。

  参数：
    name: 要构建的环境基底名称。
    roles: 按玩家位置排列的角色列表。

  返回：
    构建好的环境基底实例。
  """
  return get_factory(name).build(roles)


def list_substrates() -> Mapping[str, substrate_factory.SubstrateFactory]:
  """返回所有已注册的环境基底。

  返回：
    环境基底名称到环境基底工厂的映射副本。
  """
  return dict(SUBSTRATES)
