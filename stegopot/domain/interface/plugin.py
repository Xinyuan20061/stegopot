"""独立扩展包的声明、工厂和受限构建上下文。"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.model.experiment import validate_id
from stegopot.domain.model.diagnostic import Diagnostic, PreflightContext


API_VERSION = "1.1"
COMPONENT_KINDS = frozenset({"scenario", "policy", "llm", "substrate", "channel",
                             "codec", "detector", "reward", "evaluator", "audit"})


class BuildContext(Protocol):
  """工厂只获得自身声明的资源，不接收全局容器或完整实验真值。"""

  @property
  def node_id(self) -> str | None:
    """当前策略或注入资源所属节点；无节点作用域时为 None。"""
    ...

  @property
  def audit(self) -> AuditSink:
    """只能追加本插件命名空间事件的研究审计接口。"""
    ...

  def resource(self, slot: str) -> Any:
    """返回工厂声明的 slot 资源；未声明引用必须拒绝。"""
    ...

  def credential(self, name: str) -> str:
    """返回已授权给本工厂的 name 凭证；不提供整个环境变量字典。"""
    ...


@dataclass(frozen=True)
class ComponentDefinition:
  """一个按需创建的能力组件。

  属性：
    component_id: 带插件命名空间的唯一 ID，例如 demo.policy。
    kind: 标准能力类型，不以任意字符串扩张执行权限。
    factory: 接收已校验 config 和受限 BuildContext 的构造函数。
    config_schema: JSON Schema 2020-12 参数定义，必须拒绝未知字段。
    references: 配置字段到依赖能力类型的映射，资源按槽位注入。
    credentials: 可用作凭证引用的配置字段，值仅能是环境变量名称。
    preflight: 可选纯校验函数，接收配置和局部上下文，返回诊断；不得构造资源或访问网络。
  """

  component_id: str
  kind: str
  factory: Callable[[Mapping[str, Any], BuildContext], Any]
  config_schema: Mapping[str, Any]
  references: Mapping[str, str] = field(default_factory=dict)
  credentials: Sequence[str] = ()
  preflight: Callable[[Mapping[str, Any], PreflightContext], Sequence[Diagnostic]] | None = None

  def __post_init__(self) -> None:
    validate_id(self.component_id)
    if self.kind not in COMPONENT_KINDS or not callable(self.factory):
      raise ValueError("无效组件类型或工厂")
    if set(self.references.values()) - {"llm", "codec"}:
      raise ValueError("组件依赖只能引用显式声明的 llm/codec 资源")
    if self.credentials and self.kind != "llm":
      raise ValueError("只有模型供应商工厂可以接收基础设施凭证")
    if self.preflight is not None and not callable(self.preflight):
      raise TypeError("preflight 必须是纯校验函数")


@dataclass(frozen=True)
class PluginDefinition:
  """插件声明。plugin_id 为命名空间，version 为包版本，api_version 为契约版本，components 为工厂列表。"""

  plugin_id: str
  version: str
  api_version: str
  components: Sequence[ComponentDefinition]

  def __post_init__(self) -> None:
    validate_id(self.plugin_id)
    if any(not item.component_id.startswith(self.plugin_id + ".") for item in self.components):
      raise ValueError("组件 ID 必须属于插件自己的命名空间")
    if len({item.component_id for item in self.components}) != len(self.components):
      raise ValueError("插件组件 ID 重复")
    object.__setattr__(self, "components", tuple(self.components))
