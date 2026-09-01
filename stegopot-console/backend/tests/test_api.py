"""报告 HTTP API 测试。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.sample_report import build_sample_report


def _client(tmp_path: Path) -> TestClient:
  """使用临时报告目录创建测试客户端。"""
  settings = Settings(
      report_directory=tmp_path / "reports",
      frontend_dist=tmp_path / "missing-dist",
      allowed_origins=("http://localhost:5173",),
  )
  return TestClient(create_app(settings))


def test_list_and_read_public_report(tmp_path: Path) -> None:
  """列表与详情接口返回同一份脱敏报告。"""
  client = _client(tmp_path)
  imported = client.post("/api/reports", json=build_sample_report())
  assert imported.status_code == 201

  listing = client.get("/api/reports")
  assert listing.status_code == 200
  assert listing.json()["total"] == 1

  response = client.get("/api/reports/sample-run")
  assert response.status_code == 200
  payload = response.json()
  assert payload["view_scope"] == "public"
  assert "research" not in payload
  assert "0101" not in json.dumps(payload)


def test_research_scope_and_import_conflict(tmp_path: Path) -> None:
  """研究范围返回真值，重复导入返回冲突。"""
  client = _client(tmp_path)
  document = build_sample_report()
  assert client.post("/api/reports", json=document).status_code == 201
  assert client.post("/api/reports", json=document).status_code == 409

  response = client.get("/api/reports/sample-run?scope=research")
  assert response.status_code == 200
  assert response.json()["research"]["traces"][1]["secret_bits"] == "0101"


def test_invalid_path_and_document_are_rejected(tmp_path: Path) -> None:
  """路径穿越和错误报告都不能进入仓储。"""
  client = _client(tmp_path)
  assert client.get("/api/reports/%2E%2E%2Fsecret").status_code in (404, 422)
  assert client.post("/api/reports", json={"run_id": "broken"}).status_code == 422
