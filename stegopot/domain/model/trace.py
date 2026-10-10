"""Activation Trace 与外部存储引用。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from stegopot.domain.model.reference import TensorRef


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass(frozen=True)
class StoredTensorRef:
  """磁盘或 mmap 中张量工件的可校验引用。"""

  path: str = field(metadata=_description("相对所属工件根目录的安全路径。"))
  sha256: str = field(metadata=_description("张量文件的 SHA-256。"))
  format: str = field(metadata=_description("torch、safetensors、numpy 或自定义格式。"))
  shape: Sequence[int] = field(metadata=_description("张量维度。"))
  dtype: str = field(metadata=_description("张量数值类型。"))

  def __post_init__(self) -> None:
    if not self.path or not self.format or not self.dtype:
      raise ValueError("StoredTensorRef 的 path、format 和 dtype 不能为空")
    if len(self.sha256) != 64:
      raise ValueError("sha256 必须是 64 位十六进制摘要")
    shape = tuple(int(item) for item in self.shape)
    if any(item < 0 for item in shape):
      raise ValueError("shape 不能包含负数")
    object.__setattr__(self, "shape", shape)

  def to_dict(self) -> dict:
    """返回不含张量原值的工件引用。"""
    return {"path": self.path, "sha256": self.sha256, "format": self.format,
            "shape": list(self.shape), "dtype": self.dtype}


@dataclass
class ActivationRecord:
  """一个位置在一次模型前向中的激活及可选梯度。"""

  ref: TensorRef = field(metadata=_description("逻辑张量位置。"))
  value: Any = field(repr=False, metadata=_description("内存/CPU 张量或 StoredTensorRef。"))
  shape: Sequence[int] = field(metadata=_description("选择 token/head 后的激活形状。"))
  dtype: str = field(metadata=_description("激活数值类型。"))
  device: str = field(metadata=_description("记录创建时的设备。"))
  step_index: int | None = field(
      default=None, metadata=_description("生成步骤；普通前向时为空。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("不包含张量原值的后端元数据。"))
  _gradient: Any = field(
      default=None, init=False, repr=False, metadata=_description("反向传播后由 Hook 写入的梯度。"))

  def __post_init__(self) -> None:
    self.shape = tuple(int(item) for item in self.shape)
    if any(item < 0 for item in self.shape):
      raise ValueError("shape 不能包含负数")
    if self.step_index is not None and (type(self.step_index) is not int or self.step_index < 0):
      raise ValueError("step_index 必须是非负整数或 None")
    self.metadata = MappingProxyType(dict(self.metadata))

  @property
  def gradient(self) -> Any:
    """返回反向传播后捕获的梯度；未请求或尚未 backward 时为 None。"""
    return self._gradient

  def set_gradient(self, gradient: Any) -> None:
    """供受控 Hook 写入一次梯度；重复写入表示运行时契约错误。"""
    if self._gradient is not None:
      raise RuntimeError("同一 ActivationRecord 的梯度不能重复写入")
    self._gradient = gradient

  def to_manifest(self) -> dict:
    """返回不序列化张量原值的轨迹清单。"""
    value_ref = self.value.to_dict() if isinstance(self.value, StoredTensorRef) else None
    return {"ref": self.ref.to_dict(), "shape": list(self.shape), "dtype": self.dtype,
            "device": self.device, "step_index": self.step_index,
            "value_ref": value_ref, "gradient_ready": self.gradient is not None,
            "metadata": dict(self.metadata)}

@dataclass(frozen=True)
class ActivationTrace:
  """一次普通或生成步骤前向的选择性内部状态集合。"""

  run_id: str = field(metadata=_description("调用方或宿主提供的运行 ID。"))
  model_id: str = field(metadata=_description("模型权重与适配器的稳定标识。"))
  input_token_ids: Sequence[int] = field(
      repr=False, metadata=_description("本次前向使用的输入 token ID。"))
  records: Sequence[ActivationRecord] = field(metadata=_description("按 Hook 命中顺序保存的记录。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("精度、设备和后端等复现元数据。"))

  def __post_init__(self) -> None:
    if not self.run_id or not self.model_id:
      raise ValueError("ActivationTrace.run_id 和 model_id 不能为空")
    tokens = tuple(int(item) for item in self.input_token_ids)
    records = tuple(self.records)
    if len({(item.ref.key, item.step_index) for item in records}) != len(records):
      raise ValueError("同一步骤不能重复保存同一 TensorRef")
    object.__setattr__(self, "input_token_ids", tokens)
    object.__setattr__(self, "records", records)
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

  def get(self, ref: TensorRef, *, step_index: int | None = None) -> ActivationRecord:
    """按稳定引用和可选生成步骤读取唯一记录。"""
    matches = [item for item in self.records
               if item.ref.key == ref.key and item.step_index == step_index]
    if len(matches) != 1:
      raise KeyError(f"轨迹中期望一个记录，实际为 {len(matches)}：{ref.key}")
    return matches[0]

  def select(
      self, *, layer: int | None = None, component: str | None = None,
      step_index: int | None = None,
  ) -> tuple[ActivationRecord, ...]:
    """按层、组件和生成步骤筛选记录。"""
    return tuple(item for item in self.records
                 if (layer is None or item.ref.layer == layer)
                 and (component is None or item.ref.component == component)
                 and (step_index is None or item.step_index == step_index))

  def to_manifest(self) -> dict:
    """返回不包含内存张量的轨迹清单。"""
    return {"schema_version": "stegopot.activation-trace/1", "run_id": self.run_id,
            "model_id": self.model_id, "input_token_count": len(self.input_token_ids),
            "records": [item.to_manifest() for item in self.records],
            "metadata": dict(self.metadata)}
