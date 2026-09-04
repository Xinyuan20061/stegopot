"""通用审计的字段隔离、完整性、错误留痕和调用预算测试。"""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from stegopot.application.engine.runtime import RuntimeConfig
from stegopot.bootstrap.builder import MultiAgentBuilder
from stegopot.domain.interface.llm import LLMClient, LLMMessage, LLMResponse
from stegopot.domain.model.action import AgentAction
from stegopot.infrastructure.llm.audit import AuditedLLMClient, CallBudget
from stegopot.infrastructure.llm.scheduling import FixedActionPolicy
from stegopot.infrastructure.recorders.audit.integrity import file_digest, verify_audit
from stegopot.infrastructure.recorders.audit.journal import AuditJournal


class AuditJournalTest(unittest.TestCase):
  """验证双日志不会把后台研究信息投影到公开信道。"""

  def setUp(self) -> None:
    """为每个测试建立不共享的证据目录。"""
    self.temp = tempfile.TemporaryDirectory()
    self.addCleanup(self.temp.cleanup)
    self.path = Path(self.temp.name) / "trial"

  def test_projection_redaction_and_seal(self) -> None:
    """完整研究信息可审计，但凭证及私有提示词不进入公开日志。"""
    key = "fake-api-credential-for-testing"
    journal = AuditJournal(self.path, run_id="unit", redact_values=(key,))
    self.addCleanup(journal.close)
    journal.emit({"kind": "llm.request", "data": {
        "prompt": "PRIVATE-CODEBOOK", "api_key": key, "error": f"token={key}",
    }})
    journal.emit({"kind": "runtime.message", "actor": "a", "data": {
        "message": {"message_id": "m1", "sender": "a", "recipient": "b",
                    "content": "public text", "round_index": 0,
                    "metadata": {"private_target": "PRIVATE-CODEBOOK"}},
    }})
    journal.write_artifact("result.json", {"credential": key})
    journal.seal(artifacts=("result.json",))
    research = (self.path / "research.jsonl").read_text(encoding="utf-8")
    public = (self.path / "public.jsonl").read_text(encoding="utf-8")
    self.assertIn("PRIVATE-CODEBOOK", research)
    self.assertNotIn(key, research)
    self.assertNotIn(key, (self.path / "result.json").read_text(encoding="utf-8"))
    self.assertNotIn("PRIVATE-CODEBOOK", public)
    self.assertNotIn("metadata", public)
    seal = verify_audit(self.path)
    self.assertEqual(seal["streams"]["public"]["count"], 1)
    self.assertEqual(seal["streams"]["research"]["count"], 2)

  def test_modified_and_truncated_records_are_rejected(self) -> None:
    """修改、删除完整尾部事件和篡改关联报告均能被发现。"""
    journal = AuditJournal(self.path, run_id="unit")
    journal.emit({"kind": "one", "data": {"value": 1}})
    journal.emit({"kind": "two", "data": {"value": 2}})
    journal.write_artifact("result.json", {"ok": True})
    journal.seal(artifacts=("result.json",))
    path = self.path / "research.jsonl"
    original = path.read_text(encoding="utf-8")
    path.write_text(original.replace('"value":1', '"value":9'), encoding="utf-8")
    with self.assertRaises(ValueError):
      verify_audit(self.path)
    path.write_text(original.splitlines()[0] + "\n", encoding="utf-8")
    with self.assertRaises(ValueError):
      verify_audit(self.path)
    path.write_text(original, encoding="utf-8")
    (self.path / "result.json").write_text('{"ok": false}', encoding="utf-8")
    with self.assertRaises(ValueError):
      verify_audit(self.path)

  def test_external_anchor_and_no_overwrite(self) -> None:
    """外部哈希锚点可以检查封印被替换，目录与关联工件不能覆盖。"""
    journal = AuditJournal(self.path, run_id="unit")
    self.addCleanup(journal.close)
    with self.assertRaises(FileExistsError):
      AuditJournal(self.path, run_id="another")
    with self.assertRaises(ValueError):
      journal.write_artifact("../outside.json", {})
    journal.seal()
    verify_audit(self.path, expected_seal_sha256=file_digest(self.path / "seal.json"))
    with self.assertRaises(ValueError):
      verify_audit(self.path, expected_seal_sha256="f" * 64)
    with self.assertRaises(RuntimeError):
      journal.emit({"kind": "late"})

  def test_disk_failure_is_fail_closed(self) -> None:
    """首次写入失败后不可恢复成假装完整的日志。"""
    journal = AuditJournal(self.path, run_id="unit")
    self.addCleanup(journal.close)
    with patch.object(journal, "_append", side_effect=OSError("disk full")):
      with self.assertRaises(OSError):
        journal.emit({"kind": "one"})
    with self.assertRaises(RuntimeError):
      journal.emit({"kind": "two"})
    with self.assertRaises(ValueError):
      journal.seal()

  def test_partial_artifact_failure_prevents_sealing(self) -> None:
    """关联工件未完整写入时，不能继续追加或生成完整性封印。"""
    journal = AuditJournal(self.path, run_id="unit")
    self.addCleanup(journal.close)
    with self.assertRaises(ValueError):
      journal.write_artifact("partial.json", {"invalid": float("nan")})
    with self.assertRaises(RuntimeError):
      journal.emit({"kind": "later"})
    with self.assertRaises(ValueError):
      journal.seal()

  def test_partial_initialization_closes_opened_files(self) -> None:
    """第二个流创建失败时，第一个流的文件句柄也必须关闭。"""
    stream = Mock()
    with patch.object(Path, "open", side_effect=[stream, OSError("cannot open")]):
      with self.assertRaises(OSError):
        AuditJournal(self.path, run_id="unit")
    stream.close.assert_called_once()


