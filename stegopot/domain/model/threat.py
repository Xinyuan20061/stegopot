"""多智能体隐写实验的威胁模型声明与执行清单。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import re
from types import MappingProxyType
from typing import Any


TRUSTED_IN_PROCESS = "trusted_in_process"
PUBLIC_AUDIT_PROFILE = "minimal"
RESEARCH_AUDIT_PROFILE = "complete"


def _require_bool(value: Any, name: str) -> bool:
  """验证 value 是严格布尔值，避免把 0/1 当成权限声明。"""
  if type(value) is not bool:
    raise TypeError(f"{name} 必须是布尔值")
  return value


def _strict_mapping(
    value: Mapping[str, Any] | None,
    *,
    allowed: set[str],
    name: str,
) -> dict[str, Any]:
  """复制 value 并拒绝未知字段，保证 Python API 与配置文件同样严格。"""
  if value is None:
    return {}
  if not isinstance(value, Mapping):
    raise TypeError(f"{name} 必须是映射")
  data = dict(value)
  unknown = set(data) - allowed
  if unknown:
    raise ValueError(f"{name} 包含未知字段：{sorted(unknown)}")
  return data


@dataclass(frozen=True)
class PolicyViewSpec:
  """策略观察的可选扩展。

  属性：
    public_channel_history: 是否向所有策略公开此前已经实际投递的消息历史。
      默认关闭；节点仍会通过 inbox 读取发给自己的消息。
  """

  public_channel_history: bool = False

  def __post_init__(self) -> None:
    _require_bool(self.public_channel_history, "policy_view.public_channel_history")

  @classmethod
  def from_dict(cls, value: Mapping[str, Any] | None) -> "PolicyViewSpec":
    """从经过模式校验的 value 构造策略视图声明。"""
    data = _strict_mapping(
        value,
        allowed={"public_channel_history"},
        name="policy_view",
    )
    return cls(public_channel_history=data.get("public_channel_history", False))

  def to_dict(self) -> dict[str, bool]:
    """返回可写入实验工件的标准字典。"""
    return {"public_channel_history": self.public_channel_history}


@dataclass(frozen=True)
class DetectorViewSpec:
  """检测器请求的可选扩展。

  属性：
    public_experiment_context: 是否向检测器提供任务、节点、拓扑和
      shared_context。默认关闭，检测器只读取最终投递消息。
  """

  public_experiment_context: bool = False

  def __post_init__(self) -> None:
    _require_bool(
        self.public_experiment_context,
        "detector_view.public_experiment_context",
    )

  @classmethod
  def from_dict(cls, value: Mapping[str, Any] | None) -> "DetectorViewSpec":
    """从经过模式校验的 value 构造检测器视图声明。"""
    data = _strict_mapping(
        value,
        allowed={"public_experiment_context"},
        name="detector_view",
    )
    return cls(
        public_experiment_context=data.get(
            "public_experiment_context",
            False,
        )
    )

  def to_dict(self) -> dict[str, bool]:
    """返回可写入实验工件的标准字典。"""
    return {
        "public_experiment_context": self.public_experiment_context,
    }


@dataclass(frozen=True)
class AuditViewSpec:
  """宿主审计视图声明。

  属性：
    public_profile: 公开日志使用的白名单投影版本；当前只支持 minimal。
    research_profile: 研究日志使用的证据范围；当前只支持 complete。
  """

  public_profile: str = PUBLIC_AUDIT_PROFILE
  research_profile: str = RESEARCH_AUDIT_PROFILE

  def __post_init__(self) -> None:
    if self.public_profile != PUBLIC_AUDIT_PROFILE:
      raise ValueError("audit.public_profile 当前只支持 minimal")
    if self.research_profile != RESEARCH_AUDIT_PROFILE:
      raise ValueError("audit.research_profile 当前只支持 complete")

  @classmethod
  def from_dict(cls, value: Mapping[str, Any] | None) -> "AuditViewSpec":
    """从经过模式校验的 value 构造审计视图声明。"""
    data = _strict_mapping(
        value,
        allowed={"public_profile", "research_profile"},
        name="audit",
    )
    return cls(
        public_profile=data.get("public_profile", PUBLIC_AUDIT_PROFILE),
        research_profile=data.get(
            "research_profile",
            RESEARCH_AUDIT_PROFILE,
        ),
    )

  def to_dict(self) -> dict[str, str]:
    """返回可写入实验工件的标准字典。"""
    return {
        "public_profile": self.public_profile,
        "research_profile": self.research_profile,
    }


@dataclass(frozen=True)
class ThreatModelSpec:
  """用户声明的实验威胁模型。

  属性：
    trust_model: 插件信任方式。当前仅支持 trusted_in_process，表示组件
      遵守宿主接口，但没有操作系统级进程隔离。
    policy_view: 策略观察的可选公开信息范围。
    detector_view: 检测器请求的可选公开上下文范围。
    audit: 公开与研究审计使用的固定投影配置。
  """

  trust_model: str = TRUSTED_IN_PROCESS
  policy_view: PolicyViewSpec = field(default_factory=PolicyViewSpec)
  detector_view: DetectorViewSpec = field(default_factory=DetectorViewSpec)
  audit: AuditViewSpec = field(default_factory=AuditViewSpec)

  def __post_init__(self) -> None:
    if self.trust_model != TRUSTED_IN_PROCESS:
      raise ValueError("当前版本只支持 trusted_in_process 信任模型")

  @classmethod
  def from_dict(cls, value: Mapping[str, Any] | None) -> "ThreatModelSpec":
    """从配置 value 构造威胁模型，不接受未实现的安全保证。"""
    data = _strict_mapping(
        value,
        allowed={"trust_model", "policy_view", "detector_view", "audit"},
        name="threat_model",
    )
    return cls(
        trust_model=data.get("trust_model", TRUSTED_IN_PROCESS),
        policy_view=PolicyViewSpec.from_dict(data.get("policy_view")),
        detector_view=DetectorViewSpec.from_dict(data.get("detector_view")),
        audit=AuditViewSpec.from_dict(data.get("audit")),
    )

  def to_dict(self) -> dict[str, Any]:
    """返回配置层可序列化的威胁模型声明。"""
    return {
        "trust_model": self.trust_model,
        "policy_view": self.policy_view.to_dict(),
        "detector_view": self.detector_view.to_dict(),
        "audit": self.audit.to_dict(),
    }


@dataclass(frozen=True)
class ThreatModelManifest:
  """框架编译并在运行前冻结的有效威胁模型。

  属性：
    schema_version: 威胁模型工件格式版本。
    trust_model: 本次运行实际采用的插件信任方式。
    policy_view: 已生效的策略观察扩展。
    detector_view: 已生效的检测器请求扩展。
    audit: 已生效的双审计投影。
    component_views: 每类组件通过宿主接口能够获得的字段清单。
    enforced_boundaries: 运行时主动执行的固定边界说明。
    assumptions: 该清单不提供的安全保证和实验前提。
    plan_sha256: 完整 ExperimentPlan 规范 JSON 的 SHA-256。
    topology_sha256: 全部试验节点与有向边快照的 SHA-256。
  """

  schema_version: str
  trust_model: str
  policy_view: PolicyViewSpec
  detector_view: DetectorViewSpec
  audit: AuditViewSpec
  component_views: Mapping[str, Sequence[str]]
  enforced_boundaries: Sequence[str]
  assumptions: Sequence[str]
  plan_sha256: str
  topology_sha256: str

  def __post_init__(self) -> None:
    if self.schema_version != "stegopot.threat-model/1":
      raise ValueError("不支持的威胁模型清单版本")
    if self.trust_model != TRUSTED_IN_PROCESS:
      raise ValueError("威胁模型清单包含未实现的信任方式")
    if any(
        not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)
        for value in (self.plan_sha256, self.topology_sha256)
    ):
      raise ValueError("威胁模型清单摘要必须是 SHA-256 十六进制文本")
    normalized = {
        str(name): tuple(str(field_name) for field_name in fields)
        for name, fields in self.component_views.items()
    }
    object.__setattr__(self, "component_views", MappingProxyType(normalized))
    object.__setattr__(self, "enforced_boundaries", tuple(self.enforced_boundaries))
    object.__setattr__(self, "assumptions", tuple(self.assumptions))

  def to_dict(self) -> dict[str, Any]:
    """返回可封印、可比较的标准威胁模型工件。"""
    return {
        "schema_version": self.schema_version,
        "trust_model": self.trust_model,
        "controls": {
            "policy_view": self.policy_view.to_dict(),
            "detector_view": self.detector_view.to_dict(),
            "audit": self.audit.to_dict(),
        },
        "component_views": {
            name: list(fields)
            for name, fields in self.component_views.items()
        },
        "enforced_boundaries": list(self.enforced_boundaries),
        "assumptions": list(self.assumptions),
        "plan_sha256": self.plan_sha256,
        "topology_sha256": self.topology_sha256,
    }
