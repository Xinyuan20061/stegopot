"""真实 AC 算法通过新载体契约、统一管线与审计的集成测试。"""

import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from stegopot.infrastructure.recorders.audit.integrity import verify_experiment


@unittest.skipUnless(importlib.util.find_spec("torch"), "需要安装 .[stego] 本地依赖")
class StandardStegoTest(unittest.TestCase):
  """隐写接线验证采用实际算法，不调用付费模型。"""

  def test_actual_text_carrier_and_audit(self):
    """接收端从公开文本恢复比特，观察者没有比特，审计明确记录工具来源。"""
    from examples.standard_stego_demo import run_demo
    with tempfile.TemporaryDirectory() as output:
      report, directory = run_demo(output)
      self.assertEqual(report["status"], "completed", report["trials"][0]["error"])
      trial = report["trials"][0]
      self.assertEqual(trial["result"]["final_answers"]["receiver"], "01010101")
      self.assertTrue(trial["metrics"]["core.stego_metrics"]["payload_recovered"])
      self.assertEqual(report["model_calls"], 0)
      verify_experiment(directory)
      events = [json.loads(line)["event"] for line in
                (Path(directory) / "trial-0001" / "research.jsonl").read_text(encoding="utf-8").splitlines()]
      responses = [event for event in events if event["kind"] == "codec.response"]
      self.assertEqual(len(responses), 2)
      self.assertTrue(all(event["data"]["origin"] == "tool" for event in responses))
      observer = [event for event in events if event["kind"] == "runtime.observation" and event.get("actor") == "observer"]
      self.assertTrue(observer)
      self.assertNotIn("01010101", json.dumps(observer))
