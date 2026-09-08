"""实验信息资产、可见主体和默认拒绝的信息流规则。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import json
import re
from types import MappingProxyType
from typing import Any

ALL_NODES = "all_nodes"
SUBSTRATE = "substrate"
DETECTOR = "detector"
REWARD = "reward"
OUTCOME_REWARD = "outcome_reward"
EVALUATOR = "evaluator"
PUBLIC_AUDIT = "public_audit"
RESEARCH_AUDIT = "research_audit"

COMPONENT_PRINCIPALS = frozenset({
    SUBSTRATE,
    DETECTOR,
    REWARD,
    OUTCOME_REWARD,
    EVALUATOR,
    PUBLIC_AUDIT,
    RESEARCH_AUDIT,
})


def _json_copy(value: Any) -> Any:
  """复制标准 JSON 值并拒绝对象实例与非有限数值。"""
  return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def _validate_id(value: str) -> str:
  """验证信息名称或节点 ID 是安全标识。"""
  if not isinstance(value, str) or not re.fullmatch(
      r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value
  ):
    raise ValueError(f"无效标识：{value!r}")
  return value


class InformationClass(str, Enum):
  """多智能体隐写实验中的标准信息类别。"""

  PUBLIC = "public"
  AGENT_PRIVATE = "agent_private"
  SECRET_PAYLOAD = "secret_payload"
  DECODER_PRIVATE = "decoder_private"
  MONITOR_VISIBLE = "monitor_visible"
  EVALUATOR_ONLY = "evaluator_only"
  RESEARCH_ONLY = "research_only"


_DEFAULT_READERS = {
    InformationClass.PUBLIC: (
        ALL_NODES,
        SUBSTRATE,
        DETECTOR,
        REWARD,
        EVALUATOR,
        OUTCOME_REWARD,
        PUBLIC_AUDIT,
        RESEARCH_AUDIT,
    ),
    InformationClass.MONITOR_VISIBLE: (
        DETECTOR,
        EVALUATOR,
        RESEARCH_AUDIT,
    ),
    InformationClass.EVALUATOR_ONLY: (
        EVALUATOR,
        OUTCOME_REWARD,
        RESEARCH_AUDIT,
    ),
    InformationClass.RESEARCH_ONLY: (RESEARCH_AUDIT,),
}

_ALLOWED_COMPONENT_READERS = {
    InformationClass.PUBLIC: COMPONENT_PRINCIPALS,
    InformationClass.AGENT_PRIVATE: frozenset({EVALUATOR, RESEARCH_AUDIT}),
    InformationClass.SECRET_PAYLOAD: frozenset({EVALUATOR, RESEARCH_AUDIT}),
    InformationClass.DECODER_PRIVATE: frozenset({EVALUATOR, RESEARCH_AUDIT}),
    InformationClass.MONITOR_VISIBLE: frozenset({DETECTOR, EVALUATOR, RESEARCH_AUDIT}),
    InformationClass.EVALUATOR_ONLY: frozenset({EVALUATOR, OUTCOME_REWARD, RESEARCH_AUDIT}),
    InformationClass.RESEARCH_ONLY: frozenset({RESEARCH_AUDIT}),
}


def node_principal(node_id: str) -> str:
  """返回 node_id 对应的标准节点主体名称。

  参数：
    node_id: 当前实验计划中的节点 ID。

  返回：
    形如 ``node:sender`` 的主体名称。
  """
  return "node:" + _validate_id(node_id)


def principal_node_id(principal: str) -> str | None:
  """解析节点主体并返回节点 ID，组件主体返回 None。

  参数：
    principal: 标准组件主体或 ``node:<id>`` 节点主体。

  返回：
    节点 ID；principal 不是节点主体时返回 None。
  """
  if not isinstance(principal, str) or not principal.startswith("node:"):
    return None
  return _validate_id(principal[5:])


@dataclass(frozen=True)
class InformationAsset:
  """带安全类别和显式读取主体的不可变实验信息。

  属性：
    name: 当前 Trial 内唯一的信息名称。
    information_class: 决定可授权主体上限的标准信息类别。
    value: JSON 可序列化的信息值；研究日志可保存，公开投影默认拒绝。
    visible_to: 获准通过宿主接口读取该值的主体列表。
    description: 不包含秘密值的用途说明，用于威胁模型工件。
  """

  name: str
  information_class: InformationClass | str
  value: Any
  visible_to: Sequence[str] = field(default_factory=tuple)
  description: str = ""

  def __post_init__(self) -> None:
    _validate_id(self.name)
    try:
      category = InformationClass(self.information_class)
    except (TypeError, ValueError) as exc:
      raise ValueError(f"未知信息类别：{self.information_class!r}") from exc
    if not isinstance(self.description, str):
      raise TypeError("InformationAsset.description 必须是字符串")
    readers = tuple(self.visible_to) or _DEFAULT_READERS.get(category, ())
    if not readers:
      raise ValueError(f"信息 {self.name} 必须显式声明 visible_to")
    if len(set(readers)) != len(readers):
      raise ValueError(f"信息 {self.name} 的 visible_to 不能重复")
    for principal in readers:
      self._validate_reader(category, principal)
    object.__setattr__(self, "information_class", category)
    object.__setattr__(self, "value", _json_copy(self.value))
    object.__setattr__(self, "visible_to", readers)

  @classmethod
  def from_dict(cls, name: str, value: Mapping[str, Any]) -> "InformationAsset":
    """从严格信息声明创建资产。

    参数：
      name: 信息名称，由外层映射键提供。
      value: 只允许 class、value、visible_to 和 description 的声明。

    返回：
      经过类别与主体约束校验的信息资产。
    """
    if not isinstance(value, Mapping):
      raise TypeError(f"information.{name} 必须是对象")
    data = dict(value)
    unknown = set(data) - {"class", "value", "visible_to", "description"}
    if unknown or "class" not in data or "value" not in data:
      raise ValueError(
          f"information.{name} 必须包含 class/value，且不能包含未知字段"
      )
    return cls(
        name=name,
        information_class=data["class"],
        value=data["value"],
        visible_to=data.get("visible_to", ()),
        description=data.get("description", ""),
    )

  def is_visible_to(self, principal: str) -> bool:
    """判断 principal 是否获准读取当前信息。

    参数：
      principal: 标准组件主体或 ``node:<id>`` 节点主体。

    返回：
      显式授权或 all_nodes 覆盖节点主体时为 True。
    """
    return principal in self.visible_to or (
        principal_node_id(principal) is not None and ALL_NODES in self.visible_to
    )

  def to_dict(self, *, include_value: bool = True) -> dict[str, Any]:
    """返回标准信息声明。

    参数：
      include_value: 是否包含实际值；威胁模型目录只记录摘要时应为 False。

    返回：
      可写入计划或威胁模型工件的 JSON 字典。
    """
    data = {
        "class": self.information_class.value,
        "visible_to": list(self.visible_to),
        "description": self.description,
    }
    if include_value:
      data["value"] = _json_copy(self.value)
    return data

  @staticmethod
  def _validate_reader(category: InformationClass, principal: str) -> None:
    """验证 principal 没有突破 category 的语义上限。"""
    if not isinstance(principal, str) or not principal:
      raise ValueError("信息读取主体必须是非空字符串")
    if principal == ALL_NODES:
      if category is not InformationClass.PUBLIC:
        raise ValueError(f"{category.value} 信息不能授权给 all_nodes")
      return
    node_id = principal_node_id(principal)
    if node_id is not None:
      if category in {
          InformationClass.MONITOR_VISIBLE,
          InformationClass.EVALUATOR_ONLY,
          InformationClass.RESEARCH_ONLY,
      }:
        raise ValueError(f"{category.value} 信息不能授权给普通节点")
      return
    if principal not in COMPONENT_PRINCIPALS:
      raise ValueError(f"未知信息读取主体：{principal}")
    if principal not in _ALLOWED_COMPONENT_READERS[category]:
      raise ValueError(
          f"{category.value} 信息不能授权给组件主体 {principal}"
      )


@dataclass(frozen=True)
class InformationFlowView:
  """一个 Trial 中已编译的信息目录和主体到资产的只读映射。

  属性：
    trial_id: 当前信息流视图对应的 Trial 或 Episode ID。
    assets: 信息名称到不含值的安全声明。
    principal_assets: 主体到可读取信息名称的映射。
    specification_sha256: 含真实值信息声明的规范摘要。
  """

  trial_id: str
  assets: Mapping[str, Mapping[str, Any]]
  principal_assets: Mapping[str, Sequence[str]]
  specification_sha256: str

  def __post_init__(self) -> None:
    _validate_id(self.trial_id)
    if not re.fullmatch(r"[0-9a-f]{64}", self.specification_sha256):
      raise ValueError("信息流声明摘要必须是 SHA-256 十六进制文本")
    object.__setattr__(
        self,
        "assets",
        MappingProxyType({name: MappingProxyType(dict(value)) for name, value in self.assets.items()}),
    )
    object.__setattr__(
        self,
        "principal_assets",
        MappingProxyType({name: tuple(values) for name, values in self.principal_assets.items()}),
    )

  def to_dict(self) -> dict[str, Any]:
    """返回不包含信息值的可封印视图。"""
    return {
        "trial_id": self.trial_id,
        "assets": {name: dict(value) for name, value in self.assets.items()},
        "principal_assets": {
            name: list(values) for name, values in self.principal_assets.items()
        },
        "specification_sha256": self.specification_sha256,
    }
