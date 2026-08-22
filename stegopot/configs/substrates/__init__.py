"""环境基底配置骨架。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses
from typing import Any


@dataclasses.dataclass(frozen=True)
class SubstrateConfig:
  """基础交互环境的配置。

  属性：
    name: 环境基底配置名称，通常用于注册和引用。
    roles: 该环境基底允许或默认使用的角色列表。
    settings: 环境参数，例如消息长度、可见性和回合数限制。
    description: 环境基底的人类可读说明。
  """

  name: str
  roles: Sequence[str]
  settings: Mapping[str, Any] = dataclasses.field(default_factory=dict)
  description: str = ""


SUBSTRATE_CONFIGS: dict[str, SubstrateConfig] = {}
