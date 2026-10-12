"""与具体 SAE 库无关的稀疏自编码器领域对象。"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
import math
from types import MappingProxyType
from typing import Any, Literal


def _description(text: str) -> dict[str, str]:
  return {"description": text}


class SAECompatibilityError(ValueError):
  """公开 SAE 与目标模型、激活位置或张量宽度不兼容。"""


@dataclass(frozen=True)
class SAEManifest:
  """记录一个已加载公开 SAE 的来源、结构和兼容性元数据。"""

  sae_id: str = field(metadata=_description("公开 SAE 在来源中的稳定标识。"))
  source: str = field(metadata=_description("SAE release、仓库 ID 或本地目录。"))
  source_kind: Literal["pretrained", "local"] = field(
      metadata=_description("权重来自公开预训练资源或本地目录。"))
  input_width: int = field(metadata=_description("SAE 输入激活最后一维的宽度。"))
  feature_width: int = field(metadata=_description("SAE 稀疏特征最后一维的宽度。"))
  architecture: str = field(metadata=_description("SAE 后端声明的架构名称。"))
  dtype: str = field(metadata=_description("加载 SAE 参数时使用的数据类型。"))
  base_model_id: str | None = field(
      default=None, metadata=_description("训练该 SAE 所用的基础语言模型 ID。"))
  hook_name: str | None = field(
      default=None, metadata=_description("训练 SAE 时采集激活的位置名称。"))
  library: str = field(
      default="sae_lens", metadata=_description("提供 SAE 实现的基础设施库。"))
  library_version: str | None = field(
      default=None, metadata=_description("加载权重时使用的基础设施库版本。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict,
      metadata=_description("来源配置中不含权重和秘密的附加元数据。"))

  def __post_init__(self) -> None:
    """拒绝不完整清单，确保实验记录可以独立解释。"""
    for name in ("sae_id", "source", "architecture", "dtype", "library"):
      value = getattr(self, name)
      if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 必须是非空字符串")
      object.__setattr__(self, name, value.strip())
    if self.source_kind not in {"pretrained", "local"}:
      raise ValueError("source_kind 必须是 pretrained 或 local")
    if type(self.input_width) is not int or self.input_width <= 0:
      raise ValueError("input_width 必须是正整数")
    if type(self.feature_width) is not int or self.feature_width <= 0:
      raise ValueError("feature_width 必须是正整数")
    for name in ("base_model_id", "hook_name", "library_version"):
      value = getattr(self, name)
      if value is not None:
        if not isinstance(value, str) or not value.strip():
          raise ValueError(f"{name} 必须为空或非空字符串")
        object.__setattr__(self, name, value.strip())
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  def to_manifest(self) -> dict[str, Any]:
    """返回可写入 JSON 实验清单的普通字典。"""
    return {
        "sae_id": self.sae_id,
        "source": self.source,
        "source_kind": self.source_kind,
        "input_width": self.input_width,
        "feature_width": self.feature_width,
        "architecture": self.architecture,
        "dtype": self.dtype,
        "base_model_id": self.base_model_id,
        "hook_name": self.hook_name,
        "library": self.library,
        "library_version": self.library_version,
        "metadata": _json_value(dict(self.metadata)),
    }


@dataclass(frozen=True)
class SAEFeatureRef:
  """使用 SAE 身份和非负索引唯一指向一个稀疏特征。"""

  sae_id: str = field(metadata=_description("特征所属 SAE 的稳定标识。"))
  index: int = field(metadata=_description("特征向量最后一维的零基索引。"))

  def __post_init__(self) -> None:
    if not isinstance(self.sae_id, str) or not self.sae_id.strip():
      raise ValueError("sae_id 必须是非空字符串")
    if type(self.index) is not int or self.index < 0:
      raise ValueError("index 必须是非负整数")
    object.__setattr__(self, "sae_id", self.sae_id.strip())


@dataclass(frozen=True)
class SAEReconstructionReport:
  """描述 SAE 在一批激活上的重构质量和稀疏度。"""

  mse: float = field(metadata=_description("原始激活与重构激活的均方误差。"))
  relative_mse: float = field(
      metadata=_description("均方误差相对原始激活均方幅度的比值。"))
  cosine_similarity: float = field(
      metadata=_description("展平后原始激活与重构激活的余弦相似度。"))
  explained_variance: float | None = field(
      metadata=_description("重构解释方差；原始方差为零时为空。"))
  mean_l0: float = field(
      metadata=_description("每个位置非零 SAE 特征数量的平均值。"))
  feature_density: float = field(
      metadata=_description("mean_l0 与 SAE 特征总宽度的比值。"))

  def __post_init__(self) -> None:
    values = (self.mse, self.relative_mse, self.cosine_similarity,
              self.mean_l0, self.feature_density)
    if any(not math.isfinite(float(value)) for value in values):
      raise ValueError("SAE 重构指标必须是有限数")
    if self.explained_variance is not None and not math.isfinite(
        float(self.explained_variance)):
      raise ValueError("explained_variance 必须为空或有限数")
    if self.mse < 0 or self.relative_mse < 0 or self.mean_l0 < 0:
      raise ValueError("误差与稀疏度指标不能为负数")
    if not 0 <= self.feature_density <= 1:
      raise ValueError("feature_density 必须位于 [0, 1]")

  def to_manifest(self) -> dict[str, Any]:
    """返回可序列化的重构质量记录。"""
    return asdict(self)


def _json_value(value: Any) -> Any:
  """把后端配置缩减为稳定的 JSON 值，未知对象仅记录类型名。"""
  if value is None or isinstance(value, (str, int, float, bool)):
    return value
  if isinstance(value, Mapping):
    return {str(key): _json_value(item) for key, item in value.items()}
  if isinstance(value, (list, tuple)):
    return [_json_value(item) for item in value]
  return {"type": type(value).__name__}
