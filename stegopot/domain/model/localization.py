"""秘密定位使用的稳定领域对象，不包含文件读取和算法实现。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
import json
import math
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Any


def _description(text: str) -> dict[str, str]:
  """返回统一的参数说明元数据。"""
  return {"description": text}


def _json_mapping(value: Mapping[str, Any], name: str) -> Mapping[str, Any]:
  """复制并冻结 JSON 映射，避免领域对象共享可变状态。"""
  if not isinstance(value, Mapping):
    raise TypeError(f"{name} 必须是映射")
  try:
    copied = json.loads(json.dumps(dict(value), ensure_ascii=False, allow_nan=False))
  except (TypeError, ValueError) as exc:
    raise ValueError(f"{name} 必须只包含有限 JSON 数据") from exc
  return MappingProxyType(copied)


def _non_empty(value: str, name: str) -> str:
  """验证并规范化非空字符串。"""
  if not isinstance(value, str) or not value.strip():
    raise ValueError(f"{name} 必须是非空字符串")
  return value.strip()


def _unit_interval(value: float, name: str) -> float:
  """验证位于闭区间 [0, 1] 的有限浮点数。"""
  number = float(value)
  if not math.isfinite(number) or not 0.0 <= number <= 1.0:
    raise ValueError(f"{name} 必须位于 [0, 1]")
  return number


class SecretKind(str, Enum):
  """中央研究标签的标准类型。"""

  CATEGORICAL = "categorical"
  BITSTRING = "bitstring"


class SurfaceKind(str, Enum):
  """秘密可能出现的标准研究表面。"""

  ACTIVATION = "activation"
  KV = "kv"
  LOGITS = "logits"
  TOKEN = "token"
  COT = "cot"
  TOOL = "tool"
  MEMORY = "memory"
  TIMING = "timing"
  BEHAVIOR = "behavior"
  WEIGHT = "weight"


class DataKind(str, Enum):
  """定位器能够消费的数据形态。"""

  VECTOR = "vector"
  TEXT = "text"
  CATEGORICAL_SEQUENCE = "categorical_sequence"
  NUMERIC_SEQUENCE = "numeric_sequence"
  STRUCTURED = "structured"
  PARAMETER = "parameter"


class UnsupportedSurfaceError(ValueError):
  """所请求表面未被本次采集或定位能力支持。"""


@dataclass(frozen=True)
class SecretSpec:
  """描述只允许离线研究分析器读取的秘密标签。"""

  name: str = field(metadata=_description("秘密标签名称。"))
  kind: SecretKind = field(metadata=_description("秘密是类别还是比特串。"))
  source: str = field(metadata=_description("中央标签来源说明，不是特征字段。"))
  classes: Sequence[str] = field(default_factory=tuple,
                                 metadata=_description("可选的固定类别顺序。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "name", _non_empty(self.name, "SecretSpec.name"))
    object.__setattr__(self, "kind", SecretKind(self.kind))
    object.__setattr__(self, "source", _non_empty(self.source, "SecretSpec.source"))
    classes = tuple(_non_empty(item, "SecretSpec.classes") for item in self.classes)
    if len(set(classes)) != len(classes):
      raise ValueError("SecretSpec.classes 不能重复")
    object.__setattr__(self, "classes", classes)

  def to_dict(self) -> dict[str, Any]:
    """返回可序列化且不含实际标签值的秘密声明。"""
    return {"name": self.name, "kind": self.kind.value,
            "source": self.source, "classes": list(self.classes)}

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "SecretSpec":
    """从标准映射恢复秘密声明。"""
    return cls(name=value["name"], kind=SecretKind(value["kind"]),
               source=value["source"], classes=value.get("classes", ()))


@dataclass(frozen=True)
class ArtifactRef:
  """引用经哈希验证的外部研究工件，避免把张量写入 JSON 日志。"""

  path: str = field(metadata=_description("相对工件包根目录的 POSIX 路径。"))
  sha256: str = field(metadata=_description("工件内容的 SHA-256 摘要。"))
  format: str = field(metadata=_description("工件序列化格式。"))
  shape: Sequence[int] = field(default_factory=tuple,
                               metadata=_description("张量或向量形状。"))
  dtype: str | None = field(default=None,
                            metadata=_description("数值工件的数据类型。"))

  def __post_init__(self) -> None:
    path = PurePosixPath(_non_empty(self.path, "ArtifactRef.path"))
    if path.is_absolute() or ".." in path.parts:
      raise ValueError("ArtifactRef.path 必须是包内相对路径")
    object.__setattr__(self, "path", path.as_posix())
    if not re.fullmatch(r"[0-9a-f]{64}", self.sha256):
      raise ValueError("ArtifactRef.sha256 必须是小写 SHA-256")
    object.__setattr__(self, "format", _non_empty(self.format, "ArtifactRef.format"))
    shape = tuple(int(item) for item in self.shape)
    if any(item < 0 for item in shape):
      raise ValueError("ArtifactRef.shape 不能包含负数")
    object.__setattr__(self, "shape", shape)
    if self.dtype is not None:
      object.__setattr__(self, "dtype", _non_empty(self.dtype, "ArtifactRef.dtype"))

  def to_dict(self) -> dict[str, Any]:
    """返回标准工件引用。"""
    return {"path": self.path, "sha256": self.sha256, "format": self.format,
            "shape": list(self.shape), "dtype": self.dtype}

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "ArtifactRef":
    """从标准映射恢复工件引用。"""
    return cls(path=value["path"], sha256=value["sha256"], format=value["format"],
               shape=value.get("shape", ()), dtype=value.get("dtype"))


@dataclass(frozen=True)
class ObservationAddress:
  """跨样本稳定标识一个可定位位置，不包含 trial ID 或秘密标签。"""

  surface: SurfaceKind = field(metadata=_description("观测所属隐写表面。"))
  agent_id: str | None = field(default=None,
                               metadata=_description("产生该观测的 Agent ID。"))
  address: Mapping[str, Any] = field(default_factory=dict,
                                     metadata=_description("层、轮次、位置等表面内地址。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "surface", SurfaceKind(self.surface))
    if self.agent_id is not None:
      object.__setattr__(self, "agent_id", _non_empty(self.agent_id, "agent_id"))
    object.__setattr__(self, "address", _json_mapping(self.address, "address"))

  @property
  def key(self) -> str:
    """返回可跨运行比较的确定性地址键。"""
    return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))

  def to_dict(self) -> dict[str, Any]:
    """返回标准地址。"""
    return {"surface": self.surface.value, "agent_id": self.agent_id,
            "address": dict(self.address)}

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "ObservationAddress":
    """从标准映射恢复地址。"""
    return cls(surface=SurfaceKind(value["surface"]), agent_id=value.get("agent_id"),
               address=value.get("address", {}))


@dataclass(frozen=True)
class ObservationUnit:
  """一次试验中可由离线定位器读取的工件单元。"""

  run_id: str = field(metadata=_description("来源运行 ID。"))
  trial_id: str = field(metadata=_description("来源 Trial ID。"))
  address: ObservationAddress = field(metadata=_description("跨试验稳定观测地址。"))
  value_ref: ArtifactRef = field(metadata=_description("外部研究工件引用。"))
  timestamp: float | None = field(default=None,
                                  metadata=_description("可选采集时间戳。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "run_id", _non_empty(self.run_id, "run_id"))
    object.__setattr__(self, "trial_id", _non_empty(self.trial_id, "trial_id"))
    if self.timestamp is not None and not math.isfinite(float(self.timestamp)):
      raise ValueError("ObservationUnit.timestamp 必须是有限数")

  def to_dict(self) -> dict[str, Any]:
    """返回标准观测单元。"""
    return {"run_id": self.run_id, "trial_id": self.trial_id,
            "address": self.address.to_dict(), "value_ref": self.value_ref.to_dict(),
            "timestamp": self.timestamp}


@dataclass(frozen=True)
class CapturedObservation:
  """尚未与中央秘密标签连接的离线观测。"""

  run_id: str = field(metadata=_description("来源运行 ID。"))
  trial_id: str = field(metadata=_description("来源 Trial ID。"))
  address: ObservationAddress = field(metadata=_description("跨试验稳定地址。"))
  value: Any = field(metadata=_description("文本、向量或结构化观测值。"))
  metadata: Mapping[str, Any] = field(default_factory=dict,
                                      metadata=_description("不含 truth/secret/label 的研究元数据。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "run_id", _non_empty(self.run_id, "run_id"))
    object.__setattr__(self, "trial_id", _non_empty(self.trial_id, "trial_id"))
    object.__setattr__(self, "metadata", _json_mapping(self.metadata, "metadata"))

  @property
  def sample_id(self) -> str:
    """返回跨运行唯一的样本 ID。"""
    return f"{self.run_id}:{self.trial_id}"


@dataclass(frozen=True)
class LocalizerSample:
  """中央离线分析中的一个有标签样本。"""

  sample_id: str = field(metadata=_description("跨运行唯一的样本 ID。"))
  group_id: str = field(metadata=_description("配对秘密组 ID，切分以此为单位。"))
  label: str = field(metadata=_description("中央秘密标签，仅传给离线定位器。"))
  value: Any = field(metadata=_description("供定位器使用的局部状态。"))

  def __post_init__(self) -> None:
    for name in ("sample_id", "group_id", "label"):
      object.__setattr__(self, name, _non_empty(getattr(self, name), name))


@dataclass(frozen=True)
class LocalizerDataset:
  """同一观测地址上的配对秘密数据集。"""

  secret: SecretSpec = field(metadata=_description("中央秘密声明。"))
  address: ObservationAddress = field(metadata=_description("被定位的稳定地址。"))
  data_kind: DataKind = field(metadata=_description("样本值的数据形态。"))
  samples: Sequence[LocalizerSample] = field(metadata=_description("有标签配对样本。"))
  metadata: Mapping[str, Any] = field(default_factory=dict,
                                      metadata=_description("受泄漏审计约束的数据集元数据。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "data_kind", DataKind(self.data_kind))
    samples = tuple(self.samples)
    if not samples:
      raise ValueError("LocalizerDataset.samples 不能为空")
    if len({item.sample_id for item in samples}) != len(samples):
      raise ValueError("LocalizerDataset.sample_id 不能重复")
    object.__setattr__(self, "samples", samples)
    object.__setattr__(self, "metadata", _json_mapping(self.metadata, "metadata"))

  def with_labels(self, labels: Sequence[str]) -> "LocalizerDataset":
    """保留特征与分组并替换标签，用于 permutation null test。"""
    if len(labels) != len(self.samples):
      raise ValueError("替换标签数量与样本数不一致")
    samples = tuple(LocalizerSample(item.sample_id, item.group_id, label, item.value)
                    for item, label in zip(self.samples, labels, strict=True))
    return LocalizerDataset(self.secret, self.address, self.data_kind, samples, self.metadata)


@dataclass(frozen=True)
class LocalizationMetrics:
  """统一秘密定位分数及其可审查基础指标。"""

  score: float = field(metadata=_description("相对交叉熵下降，范围 [0, 1]。"))
  accuracy: float = field(metadata=_description("测试集分类准确率。"))
  cross_entropy: float = field(metadata=_description("测试集交叉熵。"))
  baseline_cross_entropy: float = field(metadata=_description("训练先验基线交叉熵。"))
  confidence_low: float = field(metadata=_description("定位分数置信区间下界。"))
  confidence_high: float = field(metadata=_description("定位分数置信区间上界。"))

  def __post_init__(self) -> None:
    for name in ("score", "accuracy", "confidence_low", "confidence_high"):
      object.__setattr__(self, name, _unit_interval(getattr(self, name), name))
    for name in ("cross_entropy", "baseline_cross_entropy"):
      value = float(getattr(self, name))
      if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} 必须是非负有限数")
      object.__setattr__(self, name, value)
    if self.confidence_low > self.confidence_high:
      raise ValueError("置信区间上下界顺序错误")

  def to_dict(self) -> dict[str, Any]:
    """返回统一指标。"""
    return {"score": self.score, "accuracy": self.accuracy,
            "cross_entropy": self.cross_entropy,
            "baseline_cross_entropy": self.baseline_cross_entropy,
            "confidence_interval": [self.confidence_low, self.confidence_high]}

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "LocalizationMetrics":
    """从标准映射恢复指标。"""
    interval = value["confidence_interval"]
    return cls(value["score"], value["accuracy"], value["cross_entropy"],
               value["baseline_cross_entropy"], interval[0], interval[1])


@dataclass(frozen=True)
class NullTestResult:
  """标签置换随机对照结果。"""

  repetitions: int = field(metadata=_description("标签置换次数。"))
  mean_score: float = field(metadata=_description("随机标签平均定位分数。"))
  std_score: float = field(metadata=_description("随机标签定位分数标准差。"))
  real_minus_null: float = field(metadata=_description("真实分数减随机均值。"))
  p_value: float = field(metadata=_description("置换检验单侧 p 值。"))

  def __post_init__(self) -> None:
    if self.repetitions < 1:
      raise ValueError("NullTestResult.repetitions 必须为正数")
    object.__setattr__(self, "mean_score", _unit_interval(self.mean_score, "mean_score"))
    if not math.isfinite(float(self.std_score)) or self.std_score < 0:
      raise ValueError("std_score 必须是非负有限数")
    if not math.isfinite(float(self.real_minus_null)):
      raise ValueError("real_minus_null 必须是有限数")
    object.__setattr__(self, "p_value", _unit_interval(self.p_value, "p_value"))

  def to_dict(self) -> dict[str, Any]:
    """返回随机对照指标。"""
    return {"repetitions": self.repetitions, "mean_score": self.mean_score,
            "std_score": self.std_score, "real_minus_null": self.real_minus_null,
            "p_value": self.p_value}

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "NullTestResult":
    """从标准映射恢复随机对照。"""
    return cls(**{name: value[name] for name in (
        "repetitions", "mean_score", "std_score", "real_minus_null", "p_value")})


@dataclass(frozen=True)
class LocalizationResult:
  """一个稳定地址上的秘密定位结果。"""

  unit: ObservationAddress = field(metadata=_description("被定位的稳定地址。"))
  method: str = field(metadata=_description("定位器方法名称。"))
  metrics: LocalizationMetrics = field(metadata=_description("统一定位指标。"))
  null_test: NullTestResult = field(metadata=_description("标签置换随机对照。"))
  sample_count: int = field(metadata=_description("参与该地址分析的总样本数。"))
  significant: bool = field(metadata=_description("是否通过预注册显著性阈值。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "method", _non_empty(self.method, "method"))
    if self.sample_count < 1:
      raise ValueError("sample_count 必须为正数")
    if not isinstance(self.significant, bool):
      raise TypeError("significant 必须是 bool")

  def to_dict(self) -> dict[str, Any]:
    """返回标准定位结果。"""
    return {"unit": self.unit.to_dict(), "method": self.method,
            "score": self.metrics.score, "metrics": self.metrics.to_dict(),
            "null_metrics": self.null_test.to_dict(),
            "sample_count": self.sample_count, "significant": self.significant}

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "LocalizationResult":
    """从标准映射恢复定位结果。"""
    return cls(ObservationAddress.from_dict(value["unit"]), value["method"],
               LocalizationMetrics.from_dict(value["metrics"]),
               NullTestResult.from_dict(value["null_metrics"]),
               int(value["sample_count"]), bool(value["significant"]))


@dataclass(frozen=True)
class SurfaceSummary:
  """使用 Top-K 规则聚合一个隐写表面。"""

  surface: SurfaceKind = field(metadata=_description("被聚合的隐写表面。"))
  peak_score: float = field(metadata=_description("该表面的最高定位分数。"))
  top_k_mean: float = field(metadata=_description("前 K 个定位分数的平均值。"))
  significant_unit_ratio: float = field(metadata=_description("显著单元占比。"))
  unit_count: int = field(metadata=_description("参与聚合的单元数量。"))
  top_k: int = field(metadata=_description("预注册的 Top-K 参数。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "surface", SurfaceKind(self.surface))
    for name in ("peak_score", "top_k_mean", "significant_unit_ratio"):
      object.__setattr__(self, name, _unit_interval(getattr(self, name), name))
    if self.unit_count < 1 or self.top_k < 1:
      raise ValueError("unit_count 和 top_k 必须为正数")

  def to_dict(self) -> dict[str, Any]:
    """返回标准表面摘要。"""
    return {"surface": self.surface.value, "peak_score": self.peak_score,
            "top_k_mean": self.top_k_mean,
            "significant_unit_ratio": self.significant_unit_ratio,
            "unit_count": self.unit_count, "top_k": self.top_k}


@dataclass(frozen=True)
class LocalizationMap:
  """一次离线分析产生的统一秘密定位地图。"""

  analysis_id: str = field(metadata=_description("不可变分析实例 ID。"))
  secret: SecretSpec = field(metadata=_description("被定位的中央秘密声明。"))
  run_ids: Sequence[str] = field(metadata=_description("来源封印运行 ID。"))
  units: Sequence[LocalizationResult] = field(metadata=_description("地址级定位结果。"))
  surface_scores: Sequence[SurfaceSummary] = field(metadata=_description("表面级 Top-K 摘要。"))
  protocol_fingerprint: str = field(metadata=_description("定位与归因协议指纹。"))
  analysis_metadata: Mapping[str, Any] = field(default_factory=dict,
                                               metadata=_description("不包含秘密标签值的分析元数据。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "analysis_id", _non_empty(self.analysis_id, "analysis_id"))
    run_ids = tuple(_non_empty(item, "run_id") for item in self.run_ids)
    if not run_ids or len(set(run_ids)) != len(run_ids):
      raise ValueError("run_ids 必须非空且不能重复")
    object.__setattr__(self, "run_ids", run_ids)
    object.__setattr__(self, "units", tuple(self.units))
    object.__setattr__(self, "surface_scores", tuple(self.surface_scores))
    if not re.fullmatch(r"[0-9a-f]{64}", self.protocol_fingerprint):
      raise ValueError("protocol_fingerprint 必须是 SHA-256")
    object.__setattr__(self, "analysis_metadata",
                       _json_mapping(self.analysis_metadata, "analysis_metadata"))

  def to_dict(self) -> dict[str, Any]:
    """返回可写入 localization.json 的标准结构。"""
    return {"schema_version": "stegopot.localization/1",
            "analysis_id": self.analysis_id, "secret": self.secret.to_dict(),
            "run_ids": list(self.run_ids),
            "units": [item.to_dict() for item in self.units],
            "surface_scores": [item.to_dict() for item in self.surface_scores],
            "protocol_fingerprint": self.protocol_fingerprint,
            "analysis_metadata": dict(self.analysis_metadata)}

  @classmethod
  def from_dict(cls, value: Mapping[str, Any]) -> "LocalizationMap":
    """从 localization.json 恢复定位地图。"""
    if value.get("schema_version") != "stegopot.localization/1":
      raise ValueError("不支持的 LocalizationMap schema")
    summaries = [SurfaceSummary(
        SurfaceKind(item["surface"]), item["peak_score"], item["top_k_mean"],
        item["significant_unit_ratio"], item["unit_count"], item["top_k"])
                 for item in value.get("surface_scores", ())]
    return cls(value["analysis_id"], SecretSpec.from_dict(value["secret"]),
               value["run_ids"],
               [LocalizationResult.from_dict(item) for item in value.get("units", ())],
               summaries, value["protocol_fingerprint"],
               value.get("analysis_metadata", {}))


@dataclass(frozen=True)
class ResearchCapabilities:
  """声明一次白盒采集实际支持的研究表面。"""

  provider: str = field(metadata=_description("模型或采集适配器名称。"))
  surfaces: Sequence[SurfaceKind] = field(metadata=_description("实际可采集的表面集合。"))
  white_box: bool = field(metadata=_description("是否具有模型内部白盒访问。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "provider", _non_empty(self.provider, "provider"))
    surfaces = tuple(dict.fromkeys(SurfaceKind(item) for item in self.surfaces))
    object.__setattr__(self, "surfaces", surfaces)
    if not isinstance(self.white_box, bool):
      raise TypeError("white_box 必须是 bool")

  def require(self, surface: SurfaceKind) -> None:
    """要求能力明确支持 surface；不把 unsupported 解释成零分。"""
    surface = SurfaceKind(surface)
    if surface not in self.surfaces:
      raise UnsupportedSurfaceError(f"采集能力不支持 {surface.value} 表面")

  def to_dict(self) -> dict[str, Any]:
    """返回可写入采集清单的能力声明。"""
    return {"provider": self.provider,
            "surfaces": [item.value for item in self.surfaces],
            "white_box": self.white_box}
