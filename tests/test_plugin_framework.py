"""插件接口、数据隔离、配置预检和标准报告的回归测试。"""

from dataclasses import dataclass, field, replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from stegopot.bootstrap.experiments.builtin import builtin_plugin
from stegopot.bootstrap.experiments.prepare import prepare_experiment
from stegopot.bootstrap.experiments.run import run_experiment
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.interface.plugin import ComponentDefinition, PluginDefinition
from stegopot.domain.interface.codec import Carrier, EncodeRequest, DecodeRequest
from stegopot.domain.interface.stego import StegoEmbedResult, StegoExtractResult
from stegopot.domain.interface.llm import LLMClient, LLMResponse
from stegopot.domain.model.experiment import ComponentSpec
from stegopot.infrastructure.plugins.catalog import PluginCatalog
from stegopot.infrastructure.settings.experiment import load_config
from stegopot.infrastructure.recorders.audit.integrity import verify_experiment
from stegopot.infrastructure.integrations.stegokit.codec import StegoKitCodec


def basic():
  """返回独立的最小双节点配置，修改测试副本不会影响其他用例。"""
  return {"schema_version": "1", "scenario": {"type": "core.explicit", "config": {
      "task": "test", "nodes": [
          {"id": "sender", "policy": {"type": "core.scripted", "config": {
              "actions": [{"kind": "message", "target": "receiver", "content": "public"}]}}},
          {"id": "receiver", "policy": {"type": "core.echo"}}],
      "edges": [["sender", "receiver"]], "max_rounds": 2,
      "node_contexts": {"sender": {"secret": "ONLY_SENDER"}},
      "truth": {"label": "ONLY_RESEARCHER"}}}}


def catalog_with(plugin):
  """为 plugin 建立全新注册表，不改变全局导入状态。"""
  catalog = PluginCatalog(builtin_plugin())
  catalog.add(plugin())
  return catalog


