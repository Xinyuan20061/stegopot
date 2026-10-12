"""独立扩展包的声明、工厂和受限构建上下文。"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Protocol

from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.model.capability import Capability
from stegopot.domain.model.diagnostic import Diagnostic, PreflightContext
from stegopot.domain.model.experiment import validate_id


API_VERSION = "1.6"
COMPONENT_KINDS = frozenset({
    "scenario", "policy", "llm", "model_adapter", "substrate", "channel",
    "codec", "detector", "reward", "outcome_reward", "evaluator", "tool",
    "audit", "dataset", "transform", "validator", "analyzer", "probe",
    "intervention", "metric", "reporter", "protocol", "agent", "sae",
})


def _description(text: str) -> dict[str, str]:
  return {"description": text}


class BuildContext(Protocol):
  """工厂只获得自身声明的资源，不接收全局容器或完整实验真值。"""

  @property
  def node_id(self) -> str | None:
    """返回节点作用域；全局实验组件为 None。"""
    ...

  @property
  def audit(self) -> AuditSink:
    """返回只能追加本插件命名空间事件的审计接口。"""
    ...

  def resource(self, slot: str) -> Any:
    """返回工厂显式声明的资源依赖。"""
    ...

  def credential(self, name: str) -> str:
    """返回授权给当前工厂的单个凭证值。"""
    ...


@dataclass(frozen=True)
class ComponentDefinition:
  """一个可按需创建、可在构造前检查能力的插件组件。"""

  component_id: str = field(metadata=_description("带插件命名空间的稳定组件 ID。"))
  kind: str = field(metadata=_description("宿主支持的标准组件类型。"))
  factory: Callable[[Mapping[str, Any], BuildContext], Any] = field(
      repr=False, metadata=_description("接收已校验配置和受限上下文的工厂。"))
  config_schema: Mapping[str, Any] = field(
      repr=False, metadata=_description("拒绝未知字段的 JSON Schema。"))
  references: Mapping[str, str] = field(
      default_factory=dict,
      metadata=_description("配置字段到依赖组件类型的映射。"))
  credentials: Sequence[str] = field(
      default_factory=tuple,
      metadata=_description("值为环境变量名的凭证配置字段。"))
  preflight: Callable[
      [Mapping[str, Any], PreflightContext], Sequence[Diagnostic]
  ] | None = field(
      default=None, repr=False,
      metadata=_description("不构造资源的可选纯预检函数。"))
  requires_capabilities: Sequence[Capability | str] = field(
      default_factory=tuple,
      metadata=_description("组件运行前要求模型后端提供的能力。"))
  provides_capabilities: Sequence[Capability | str] = field(
      default_factory=tuple,
      metadata=_description("当前组件实例能够提供的模型能力。"))

  def __post_init__(self) -> None:
    validate_id(self.component_id)
    if self.kind not in COMPONENT_KINDS or not callable(self.factory):
      raise ValueError("无效组件类型或工厂")
    references = dict(self.references)
    if set(references.values()) - COMPONENT_KINDS:
      raise ValueError("组件依赖引用了未知组件类型")
    if self.credentials and self.kind not in {"llm", "model_adapter", "tool"}:
      raise ValueError("只有模型、模型适配器或工具可以接收基础设施凭证")
    if self.preflight is not None and not callable(self.preflight):
      raise TypeError("preflight 必须是纯校验函数")
    required = tuple(Capability(item) for item in self.requires_capabilities)
    provided = tuple(Capability(item) for item in self.provides_capabilities)
    if len(set(required)) != len(required) or len(set(provided)) != len(provided):
      raise ValueError("组件能力声明不能重复")
    if provided and self.kind != "model_adapter":
      raise ValueError("只有 model_adapter 可以声明 provides_capabilities")
    object.__setattr__(self, "references", MappingProxyType(references))
    object.__setattr__(self, "credentials", tuple(self.credentials))
    object.__setattr__(self, "requires_capabilities", required)
    object.__setattr__(self, "provides_capabilities", provided)


@dataclass(frozen=True)
class PluginDefinition:
  """一个插件包公开的版本化组件清单。"""

  plugin_id: str = field(metadata=_description("插件命名空间。"))
  version: str = field(metadata=_description("插件发行版本。"))
  api_version: str = field(metadata=_description("插件使用的 StegoPot 接口版本。"))
  components: Sequence[ComponentDefinition] = field(
      metadata=_description("插件公开的组件定义。"))

  def __post_init__(self) -> None:
    validate_id(self.plugin_id)
    components = tuple(self.components)
    if any(not item.component_id.startswith(self.plugin_id + ".") for item in components):
      raise ValueError("组件 ID 必须属于插件自己的命名空间")
    if len({item.component_id for item in components}) != len(components):
      raise ValueError("插件组件 ID 重复")
    object.__setattr__(self, "components", components)
