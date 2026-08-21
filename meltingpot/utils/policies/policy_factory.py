"""用于构建智能体策略的工厂。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Callable

from meltingpot.utils.policies import policy


class PolicyFactory:
  """为某一种策略类型创建实例的工厂。"""

  def __init__(
      self,
      *,
      builder: Callable[[], policy.Policy],
      observation_spec: Mapping[str, Any] | None = None,
      action_spec: Mapping[str, Any] | None = None,
      metadata: Mapping[str, Any] | None = None,
  ) -> None:
    """初始化策略工厂。

    参数：
      builder: 无参构造函数，用于创建策略实例。
      observation_spec: 策略期望观察结构的元数据。
      action_spec: 策略输出动作结构的元数据。
      metadata: 工厂级元数据，供注册、记录和调试使用。
    """
    self._builder = builder
    self._observation_spec = dict(observation_spec or {})
    self._action_spec = dict(action_spec or {})
    self._metadata = dict(metadata or {})

  def observation_spec(self) -> Mapping[str, Any]:
    """返回期望观察结构的元数据。

    返回：
      观察结构元数据的副本。
    """
    return dict(self._observation_spec)

  def action_spec(self) -> Mapping[str, Any]:
    """返回动作结构的元数据。

    返回：
      动作结构元数据的副本。
    """
    return dict(self._action_spec)

  def metadata(self) -> Mapping[str, Any]:
    """返回工厂元数据。

    返回：
      工厂元数据的副本。
    """
    return dict(self._metadata)

  def build(self) -> policy.Policy:
    """构建一个策略实例。

    返回：
      新创建的策略实例。
    """
    return self._builder()