class RuntimeAuditTest(unittest.TestCase):
  """验证审计钩子覆盖观察、动作、消息和异常且不改变路由。"""

  def test_runtime_events_and_failure(self) -> None:
    """已完成运行产生完整事件序列，非法目标产生失败终点。"""
    for target in ("b", "missing"):
      with self.subTest(target=target):
        sink = Mock()
        builder = MultiAgentBuilder()
        builder.add_node(node_id="a", role="sender", policy=FixedActionPolicy(
            AgentAction.message("hello", target=target)))
        builder.add_node(node_id="b", role="receiver", policy=FixedActionPolicy(AgentAction.wait()))
        builder.connect("a", "b")
        runtime = builder.build(config=RuntimeConfig(max_rounds=1), audit_sink=sink)
        self.addCleanup(runtime.close)
        if target == "missing":
          with self.assertRaises(ValueError):
            runtime.run("test")
        else:
          self.assertEqual(len(runtime.run("test").messages), 1)
        kinds = [call.args[0]["kind"] for call in sink.emit.call_args_list]
        self.assertEqual(kinds[0], "runtime.started")
        self.assertIn("runtime.observation", kinds)
        self.assertIn("runtime.action", kinds)
        self.assertEqual(kinds[-1], "runtime.failed" if target == "missing" else "runtime.completed")


class AuditedLLMTest(unittest.TestCase):
  """模型审计包装器保持原响应，不记录 raw 隐藏推理和鉴权字段。"""

  def test_response_allowlist_and_budget(self) -> None:
    """用量和实际模型被记录，达到预算时不会再次调用底层客户端。"""
    response = LLMResponse("actual", metadata={"model": "test-model", "usage": {"total_tokens": 7},
                                             "api_key": "not-allowed"},
                           raw={"reasoning_content": "not-audit-data"})
    client = Mock(spec=LLMClient)
    client.generate.return_value = response
    sink = Mock()
    budget = CallBudget(1)
    wrapped = AuditedLLMClient(client, audit_sink=sink, node_id="sender", budget=budget)
    self.assertIs(wrapped.generate([LLMMessage("user", "question")]), response)
    with self.assertRaises(RuntimeError):
      wrapped.generate([])
    self.assertEqual(client.generate.call_count, 1)
    serialized = json.dumps([call.args[0] for call in sink.emit.call_args_list])
    self.assertNotIn("not-audit-data", serialized)
    self.assertNotIn("not-allowed", serialized)
    self.assertEqual(budget.usage["total_tokens"], 7)

  def test_request_audit_failure_prevents_network(self) -> None:
    """请求审计失败时不发生网络请求。"""
    client = Mock(spec=LLMClient)
    sink = Mock()
    sink.emit.side_effect = OSError("cannot persist")
    wrapped = AuditedLLMClient(client, audit_sink=sink, node_id="a", budget=CallBudget(1))
    with self.assertRaises(OSError):
      wrapped.generate([])
    client.generate.assert_not_called()

  def test_model_failure_is_recorded_and_raised(self) -> None:
    """模型错误不替换为虚假成功响应。"""
    client = Mock(spec=LLMClient)
    client.generate.side_effect = TimeoutError("timeout")
    sink = Mock()
    wrapped = AuditedLLMClient(client, audit_sink=sink, node_id="a", budget=CallBudget(1))
    with self.assertRaises(TimeoutError):
      wrapped.generate([])
    self.assertEqual(sink.emit.call_args.args[0]["kind"], "llm.failed")
