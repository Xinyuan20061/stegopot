"""前端视图投影测试。"""

from __future__ import annotations

import json

import pytest

from app.projector import ProjectionError
from app.projector import project_experiment
from tests.sample_report import build_sample_report


def test_public_view_does_not_expose_private_payloads() -> None:
  """公开视图不得包含秘密比特、解码比特或逐消息真值。"""
  view = project_experiment(build_sample_report(), scope="public")
  payload = json.dumps(view.model_dump(exclude_none=True), ensure_ascii=False)

  assert view.research is None
  assert "0101" not in payload
  for forbidden_key in ("secret_bits", "decoded_bits", "ground_truth", "outcome"):
    assert forbidden_key not in payload
  assert view.messages[1].detection is not None
  assert view.messages[1].detection.verdict == "suspicious"


def test_research_view_correlates_secret_and_decoded_bits() -> None:
  """研究视图能够按消息 ID 关联完整隐写轨迹。"""
  view = project_experiment(build_sample_report(), scope="research")

  assert view.research is not None
  trace = next(item for item in view.research.traces if item.message_id == "msg-2")
  assert trace.is_stego is True
  assert trace.secret_bits == "0101"
  assert trace.decoded_bits == "0101"
  assert trace.outcome == "true_positive"
  assert trace.complete_recovery is True


def test_invalid_report_is_rejected() -> None:
  """缺少核心结果结构的报告必须被拒绝。"""
  with pytest.raises(ProjectionError):
    project_experiment({"run_id": "broken"})
