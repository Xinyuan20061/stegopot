"""实验工件与磁盘张量存储协议。"""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from stegopot.domain.model.trace import StoredTensorRef


class ArtifactStore(Protocol):
  """每个 run 独占、不可静默覆盖的工件存储。"""

  @property
  def root(self) -> str:
    """返回当前 run 工件根目录。"""
    ...

  def write_json(self, name: str, value: Mapping[str, Any]) -> Mapping[str, Any]:
    """独占写入 JSON 并返回摘要引用。"""
    ...

  def write_jsonl(self, name: str, values: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """独占写入 JSONL 并返回摘要引用。"""
    ...

  def write_tensor(self, name: str, tensor: Any) -> StoredTensorRef:
    """保存张量并返回不含原值的引用。"""
    ...

  def seal(self, metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """封印当前已写入工件并返回根清单。"""
    ...

  def close(self) -> None:
    """释放文件句柄；未封印时不得伪造完成状态。"""
    ...


class TraceStore(Protocol):
  """供模型适配器按需落盘单个张量的最小接口。"""

  def write_tensor(self, name: str, tensor: Any) -> StoredTensorRef:
    """写入张量并返回校验引用。"""
    ...
