"""独占写入、可校验封印的本地实验工件存储。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

from stegopot.domain.model.trace import StoredTensorRef


class FileArtifactStore:
  """一个实例只负责一个新 run 目录，不覆盖已有工件。"""

  def __init__(self, root: str | Path) -> None:
    """创建独占目录。

    参数：
      root: 当前 run 的新目录；已存在时拒绝打开，避免覆盖历史实验。
    """
    self._root = Path(root).expanduser().resolve()
    self._root.mkdir(parents=True, exist_ok=False)
    self._entries: dict[str, dict[str, Any]] = {}
    self._sealed = False
    self._closed = False

  @property
  def root(self) -> str:
    """返回绝对工件根目录。"""
    return str(self._root)

  def write_json(
      self, name: str, value: Mapping[str, Any],
  ) -> Mapping[str, Any]:
    """独占写入 UTF-8 JSON。"""
    data = json.dumps(
        value, ensure_ascii=False, sort_keys=True, indent=2,
        allow_nan=False).encode("utf-8")
    return self._write(name, data, "json")

  def write_jsonl(
      self, name: str, values: Sequence[Mapping[str, Any]],
  ) -> Mapping[str, Any]:
    """独占写入稳定 JSONL。"""
    lines = [
        json.dumps(item, ensure_ascii=False, sort_keys=True, allow_nan=False)
        for item in values
    ]
    data = (("\n".join(lines) + "\n") if lines else "").encode("utf-8")
    return self._write(name, data, "jsonl")

  def write_tensor(self, name: str, tensor: Any) -> StoredTensorRef:
    """用 torch.save 写入 CPU Tensor 并返回摘要引用。"""
    self._ensure_writable()
    target, relative = self._target(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
      import torch
    except ImportError as exc:
      raise RuntimeError("保存张量需要安装 torch") from exc
    if not torch.is_tensor(tensor):
      raise TypeError("write_tensor 只接受 PyTorch Tensor")
    value = tensor.detach().cpu()
    with target.open("xb") as handle:
      torch.save(value, handle)
    entry = self._remember(relative, target, "torch")
    return StoredTensorRef(
        relative, entry["sha256"], "torch",
        tuple(int(item) for item in value.shape), str(value.dtype))

  def seal(self, metadata: Mapping[str, Any]) -> Mapping[str, Any]:
    """写入包含全部已登记工件摘要的只读清单。"""
    self._ensure_writable()
    manifest = {
        "schema_version": "stegopot.artifacts/1",
        "metadata": dict(metadata),
        "artifacts": [self._entries[name] for name in sorted(self._entries)],
    }
    reference = self.write_json("manifest.json", manifest)
    self._sealed = True
    return reference

  def close(self) -> None:
    """关闭写入端；不自动伪造封印。"""
    self._closed = True

  def _write(self, name: str, data: bytes, format_name: str) -> Mapping[str, Any]:
    self._ensure_writable()
    target, relative = self._target(name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("xb") as handle:
      handle.write(data)
      handle.flush()
    return self._remember(relative, target, format_name)

  def _remember(
      self, relative: str, target: Path, format_name: str,
  ) -> dict[str, Any]:
    entry = {
        "path": relative, "format": format_name,
        "size": target.stat().st_size, "sha256": _digest(target),
    }
    self._entries[relative] = entry
    return dict(entry)

  def _target(self, name: str) -> tuple[Path, str]:
    value = PurePosixPath(name)
    if value.is_absolute() or not value.parts or ".." in value.parts:
      raise ValueError("工件名称必须是根目录内的安全相对路径")
    relative = value.as_posix()
    target = (self._root / Path(*value.parts)).resolve()
    if self._root not in target.parents:
      raise ValueError("工件路径越过运行目录")
    if relative in self._entries or target.exists():
      raise FileExistsError(f"工件已存在：{relative}")
    return target, relative

  def _ensure_writable(self) -> None:
    if self._closed:
      raise RuntimeError("ArtifactStore 已关闭")
    if self._sealed:
      raise RuntimeError("ArtifactStore 已封印")


def _digest(path: Path) -> str:
  value = hashlib.sha256()
  with path.open("rb") as handle:
    for block in iter(lambda: handle.read(1024 * 1024), b""):
      value.update(block)
  return value.hexdigest()
