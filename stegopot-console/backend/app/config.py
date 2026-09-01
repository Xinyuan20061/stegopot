"""后端路径和跨域设置。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
  """Console 后端运行配置。

  属性：
    report_directory: StegoPot 生成的 JSON 实验报告目录。
    frontend_dist: 前端生产构建目录；存在时由后端直接托管。
    allowed_origins: 允许访问 API 的前端开发地址。
  """

  report_directory: Path
  frontend_dist: Path
  allowed_origins: tuple[str, ...]

  @classmethod
  def from_environment(cls) -> "Settings":
    """读取环境变量并生成默认配置。"""
    console_root = Path(__file__).resolve().parents[2]
    default_reports = console_root.parent / "artifacts" / "detection"
    configured_reports = os.environ.get("STEGOPOT_REPORT_DIR", "").strip()
    origins = tuple(
        item.strip()
        for item in os.environ.get(
            "STEGOPOT_CONSOLE_ORIGINS",
            "http://127.0.0.1:5173,http://localhost:5173",
        ).split(",")
        if item.strip()
    )
    return cls(
        report_directory=Path(configured_reports).expanduser().resolve()
        if configured_reports
        else default_reports.resolve(),
        frontend_dist=(console_root / "frontend" / "dist").resolve(),
        allowed_origins=origins,
    )
