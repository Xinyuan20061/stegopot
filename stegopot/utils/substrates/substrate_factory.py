"""用于构建环境基底的工厂。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Callable

from stegopot.utils.substrates import substrate


class SubstrateFactory:
  """某一种环境基底类型的工厂。"""

  def __init__(
      self,
      *,
      builder: Callable[[Sequence[str]], substrate.Substrate],
      valid_roles: Sequence[str],
      default_player_roles: Sequence[str],
      metadata: Mapping[str, Any] | None = None,
  ) -> None:
    """初始化环境基底工厂。

    参数：
      builder: 接收角色序列并返回环境基底实例的构造函数。
      valid_roles: 该环境基底允许出现的角色列表。
      default_player_roles: 默认玩家角色排列。
      metadata: 环境基底元数据，供注册、记录和调试使用。
    """
    self._builder = builder
    self._valid_roles = tuple(valid_roles)
    self._default_player_roles = tuple(default_player_roles)
    self._metadata = dict(metadata or {})

  def valid_roles(self) -> Sequence[str]:
    """返回该环境基底接受的角色。

    返回：
      合法角色列表。
    """
    return self._valid_roles

  def default_player_roles(self) -> Sequence[str]:
    """返回默认角色分配。

    返回：
      默认玩家角色排列。
    """
    return self._default_player_roles

  def metadata(self) -> Mapping[str, Any]:
    """返回环境基底元数据。

    返回：
      环境基底元数据的副本。
    """
    return dict(self._metadata)

  def build(self, roles: Sequence[str]) -> substrate.Substrate:
    """构建环境基底。

    参数：
      roles: 按玩家位置排列的角色列表。

    返回：
      新创建的环境基底实例。
    """
    invalid_roles = set(roles) - set(self._valid_roles)
    if invalid_roles:
      raise ValueError(f"无效角色：{sorted(invalid_roles)!r}")
    return self._builder(tuple(roles))
