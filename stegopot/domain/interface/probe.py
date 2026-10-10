"""可由外部插件实现的 Probe 契约。"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from stegopot.domain.model.probe import ProbeDataset, ProbeScore


class Probe(Protocol):
  """不限定线性、MLP、子空间或 SAE 表示的统一接口。"""

  @property
  def probe_id(self) -> str:
    """返回 Probe 类型和版本标识。"""
    ...
  def fit(self, dataset: ProbeDataset) -> None:
    """只使用调用方提供的数据训练 Probe。"""
    ...

  def predict(self, features: Any) -> Any:
    """返回 Probe 定义的预测。"""
    ...

  def score(self, features: Any) -> ProbeScore:
    """返回在线条件可以消费的有限分数。"""
    ...

  def save(self, path: str | Path) -> None:
    """保存 Probe 参数和版本元数据。"""
    ...

  def close(self) -> None:
    """释放 Probe 持有的可选加速器资源。"""
    ...


class ProbeLoader(Protocol):
  """把工件恢复为 Probe，避免在协议中固定类方法语义。"""

  def load(self, path: str | Path) -> Probe:
    """校验并加载 Probe 工件。"""
    ...
