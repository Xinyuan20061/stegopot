"""把具体 SAE 后端约束到 StegoPot 的稳定运行协议。"""

from __future__ import annotations

from typing import Any

from stegopot.domain.model.sae import (
    SAECompatibilityError,
    SAEFeatureRef,
    SAEManifest,
)


class SAERuntime:
  """验证张量边界并代理后端的 encode/decode 调用。"""

  def __init__(self, backend: Any, manifest: SAEManifest, *, device: str,
               dtype: str) -> None:
    """保存已加载后端。

    参数：
      backend: 提供 encode 和 decode 的已加载 SAE 对象。
      manifest: 经加载器提取并验证的 SAE 元数据。
      device: SAE 执行使用的 PyTorch 设备字符串。
      dtype: SAE 输入转换使用的 PyTorch 数据类型名称。
    """
    if not callable(getattr(backend, "encode", None)):
      raise TypeError("SAE 后端必须提供 encode")
    if not callable(getattr(backend, "decode", None)):
      raise TypeError("SAE 后端必须提供 decode")
    self._backend = backend
    self._manifest = manifest
    self._device = device
    self._dtype = dtype

  @property
  def sae_id(self) -> str:
    """返回当前权重的稳定 SAE 标识。"""
    return self._manifest.sae_id

  @property
  def manifest(self) -> SAEManifest:
    """返回只读 SAE 清单。"""
    return self._manifest

  def encode(self, activation: Any) -> Any:
    """校验输入宽度后编码激活。"""
    tensor = self._prepare(activation, self._manifest.input_width, "激活")
    features = self._backend_or_raise().encode(tensor)
    self._validate_last_width(features, self._manifest.feature_width, "SAE 特征")
    return features

  def decode(self, features: Any) -> Any:
    """校验特征宽度后解码激活。"""
    tensor = self._prepare(features, self._manifest.feature_width, "SAE 特征")
    activation = self._backend_or_raise().decode(tensor)
    self._validate_last_width(activation, self._manifest.input_width, "重构激活")
    return activation

  def reconstruct(self, activation: Any) -> Any:
    """重构激活并恢复调用方张量的设备和数据类型。"""
    self._require_tensor(activation, "激活")
    reconstructed = self.decode(self.encode(activation))
    return reconstructed.to(device=activation.device, dtype=activation.dtype)

  def feature(self, features: Any, ref: SAEFeatureRef | int) -> Any:
    """读取最后一维中的一个 SAE 特征。"""
    index = ref.index if isinstance(ref, SAEFeatureRef) else ref
    if isinstance(ref, SAEFeatureRef) and ref.sae_id != self.sae_id:
      raise SAECompatibilityError("特征引用属于另一个 SAE")
    if type(index) is not int or not 0 <= index < self._manifest.feature_width:
      raise IndexError("SAE 特征索引超出范围")
    self._validate_last_width(features, self._manifest.feature_width, "SAE 特征")
    return features[..., index]

  def close(self) -> None:
    """断开后端引用，使运行器可以及时回收显存。"""
    backend, self._backend = self._backend, None
    close = getattr(backend, "close", None)
    if callable(close):
      close()

  def _prepare(self, value: Any, width: int, label: str) -> Any:
    """检查 PyTorch 张量并转到 SAE 的执行设备和数据类型。"""
    self._validate_last_width(value, width, label)
    torch = _torch()
    dtype = getattr(torch, self._dtype, None)
    if dtype is None:
      raise ValueError(f"PyTorch 不支持数据类型 {self._dtype}")
    return value.to(device=self._device, dtype=dtype)

  def _validate_last_width(self, value: Any, width: int, label: str) -> None:
    """验证张量及其最后一维。"""
    self._require_tensor(value, label)
    if value.ndim == 0 or value.shape[-1] != width:
      actual = "标量" if value.ndim == 0 else value.shape[-1]
      raise SAECompatibilityError(
          f"{label}最后一维应为 {width}，实际为 {actual}")

  @staticmethod
  def _require_tensor(value: Any, label: str) -> None:
    """拒绝把数组或列表隐式转换成模型张量。"""
    if not _torch().is_tensor(value):
      raise TypeError(f"{label}必须是 PyTorch 张量")

  def _backend_or_raise(self) -> Any:
    """在资源已关闭后拒绝继续执行。"""
    if self._backend is None:
      raise RuntimeError("SAE 资源已经关闭")
    return self._backend


def _torch() -> Any:
  """延迟导入 PyTorch，保持基础安装轻量。"""
  try:
    import torch
  except ImportError as exc:
    raise RuntimeError("使用 SAE 需要安装 stegopot[sae]") from exc
  return torch
