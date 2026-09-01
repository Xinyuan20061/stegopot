"""文件系统实验报告仓储。"""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re
from typing import Any

REPORT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


class ReportRepositoryError(RuntimeError):
  """报告仓储操作失败。"""


class InvalidReportError(ReportRepositoryError):
  """报告内容或报告 ID 不符合要求。"""


class ReportNotFoundError(ReportRepositoryError):
  """指定报告不存在。"""


class ReportConflictError(ReportRepositoryError):
  """导入报告与已有文件冲突。"""


class ReportRepository:
  """从独立目录读取和保存 StegoPot JSON 报告。"""

  def __init__(self, directory: Path) -> None:
    """初始化仓储。

    参数：
      directory: JSON 报告所在目录；不存在时自动创建。
    """
    self._directory = directory.expanduser().resolve()
    self._directory.mkdir(parents=True, exist_ok=True)

  @property
  def directory(self) -> Path:
    """返回已规范化的报告目录。"""
    return self._directory

  def list_documents(self) -> list[tuple[str, dict[str, Any]]]:
    """读取目录中全部合法报告，损坏文件不会中断列表接口。"""
    documents: list[tuple[str, dict[str, Any]]] = []
    for path in self._directory.glob("*.json"):
      try:
        document = self._read_path(path)
        self._validate_document(document)
      except (OSError, ValueError, json.JSONDecodeError, InvalidReportError):
        continue
      documents.append((path.stem, document))
    documents.sort(
        key=lambda item: str(item[1].get("created_at") or ""),
        reverse=True,
    )
    return documents

  def load(self, report_id: str) -> dict[str, Any]:
    """根据安全报告 ID 读取一份报告。

    参数：
      report_id: 不带扩展名的报告文件 ID。
    """
    path = self._path_for_id(report_id)
    if not path.is_file():
      raise ReportNotFoundError(f"实验报告不存在：{report_id}")
    try:
      document = self._read_path(path)
      self._validate_document(document)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
      raise InvalidReportError(f"实验报告无法读取：{report_id}") from exc
    return document

  def save(
      self,
      document: Mapping[str, Any],
      *,
      overwrite: bool = False,
  ) -> str:
    """验证并原子保存一份外部导入报告。

    参数：
      document: StegoPot ExperimentReport.to_dict() 产生的标准映射。
      overwrite: 同 ID 报告存在时是否覆盖。

    返回：
      保存后的安全报告 ID。
    """
    normalized = dict(document)
    self._validate_document(normalized)
    report_id = str(normalized["run_id"]).strip()
    path = self._path_for_id(report_id)
    if path.exists() and not overwrite:
      raise ReportConflictError(f"实验报告已存在：{report_id}")
    temporary_path = path.with_suffix(".json.tmp")
    try:
      temporary_path.write_text(
          json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True),
          encoding="utf-8",
      )
      temporary_path.replace(path)
    except OSError as exc:
      raise ReportRepositoryError(f"实验报告保存失败：{report_id}") from exc
    return report_id

  def count(self) -> int:
    """返回当前能够正常读取的报告数量。"""
    return len(self.list_documents())

  def _path_for_id(self, report_id: str) -> Path:
    """校验报告 ID 并构造位于仓储目录内的路径。"""
    if not isinstance(report_id, str) or not REPORT_ID_PATTERN.fullmatch(
        report_id.strip()
    ):
      raise InvalidReportError("报告 ID 只能包含字母、数字、点、下划线和连字符")
    path = (self._directory / f"{report_id.strip()}.json").resolve()
    if path.parent != self._directory:
      raise InvalidReportError("报告路径超出仓储目录")
    return path

  @staticmethod
  def _read_path(path: Path) -> dict[str, Any]:
    """读取 UTF-8 JSON 文件并要求根节点为对象。"""
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
      raise InvalidReportError("实验报告根节点必须是 JSON 对象")
    return value

  @staticmethod
  def _validate_document(document: Mapping[str, Any]) -> None:
    """验证投影服务依赖的最小 ExperimentReport 结构。"""
    run_id = document.get("run_id")
    if not isinstance(run_id, str) or not REPORT_ID_PATTERN.fullmatch(
        run_id.strip()
    ):
      raise InvalidReportError("run_id 不是安全的非空报告 ID")
    for key in ("scenario", "result", "evaluation"):
      if not isinstance(document.get(key), Mapping):
        raise InvalidReportError(f"实验报告缺少对象字段：{key}")
