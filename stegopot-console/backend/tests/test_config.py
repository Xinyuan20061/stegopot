"""Console 默认路径配置测试。"""

from __future__ import annotations

from pathlib import Path

from app.config import Settings


def test_default_report_directory_points_to_repository_artifacts(
    monkeypatch,
) -> None:
  """Console 位于仓库内时应默认读取核心 artifacts/detection。"""
  monkeypatch.delenv("STEGOPOT_REPORT_DIR", raising=False)
  settings = Settings.from_environment()
  console_root = Path(__file__).resolve().parents[2]

  assert settings.report_directory == (
      console_root.parent / "artifacts" / "detection"
  ).resolve()