class PluginFrameworkTest(unittest.TestCase):
  """验证运行状态、声明式注册和审计边界。"""

  def test_core_config_run_repeat_and_tamper(self):
    """每次运行实例隔离，报告与子日志可验，篡改会失败。"""
    with tempfile.TemporaryDirectory() as output:
      prepared = prepare_experiment(basic())
      first, directory = run_experiment(prepared, output=output)
      second, other = run_experiment(prepared, output=output)
      self.assertEqual(first["status"], "completed")
      self.assertNotEqual(directory, other)
      self.assertEqual(second["trials"][0]["result"]["final_answers"]["receiver"], "public")
      verify_experiment(directory)
      research = [json.loads(line)["event"] for line in (directory / "trial-0001" / "research.jsonl").read_text(encoding="utf-8").splitlines()]
      observations = [event for event in research if event["kind"] == "runtime.observation"]
      self.assertTrue(observations)
      receiver = [event for event in observations if event.get("actor") == "receiver"]
      self.assertNotIn("ONLY_SENDER", json.dumps(receiver))
      self.assertNotIn("ONLY_RESEARCHER", json.dumps(observations))
      self.assertNotIn("ONLY_SENDER", (directory / "trial-0001" / "public.jsonl").read_text(encoding="utf-8"))
      (directory / "report.md").write_text("tamper", encoding="utf-8")
      with self.assertRaises(ValueError):
        verify_experiment(directory)

  def test_decorator_dataclass_and_duplicate(self):
    """参数自动成文、默认值自动构造、重复 ID 和导出后注册均拒绝。"""
    @dataclass
    class Config:
      count: int = field(default=2, metadata={"description": "节点奖励分值"})
    plugin = Plugin("demo", "0.1.0")
    @plugin.component("reward", "constant", config=Config)
    def reward(config, context):
      """将 config 的分值接入奖励对象，context 未使用。"""
      return Mock(score=lambda transition: {"sender": config.count})
    with self.assertRaises(ValueError):
      plugin.component("reward", "constant")(reward)
    catalog = catalog_with(plugin)
    definition = catalog.validate(ComponentSpec("demo.constant"), "reward")
    self.assertEqual(definition.config_schema["properties"]["count"]["description"], "节点奖励分值")
    with self.assertRaises(RuntimeError):
      plugin.component("reward", "late")(reward)
    value = basic()
    value["rewards"] = [{"type": "demo.constant", "config": {"count": 3}}]
    with tempfile.TemporaryDirectory() as output:
      report, _ = run_experiment(prepare_experiment(value, catalog=catalog), output=output)
      self.assertEqual(report["status"], "completed")
    with self.assertRaises(ValueError):
      catalog.validate(ComponentSpec("demo.constant", {"count": "bad"}), "reward")

  def test_config_failures_before_resources(self):
    """未知字段、拓扑越界、未启用插件和缺少资源在调用前被拒绝。"""
    invalid = []
    value = basic()
    value["unknown"] = True
    invalid.append(value)
    value = basic()
    value["topology"] = {"edges": [["sender", "missing"]]}
    invalid.append(value)
    value = basic()
    value["channels"] = [{"type": "missing.channel"}]
    invalid.append(value)
    value = basic()
    value["policies"] = {"sender": {"type": "core.llm", "config": {"client": "missing"}}}
    invalid.append(value)
    value = basic()
    value["audit"] = {"required": False}
    invalid.append(value)
    for value in invalid:
      with self.subTest(value=value), self.assertRaises(ValueError):
        prepare_experiment(value)

  def test_duplicate_and_unsafe_yaml_rejected(self):
    """禁止重复键、别名和 YAML 对象构造标签。"""
    with tempfile.TemporaryDirectory() as output:
      for text in ("a: 1\na: 2", "a: &x [1]\nb: *x", "!!python/object/apply:os.system ['echo bad']"):
        path = Path(output) / "bad.yaml"
        path.write_text(text, encoding="utf-8")
        with self.assertRaises(Exception):
          load_config(path)
      path = Path(output) / "bad.json"
      path.write_text('{"schema_version":"1","schema_version":"2"}', encoding="utf-8")
      with self.assertRaises(ValueError):
        load_config(path)

  def test_channel_block_and_identity_validation(self):
    """正文阻断是合法干预，改变接收者则失败并保留日志。"""
    plugin = Plugin("demo", "0.1.0")
    @plugin.component("channel", "reroute")
    def reroute(config, context):
      """返回故意违反身份约束的测试信道。"""
      return Mock(transform=lambda message: replace(message, recipient="sender"))
    for channel, status, count in (({"type": "core.block"}, "completed", 0),
                                    ({"type": "demo.reroute"}, "failed", 0)):
      value = basic()
      value["channels"] = [channel]
      with tempfile.TemporaryDirectory() as output:
        report, directory = run_experiment(prepare_experiment(value, catalog=catalog_with(plugin)), output=output)
        self.assertEqual(report["status"], status)
        self.assertEqual(len(report["trials"][0]["result"].get("messages", [])), count)
        verify_experiment(directory)

  def test_detector_gets_public_only_and_resource_scope(self):
    """检测器没有中央标签，工厂不能索取未声明资源。"""
    plugin = Plugin("demo", "0.1.0")
    detector = Mock()
    from stegopot.domain.model.detection import DetectionResult
    detector.detect.side_effect = lambda request: DetectionResult(
        request.message_id, "demo", False, 0.0)
    @plugin.component("detector", "capture")
    def factory(config, context):
      """记录 config 工厂只获得 context 中声明的能力。"""
      with self.assertRaises(PermissionError):
        context.resource("unlisted")
      with self.assertRaises(PermissionError):
        context.credential("DEEPSEEK_API_KEY")
      return detector
    value = basic()
    value["detectors"] = [{"type": "demo.capture"}]
    with tempfile.TemporaryDirectory() as output:
      report, _ = run_experiment(prepare_experiment(value, catalog=catalog_with(plugin)), output=output)
      self.assertEqual(report["status"], "completed")
    request = detector.detect.call_args.args[0]
    self.assertEqual(request.content, "public")
    self.assertEqual(dict(request.context), {})
    self.assertEqual(dict(request.metadata), {})
    detector.close.assert_called_once()

  def test_model_budget_failure_and_resource_close(self):
    """统一预算在请求前生效，失败试验封印，所有原始客户端只关闭一次。"""
    plugin = Plugin("demo", "0.1.0")
    client = Mock(spec=LLMClient)
    client.generate.return_value = LLMResponse('{"kind":"wait"}')
    @plugin.component("llm", "client")
    def factory(config, context):
      """返回可追踪的测试客户端。"""
      return client
    value = basic()
    value["resources"] = {"model": {"type": "demo.client"}}
    value["policies"] = {"sender": {"type": "core.llm", "config": {"client": "model"}}}
    value["runtime"] = {"max_model_calls": 2, "max_output_tokens": 7}
    with tempfile.TemporaryDirectory() as output:
      report, _ = run_experiment(prepare_experiment(value, catalog=catalog_with(plugin)), output=output)
      self.assertEqual(report["model_calls"], 2)
      self.assertEqual(client.generate.call_args.kwargs["max_tokens"], 7)
      client.close.assert_called_once()
    value["runtime"]["max_model_calls"] = 1
    with self.assertRaises(ValueError):
      prepare_experiment(value, catalog=catalog_with(plugin))

  def test_api_mismatch_and_duplicate_plugin(self):
    """插件版本冲突不能悄悄覆盖现有实现。"""
    catalog = PluginCatalog(builtin_plugin())
    with self.assertRaises(ValueError):
      catalog.add(PluginDefinition("demo", "0.1.0", "2.0", ()))
    with self.assertRaises(ValueError):
      catalog.add(builtin_plugin())

  def test_prepared_catalog_is_frozen(self):
    """预检完成后不能偷偷修改本次运行的插件清单。"""
    prepared = prepare_experiment(basic())
    with self.assertRaises(RuntimeError):
      prepared.catalog.add(PluginDefinition('later', '0.1.0', '1.0', ()))

  def test_missing_credentials_preflight(self):
    """仅声明环境变量引用，缺少凭证时不构造供应商对象。"""
    factory = Mock()
    catalog = PluginCatalog(builtin_plugin())
    catalog.add(PluginDefinition('demo', '0.1.0', '1.0', (
        ComponentDefinition('demo.private', 'llm', factory, {
            'type': 'object', 'additionalProperties': False,
            'properties': {'api_key_env': {'type': 'string'}}, 'required': ['api_key_env']},
            credentials=('api_key_env',)),)))
    value = basic()
    value['resources'] = {'model': {'type': 'demo.private', 'config': {'api_key_env': 'TEST_API_KEY'}}}
    value['policies'] = {'sender': {'type': 'core.llm', 'config': {'client': 'model'}}}
    with self.assertRaises(ValueError):
      prepare_experiment(value, catalog=catalog, environment={})
    factory.assert_not_called()

  def test_core_import_without_optional_components(self):
    """核心启动不导入实验插件、DeepSeek 或重型模型库。"""
    import subprocess
    import sys
    code = '''import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
  def find_spec(self, fullname, path=None, target=None):
    if fullname.split('.')[0] in {'torch', 'transformers', 'stegopot_collusion', 'stegopot_deepseek'}:
      raise RuntimeError(fullname)
sys.meta_path.insert(0, Block())
from stegopot.bootstrap.experiments.builtin import builtin_plugin
assert any(item.component_id == 'core.stegokit' for item in builtin_plugin().components)
'''
    result = subprocess.run([sys.executable, '-I', '-c', code], capture_output=True, text=True)
    self.assertEqual(result.returncode, 0, result.stderr)

  def test_audit_failure_stops_run(self):
    """宿主审计写入失败不能继续生成完整成功报告。"""
    with tempfile.TemporaryDirectory() as output, patch(
        "stegopot.bootstrap.experiments.run.AuditJournal.emit", side_effect=OSError("disk")):
      with self.assertRaises(OSError):
        run_experiment(prepare_experiment(basic()), output=output)
      self.assertFalse(list(Path(output).rglob("seal.json")))


