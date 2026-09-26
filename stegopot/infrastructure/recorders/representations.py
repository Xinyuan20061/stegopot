"""大向量研究工件的独立记录、封印和按需读取。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import struct
from typing import Any

from stegopot.infrastructure.recorders.audit.integrity import (
    canonical_json,
    file_digest,
    verify_experiment,
)


class RepresentationRecorder:
  """把内部向量写入独立研究工件包，不向 public/research JSONL 写张量。"""

  def __init__(
      self,
      directory: str | Path,
      *,
      source_run: str | Path,
      run_id: str,
      capabilities: Mapping[str, Any],
  ) -> None:
    """创建全新采集包。

    参数：
      directory: 采集包目录，必须不存在且不能位于待封印运行目录中。
      source_run: 来源实验目录，可以尚未封印；采集包不得位于该目录内。
      run_id: 将在 seal 时绑定的实验运行 ID。
      capabilities: 模型适配器实际声明的白盒采集能力。
    """
    self.directory = Path(directory).resolve()
    self.source_run = Path(source_run).resolve()
    if self.directory == self.source_run or self.directory.is_relative_to(self.source_run):
      raise ValueError("表征工件包不能写入原实验运行目录")
    self.directory.mkdir(parents=True, exist_ok=False)
    self.run_id = _identifier(run_id, "run_id")
    self.capabilities = _capabilities(capabilities)
    self._entries: list[dict[str, Any]] = []
    self._sealed = False

  def record_vector(
      self,
      *,
      trial_id: str,
      agent_id: str,
      surface: str,
      address: Mapping[str, Any],
      value: Sequence[float],
      timestamp: float | None = None,
  ) -> dict[str, Any]:
    """记录一个有限 float64 向量并返回仅含引用的观测单元。

    参数：
      trial_id: 来源 Trial ID。
      agent_id: 产生向量的 Agent ID。
      surface: activation、kv 或 logits 等已声明表面。
      address: layer、token、step 等表面内地址。
      value: 不直接写入审计 JSON 的数值向量。
      timestamp: 可选采集时间戳。
    """
    if self._sealed:
      raise RuntimeError("表征工件包已经封印")
    trial_id = _identifier(trial_id, "trial_id")
    agent_id = _identifier(agent_id, "agent_id")
    surface = _surface(surface)
    if surface not in self.capabilities["surfaces"]:
      raise ValueError(f"采集能力不支持 {surface} 表面；unsupported 不能记录为零")
    vector = tuple(float(item) for item in value)
    if not vector or any(not math.isfinite(item) for item in vector):
      raise ValueError("表征向量必须非空且只含有限数")
    if timestamp is not None and not math.isfinite(float(timestamp)):
      raise ValueError("timestamp 必须是有限数")
    relative = Path("artifacts") / trial_id / agent_id / surface / f"{len(self._entries):08d}.f64"
    path = self.directory / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
      stream.write(struct.pack(f"<{len(vector)}d", *vector))
    reference = {"path": relative.as_posix(), "sha256": file_digest(path),
                 "format": "raw-float64-le", "shape": [len(vector)], "dtype": "float64"}
    unit = {"run_id": self.run_id, "trial_id": trial_id,
            "address": {"surface": surface, "agent_id": agent_id,
                        "address": _json_mapping(address, "address")},
            "value_ref": reference, "timestamp": timestamp}
    self._entries.append(unit)
    return unit

  def seal(self) -> dict[str, Any]:
    """核验来源实验并将采集包绑定到其根封印，不修改来源目录。"""
    if self._sealed:
      raise RuntimeError("表征工件包已经封印")
    source = self.source_run
    verify_experiment(source)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest["run_id"] != self.run_id:
      raise ValueError("表征 run_id 与来源实验不一致")
    index = {
        "schema_version": "stegopot.representations/1",
        "run_id": self.run_id,
        "capabilities": self.capabilities,
        "entries": self._entries,
    }
    index_path = self.directory / "index.json"
    with index_path.open("x", encoding="utf-8", newline="\n") as stream:
      stream.write(json.dumps(index, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    seal = {
        "schema_version": "stegopot.representation-seal/1",
        "run_id": self.run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_run_seal_sha256": file_digest(source / "seal.json"),
        "index_sha256": file_digest(index_path),
        "artifact_count": len(self._entries),
    }
    seal_path = self.directory / "representation-seal.json"
    with seal_path.open("x", encoding="utf-8", newline="\n") as stream:
      stream.write(canonical_json(seal) + "\n")
    self._sealed = True
    return seal


class RepresentationReader:
  """验证来源运行、采集包和每个工件摘要后读取向量。"""

  def __init__(self, directory: str | Path, *, source_run: str | Path) -> None:
    """初始化只读表征包；任何摘要不一致都会拒绝分析。"""
    self.directory = Path(directory).resolve()
    self.source_run = Path(source_run).resolve()
    seal = json.loads((self.directory / "representation-seal.json").read_text(encoding="utf-8"))
    if seal.get("schema_version") != "stegopot.representation-seal/1":
      raise ValueError("未知表征封印版本")
    verify_experiment(self.source_run,
                      expected_seal_sha256=seal["source_run_seal_sha256"])
    source_manifest = json.loads((self.source_run / "manifest.json").read_text(encoding="utf-8"))
    index_path = self.directory / "index.json"
    if file_digest(index_path) != seal["index_sha256"]:
      raise ValueError("表征 index.json 摘要不一致")
    self.index = json.loads(index_path.read_text(encoding="utf-8"))
    if self.index.get("schema_version") != "stegopot.representations/1":
      raise ValueError("未知表征索引版本")
    if self.index.get("run_id") != seal["run_id"]:
      raise ValueError("表征索引与封印 run_id 不一致")
    if source_manifest.get("run_id") != seal["run_id"]:
      raise ValueError("表征封印与来源实验 run_id 不一致")
    if len(self.index.get("entries", ())) != seal["artifact_count"]:
      raise ValueError("表征工件数量与封印不一致")
    for item in self.index["entries"]:
      reference = _artifact(item["value_ref"])
      path = self._artifact_path(reference)
      if file_digest(path) != reference["sha256"]:
        raise ValueError(f"表征工件摘要不一致：{reference['path']}")

  def observations(self, *, surface: str | None = None) -> Iterator[dict[str, Any]]:
    """按索引顺序返回工件引用，可按表面过滤。"""
    expected = None if surface is None else _surface(surface)
    for item in self.index["entries"]:
      address = item["address"]
      if expected is not None and address["surface"] != expected:
        continue
      yield json.loads(json.dumps(item, ensure_ascii=False, allow_nan=False))

  def read_vector(self, unit: Mapping[str, Any]) -> tuple[float, ...]:
    """验证引用后按 little-endian float64 读取一个向量。"""
    reference = _artifact(unit["value_ref"])
    if reference["format"] != "raw-float64-le" or len(reference["shape"]) != 1:
      raise ValueError("当前读取器只支持一维 raw-float64-le 工件")
    path = self._artifact_path(reference)
    if file_digest(path) != reference["sha256"]:
      raise ValueError("读取前表征工件摘要验证失败")
    data = path.read_bytes()
    expected = reference["shape"][0] * 8
    if len(data) != expected:
      raise ValueError("表征工件字节数与 shape 不一致")
    return struct.unpack(f"<{reference['shape'][0]}d", data)

  def _artifact_path(self, reference: Mapping[str, Any]) -> Path:
    """解析包内路径并拒绝目录穿越。"""
    path = (self.directory / reference["path"]).resolve()
    if not path.is_relative_to(self.directory) or not path.is_file():
      raise ValueError("表征工件路径越出采集包或不存在")
    return path


def load_representation_observations(
    readers: Sequence[RepresentationReader], *, surface: str,
) -> tuple[tuple[dict[str, Any], tuple[float, ...]], ...]:
  """从多个已验证采集包加载同一表面的向量观测。"""
  result = []
  for reader in readers:
    for unit in reader.observations(surface=surface):
      result.append((unit, reader.read_vector(unit)))
  if not result:
    raise ValueError(f"表征包不含 {_surface(surface)} 观测；unsupported 不能记为零分")
  return tuple(result)


def _identifier(value: str, name: str) -> str:
  """验证安全工件标识，不允许路径穿越。"""
  import re
  if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
    raise ValueError(f"{name} 不是有效标识")
  return value


def _surface(value: str) -> str:
  """验证标准研究表面名称。"""
  allowed = {"activation", "kv", "logits", "token", "cot", "tool", "memory",
             "timing", "behavior", "weight"}
  if value not in allowed:
    raise ValueError(f"未知研究表面：{value}")
  return value


def _json_mapping(value: Mapping[str, Any], name: str) -> dict[str, Any]:
  """复制有限 JSON 映射。"""
  if not isinstance(value, Mapping):
    raise TypeError(f"{name} 必须是映射")
  try:
    return json.loads(json.dumps(dict(value), ensure_ascii=False, allow_nan=False))
  except (TypeError, ValueError) as exc:
    raise ValueError(f"{name} 必须只包含有限 JSON 数据") from exc


def _capabilities(value: Mapping[str, Any]) -> dict[str, Any]:
  """验证采集能力声明；记录器不依赖领域层类型。"""
  copied = _json_mapping(value, "capabilities")
  if not isinstance(copied.get("provider"), str) or not copied["provider"].strip():
    raise ValueError("capabilities.provider 必须是非空字符串")
  if not isinstance(copied.get("white_box"), bool):
    raise ValueError("capabilities.white_box 必须是 bool")
  surfaces = copied.get("surfaces")
  if not isinstance(surfaces, list):
    raise ValueError("capabilities.surfaces 必须是数组")
  copied["surfaces"] = list(dict.fromkeys(_surface(item) for item in surfaces))
  internal = {"activation", "kv", "logits", "weight"}
  if not copied["white_box"] and internal.intersection(copied["surfaces"]):
    raise ValueError("非白盒能力不能声明模型内部表面")
  return copied


def _artifact(value: Mapping[str, Any]) -> dict[str, Any]:
  """验证工件引用映射。"""
  import re
  copied = _json_mapping(value, "value_ref")
  path = Path(copied.get("path", ""))
  if path.is_absolute() or ".." in path.parts:
    raise ValueError("工件引用必须是包内相对路径")
  if not re.fullmatch(r"[0-9a-f]{64}", copied.get("sha256", "")):
    raise ValueError("工件引用 SHA-256 无效")
  if not isinstance(copied.get("shape"), list) or any(
      type(item) is not int or item < 0 for item in copied["shape"]):
    raise ValueError("工件 shape 无效")
  return copied
