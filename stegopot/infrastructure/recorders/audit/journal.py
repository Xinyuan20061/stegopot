"""双视图追加写入审计日志；每条事件立即刷盘，结束时封印。"""

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
from typing import Any

from stegopot.infrastructure.recorders.audit.integrity import canonical_json
from stegopot.infrastructure.recorders.audit.integrity import digest, file_digest
from stegopot.infrastructure.recorders.audit.projection import public_event


class AuditJournal:
  """满足 AuditSink 结构契约的文件记录器，不依赖应用层。

  日志中保留实验合成秘密供研究审计；API 密钥等基础设施凭证被脱敏。
  """

  def __init__(
      self, directory: str | Path, *, run_id: str,
      redact_values: Sequence[str] = (),
  ) -> None:
    """创建全新日志目录，绝不覆盖已有证据。

    参数：
      directory: 本次运行专用目录，必须不存在。
      run_id: 中央运行标识，不应编码私有目标。
      redact_values: 需要精确移除的凭证值；空值被忽略。
    """
    if not run_id:
      raise ValueError("run_id 不能为空")
    self.directory = Path(directory).resolve()
    self.directory.mkdir(parents=True, exist_ok=False)
    self._run_id = run_id
    self._redact_values = tuple(value for value in redact_values if value)
    self._lock = threading.RLock()
    self._closed = False
    self._failed = False
    self._streams = {}
    self._state = {}
    try:
      for scope in ("research", "public"):
        self._streams[scope] = (self.directory / f"{scope}.jsonl").open(
            "x", encoding="utf-8", newline="\n")
        self._state[scope] = {"count": 0, "head": "0" * 64}
    except Exception:
      self.close()
      raise

  def emit(self, event: Mapping[str, Any]) -> None:
    """追加事件并刷新到磁盘；event 为标准映射，写入失败直接传播。"""
    with self._lock:
      if self._closed or self._failed:
        raise RuntimeError("已关闭或写入失败的审计日志不能追加")
      clean = self._redact(dict(event))
      if not isinstance(clean.get("kind"), str):
        raise ValueError("审计事件必须包含 kind 字符串")
      try:
        self._append("research", clean)
        projected = public_event(clean)
        if projected is not None:
          self._append("public", projected)
      except Exception:
        self._failed = True
        raise

  def write_artifact(self, name: str, value: Mapping[str, Any]) -> None:
    """写入研究报告；name 必须是当前目录内的新 JSON 文件名，value 会脱敏。"""
    with self._lock:
      if self._closed or self._failed or Path(name).name != name or not name.endswith(".json"):
        raise ValueError("关联文件名称无效或日志已封印")
      try:
        with (self.directory / name).open("x", encoding="utf-8") as stream:
          json.dump(self._redact(dict(value)), stream, ensure_ascii=False, indent=2,
                    allow_nan=False)
          stream.write("\n")
          stream.flush()
          os.fsync(stream.fileno())
      except Exception:
        self._failed = True
        raise

  def seal(self, *, artifacts: Sequence[str] = ()) -> dict[str, Any]:
    """封印当前日志并关闭文件。

    参数：
      artifacts: 需要纳入完整性检查的当前目录文件名，不接受路径穿越。

    返回：
      封印内容；调用者应另行保管 seal.json 哈希作为外部锚点。
    """
    with self._lock:
      if self._closed:
        raise RuntimeError("日志已经封印")
      hashes = {}
      for name in artifacts:
        path = self.directory / name
        if Path(name).name != name or path.resolve().parent != self.directory:
          raise ValueError("关联文件不能越出日志目录")
        hashes[name] = file_digest(path)
      seal = {
          "schema_version": "1.0", "run_id": self._run_id,
          "streams": self._state, "artifacts": hashes,
      }
      self.write_artifact("seal.json", seal)
      self.close()
      return seal

  def close(self) -> None:
    """关闭文件但不伪造封印；中途崩溃留下的未封印日志仍可逐行调查。"""
    with self._lock:
      for stream in self._streams.values():
        stream.close()
      self._closed = True

  def _append(self, scope: str, event: Mapping[str, Any]) -> None:
    """追加 scope 流的 event，独立计算序号和前向哈希。"""
    state = self._state[scope]
    record = {
        "schema_version": "1.0", "run_id": self._run_id, "scope": scope,
        "seq": state["count"] + 1, "prev_hash": state["head"],
        "timestamp": datetime.now(timezone.utc).isoformat(), "event": event,
    }
    checksum = digest(record)
    stream = self._streams[scope]
    stream.write(canonical_json({**record, "hash": checksum}) + "\n")
    stream.flush()
    os.fsync(stream.fileno())
    state.update(count=record["seq"], head=checksum)

  def _redact(self, value: Any) -> Any:
    """递归移除 value 中的基础设施凭证，不删除实验私有目标。"""
    if isinstance(value, Mapping):
      sensitive = {"api_key", "authorization", "access_token", "password"}
      return {
          str(key): "[REDACTED]" if str(key).lower() in sensitive else self._redact(item)
          for key, item in value.items()
      }
    if isinstance(value, (list, tuple)):
      return [self._redact(item) for item in value]
    if isinstance(value, str):
      for secret in self._redact_values:
        value = value.replace(secret, "[REDACTED]")
      return re.sub(r"sk-[A-Za-z0-9_-]{16,}", "[REDACTED]", value)
    return value
