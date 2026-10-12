"""供公开 SAE 后端实现的稳定运行协议。"""

from typing import Any, Protocol, runtime_checkable

from stegopot.domain.model.sae import SAEFeatureRef, SAEManifest


@runtime_checkable
class SAEModel(Protocol):
  """统一公开 SAE 的编码、解码和特征读取接口。

  约定输入激活和输出特征都保留前导维度；最后一维分别对应
  ``manifest.input_width`` 和 ``manifest.feature_width``。
  """

  @property
  def sae_id(self) -> str:
    """返回当前权重的稳定 SAE 标识。"""
    ...

  @property
  def manifest(self) -> SAEManifest:
    """返回来源、结构和兼容性元数据。"""
    ...

  def encode(self, activation: Any) -> Any:
    """把基础模型激活编码为稀疏特征。"""
    ...

  def decode(self, features: Any) -> Any:
    """把稀疏特征解码回基础模型激活空间。"""
    ...

  def reconstruct(self, activation: Any) -> Any:
    """执行编码和解码，并恢复输入张量的设备与数据类型。"""
    ...

  def feature(self, features: Any, ref: SAEFeatureRef | int) -> Any:
    """从特征张量最后一维读取指定特征。"""
    ...

  def close(self) -> None:
    """释放当前 SAE 持有的后端资源。"""
    ...
