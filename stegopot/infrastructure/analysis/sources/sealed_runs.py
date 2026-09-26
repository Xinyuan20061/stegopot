"""只从通过封印验证的实验运行提取公开文本观测。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
import json
from pathlib import Path
from typing import Any

from stegopot.domain.model.localization import CapturedObservation, ObservationAddress, SurfaceKind
from stegopot.infrastructure.recorders.audit.integrity import digest, file_digest, verify_experiment
from stegopot.infrastructure.recorders.audit.reader import AuditReader


def resolve_run_directories(target: str | Path) -> tuple[Path, ...]:
  """解析单个运行、运行组目录或含 runs 数组的 JSON 清单。"""
  path = Path(target).expanduser().resolve()
  if path.is_file():
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("runs"), list):
      raise ValueError("运行组清单必须包含 runs 数组")
    runs = tuple((path.parent / item).resolve() if not Path(item).is_absolute()
                 else Path(item).resolve() for item in value["runs"])
  elif (path / "seal.json").is_file():
    runs = (path,)
  elif path.is_dir():
    runs = tuple(sorted(item.resolve() for item in path.iterdir()
                        if item.is_dir() and (item / "seal.json").is_file()))
  else:
    raise ValueError("运行目标不存在")
  if not runs:
    raise ValueError("没有发现封印运行目录")
  for run in runs:
    verify_experiment(run)
  return runs


def run_provenance(run_directories: Sequence[Path]) -> tuple[dict[str, str], ...]:
  """返回来源运行 ID、路径和根封印摘要。"""
  result = []
  for directory in run_directories:
    verify_experiment(directory)
    report = json.loads((directory / "experiment-report.json").read_text(encoding="utf-8"))
    result.append({"run_id": report["run_id"], "directory": str(directory),
                   "seal_sha256": file_digest(directory / "seal.json")})
  return tuple(result)


def load_public_text_observations(
    run_directories: Sequence[Path],
    *,
    agent_id: str | None = None,
    recipient: str | None = None,
    rounds: Sequence[int] | None = None,
    flow_order: float | None = None,
) -> tuple[CapturedObservation, ...]:
  """从公开 runtime.message 事件构造跨 Trial 稳定的文本地址。

  参数：
    run_directories: 已解析的标准运行目录；每个目录会再次核验。
    agent_id: 可选发送 Agent 过滤条件。
    recipient: 可选接收 Agent 过滤条件。
    rounds: 可选同步轮次允许列表。
    flow_order: 可选跨表面预注册顺序，只用于路径边，不进入文本特征。

  返回：
    不含中央秘密标签的文本观测。消息 ID 不进入地址，避免把样本身份当特征。
  """
  allowed_rounds = None if rounds is None else {int(item) for item in rounds}
  observations = []
  for directory in run_directories:
    verify_experiment(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    run_id = manifest["run_id"]
    context = {
        item["trial_id"]: digest({
            "task": item.get("task"), "shared_context": item.get("shared_context", {}),
            "nodes": item.get("nodes", ()),
            "edges": item.get("edges", ()),
            "substrate": item.get("substrate", {}),
        }) for item in manifest["plan"]["trials"]
    }
    counters: dict[tuple[str, str, str, int], int] = defaultdict(int)
    reader = AuditReader(directory, verify=True)
    for record in reader.events(scope="public", kind="runtime.message"):
      message = record["event"]["data"]["message"]
      sender = message["sender"]
      target = message["recipient"]
      round_index = int(message["round_index"])
      if agent_id is not None and sender != agent_id:
        continue
      if recipient is not None and target != recipient:
        continue
      if allowed_rounds is not None and round_index not in allowed_rounds:
        continue
      trial_id = record["run_id"]
      key = (trial_id, sender, target, round_index)
      index = counters[key]
      counters[key] += 1
      location = {"recipient": target, "round": round_index, "message_index": index}
      if flow_order is not None:
        location["flow_order"] = float(flow_order)
      address = ObservationAddress(
          SurfaceKind.TOKEN,
          sender,
          location,
      )
      observations.append(CapturedObservation(
          run_id, trial_id, address, message["content"],
          {"context_fingerprint": context.get(trial_id)},
      ))
  if not observations:
    raise ValueError("过滤后没有公开文本观测")
  return tuple(observations)


def assert_runs_unchanged(provenance: Sequence[dict[str, str]]) -> None:
  """分析写出后重新核验来源，确保离线流程未修改原始运行。"""
  for item in provenance:
    directory = Path(item["directory"])
    verify_experiment(directory, expected_seal_sha256=item["seal_sha256"])
