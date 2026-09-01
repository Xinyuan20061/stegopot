"""导出前端读取模型的 JSON Schema。"""

from __future__ import annotations

import json
from pathlib import Path

from app.models import ExperimentView


def main() -> None:
  """把当前 Pydantic 契约写入 Console 根目录的 contracts。"""
  console_root = Path(__file__).resolve().parents[2]
  output_directory = console_root / "contracts"
  output_directory.mkdir(parents=True, exist_ok=True)
  output_path = output_directory / "experiment-view-v1.schema.json"
  output_path.write_text(
      json.dumps(
          ExperimentView.model_json_schema(),
          ensure_ascii=False,
          indent=2,
          sort_keys=True,
      ) + "\n",
      encoding="utf-8",
  )
  print(output_path)


if __name__ == "__main__":
  main()