class CarrierCodecTest(unittest.TestCase):
  """新接口必须依赖实际载体，不偷用编码端 token ID。"""

  def test_received_text_is_retokenized(self):
    """修改接收文本会改变实际传给工具的 token 序列。"""
    adapter, tokenizer = Mock(), Mock()
    tokenizer.encode.side_effect = lambda text, **kwargs: [1] if text == "cover" else [2]
    adapter.embed.return_value = StegoEmbedResult("cover", [1], 2)
    adapter.extract.return_value = StegoExtractResult("01")
    codec = StegoKitCodec(adapter=adapter, tokenizer=tokenizer)
    shared = {"messages": [{"role": "user", "content": "prompt"}]}
    encoded = codec.encode(EncodeRequest("01", Carrier("prompt"), shared))
    self.assertEqual(encoded.carrier.content, "cover")
    self.assertNotIn("generated_token_ids", encoded.research)
    codec.decode(DecodeRequest(Carrier("changed"), shared))
    self.assertEqual(adapter.extract.call_args.args[0].generated_token_ids, (2,))

  def test_non_roundtrip_tokenizer_fails_explicitly(self):
    """文本无法恢复原 token 则显式失败，不给接收者额外内部数据。"""
    adapter, tokenizer = Mock(), Mock()
    adapter.embed.return_value = StegoEmbedResult("cover", [1], 2)
    tokenizer.encode.return_value = [2]
    codec = StegoKitCodec(adapter=adapter, tokenizer=tokenizer)
    with self.assertRaises(ValueError):
      codec.encode(EncodeRequest("01", Carrier("prompt")))
