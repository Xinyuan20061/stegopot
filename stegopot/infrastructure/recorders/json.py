"""把完整实验报告原子写入 UTF-8 JSON 文件。"""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import re
from typing import Any


class JsonExperimentRecorder:
  """按 run_id 为每次实验创建独立 JSON 报告。"""

  _SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9._-]+$")

  def __init__(
      self,
      *,
      output_dir: str | Path,
      indent: int = 2,
      ensure_ascii: bool = False,
      overwrite: bool = False,
  ) -> None:
    """初始化 JSON 记录器。

    参数：
      output_dir: 保存实验报告的目录；不存在时自动创建。
      indent: JSON 缩进空格数，必须大于或等于 0。
      ensure_ascii: 是否把非 ASCII 字符转义为 Unicode 序列。
      overwrite: 目标 run_id 已存在时是否覆盖旧报告。
    """
    if indent < 0:
      raise ValueError("indent 不能小于 0")
    self._output_dir = Path(output_dir)
    self._indent = int(indent)
    self._ensure_ascii = bool(ensure_ascii)
    self._overwrite = bool(overwrite)

  def write(self, report: Mapping[str, Any]) -> Path:
    """把一个可序列化实验报告写入独立文件。

    参数：
      report: 必须包含安全 run_id 字段的完整实验报告映射。

    返回：
      已写入 JSON 报告的绝对路径。
    """
    run_id = report.get("run_id")
    if not isinstance(run_id, str) or not self._SAFE_RUN_ID.fullmatch(run_id):
      raise ValueError(
          "report.run_id 只能包含字母、数字、点、下划线和连字符"
      )
    self._output_dir.mkdir(parents=True, exist_ok=True)
    target = self._output_dir / f"{run_id}.json"
    if target.exists() and not self._overwrite:
      raise FileExistsError(f"实验报告已经存在：{target}")
    temporary = self._output_dir / f".{run_id}.tmp"
    serialized = json.dumps(
        dict(report),
        ensure_ascii=self._ensure_ascii,
        indent=self._indent,
        sort_keys=True,
        default=str,
    )
    temporary.write_text(serialized + "\n", encoding="utf-8")
    temporary.replace(target)
    return target.resolve()
