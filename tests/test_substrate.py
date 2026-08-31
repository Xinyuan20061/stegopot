"""Substrate、StegoKit 适配器和运行器接线的离线测试。"""

from __future__ import annotations

import dataclasses
import json
from types import SimpleNamespace
import unittest
from unittest import mock

from stegopot.application.engine import AgentNode
from stegopot.application.engine import MessageRouter
from stegopot.application.engine import MultiAgentRuntime
from stegopot.application.engine import RuntimeConfig
from stegopot.domain.model import AgentAction
from stegopot.domain.model import AgentMessage
from stegopot.domain.model import AgentTopology
from stegopot.infrastructure.integrations.stegokit import StegoKitAdapter
from stegopot.infrastructure.integrations.stegokit import bundled_stegokit_path
from stegopot.domain.interface import Policy
from stegopot.domain.interface import StegoEmbedRequest
from stegopot.domain.interface import StegoEmbedResult
from stegopot.domain.interface import StegoExtractRequest
from stegopot.domain.interface import StegoExtractResult
from stegopot.domain.interface import StegoGenerationConfig
from stegopot.domain.interface import SubstrateResetContext
from stegopot.domain.interface import SubstrateStepContext
from stegopot.infrastructure.substrates import CommunicationSubstrate
from stegopot.infrastructure.substrates.stego import SteganographySubstrate


class RecordingPolicy(Policy[int]):
  """按顺序返回动作并记录所有观察的测试策略。"""

  def __init__(self, actions: list[AgentAction]) -> None:
    """初始化测试策略。

    参数：
      actions: 每次 step 按顺序返回的动作列表。
    """
    self._actions = tuple(actions)
    self.observations: list[object] = []

  def initial_state(self) -> int:
    """返回第一条动作的索引。"""
    return 0

  def step(self, observation, prev_state: int):
    """记录观察并返回当前索引对应的动作。"""
    self.observations.append(observation)
    if prev_state >= len(self._actions):
      return AgentAction.wait(), prev_state + 1
    return self._actions[prev_state], prev_state + 1


class FakeStegoTool:
  """不依赖模型和 GPU 的确定性隐写工具。"""

  def __init__(self) -> None:
    """初始化请求记录和关闭状态。"""
    self.embed_requests: list[StegoEmbedRequest] = []
    self.extract_requests: list[StegoExtractRequest] = []
    self.closed = False

  def embed(self, request: StegoEmbedRequest) -> StegoEmbedResult:
    """返回固定载密文本和 token ID。"""
    self.embed_requests.append(request)
    return StegoEmbedResult(
        text="这是一条载密公开文本",
        generated_token_ids=[11, 22, 33],
        consumed_bits=len(request.secret_bits),
        encode_time_seconds=0.1,
        embedding_capacity=1.5,
        metadata={"fake": True},
    )

  def extract(self, request: StegoExtractRequest) -> StegoExtractResult:
    """返回与测试秘密一致的固定解码结果。"""
    self.extract_requests.append(request)
    return StegoExtractResult(
        bits="0101",
        decode_time_seconds=0.05,
        metadata={"fake": True},
    )

  def close(self) -> None:
    """记录工具已经关闭。"""
    self.closed = True


class DecodeFailureStegoTool(FakeStegoTool):
  """编码成功但解码失败的测试隐写工具。"""

  def extract(self, request: StegoExtractRequest) -> StegoExtractResult:
    """模拟接收端解码异常。"""
    self.extract_requests.append(request)
    raise RuntimeError("decode failed")


class CommunicationSubstrateTest(unittest.TestCase):
  """默认透明通信环境测试。"""

  def test_default_substrate_delivers_messages_and_records_events(self) -> None:
    """验证默认环境不修改消息，并产生零奖励和投递事件。"""
    substrate = CommunicationSubstrate()
    substrate.reset(SubstrateResetContext(
        task="测试普通通信",
        node_ids=("a", "b"),
        topology={"nodes": ["a", "b"], "edges": [["a", "b"]]},
    ))
    message = AgentMessage(
        message_id="msg-000001",
        sender="a",
        recipient="b",
        content="hello",
        round_index=0,
    )

    result = substrate.step(SubstrateStepContext(
        round_index=0,
        actions={"a": AgentAction.message("hello", target="b")},
        messages=(message,),
    ))

    self.assertEqual(result.messages, (message,))
    self.assertEqual(dict(result.rewards), {"a": 0.0, "b": 0.0})
    self.assertEqual(result.events[0].kind, "message_delivered")
    self.assertEqual(substrate.observe("b")["delivered_message_count"], 1)


class SteganographySubstrateTest(unittest.TestCase):
  """隐写消息变换、解码权限和状态隔离测试。"""

  def test_broadcast_embeds_once_and_only_decoder_sees_bits(self) -> None:
    """验证一次广播只编码一次，且秘密不会进入公开消息元数据。"""
    tool = FakeStegoTool()
    substrate = SteganographySubstrate(
        tool=tool,
        decoder_nodes={"receiver"},
    )
    nodes = ("sender", "receiver", "auditor")
    substrate.reset(SubstrateResetContext(
        task="测试隐写广播",
        node_ids=nodes,
        topology={"nodes": list(nodes)},
    ))
    action = AgentAction.message(
        "围绕隐私生成一句话",
        target="*",
        metadata={
            "stego": {
                "algorithm": "ac",
                "secret_bits": "0101",
                "generation": {
                    "max_new_tokens": 32,
                    "temperature": 1.0,
                    "top_k": 20,
                    "precision": 16,
                },
            }
        },
    )
    topology = AgentTopology(nodes)
    topology.connect("sender", "receiver")
    topology.connect("sender", "auditor")
    routed = MessageRouter(topology).route(
        sender="sender",
        action=action,
        round_index=0,
    )

    result = substrate.step(SubstrateStepContext(
        round_index=0,
        actions={"sender": action},
        messages=routed,
    ))

    self.assertEqual(len(tool.embed_requests), 1)
    self.assertEqual(len(tool.extract_requests), 1)
    self.assertEqual(len(result.messages), 2)
    self.assertTrue(all(
        message.content == "这是一条载密公开文本"
        for message in result.messages
    ))
    public_metadata = json.dumps(
        result.messages[0].to_dict(), ensure_ascii=False
    )
    self.assertNotIn("secret_bits", public_metadata)
    self.assertNotIn("stego", public_metadata)
    embedded_event = next(
        event for event in result.events if event.kind == "stego_embedded"
    )
    self.assertEqual(
        list(embedded_event.metadata["generated_token_ids"]),
        [11, 22, 33],
    )
    receiver_private = substrate.observe("receiver")["steganography"]
    auditor_private = substrate.observe("auditor")["steganography"]
    self.assertEqual(receiver_private["decoded_messages"][0]["bits"], "0101")
    self.assertEqual(auditor_private["decoded_messages"], [])
    self.assertNotIn("0101", json.dumps(substrate.state()))

  def test_runtime_exposes_substrate_observation_and_records_state(self) -> None:
    """验证 Runtime 会把环境观察交给节点并保存环境结果。"""
    sender_policy = RecordingPolicy([
        AgentAction.message(
            "生成载密文本",
            target="receiver",
            metadata={
                "stego": {
                    "algorithm": "ac",
                    "secret_bits": "0101",
                }
            },
        ),
        AgentAction.final_answer("sender done"),
    ])
    receiver_policy = RecordingPolicy([
        AgentAction.wait(),
        AgentAction.final_answer("receiver done"),
    ])
    topology = AgentTopology(("sender", "receiver"))
    topology.connect("sender", "receiver")
    substrate = SteganographySubstrate(
        tool=FakeStegoTool(),
        decoder_nodes={"receiver"},
    )
    runtime = MultiAgentRuntime(
        nodes={
            "sender": AgentNode(
                node_id="sender", role="sender", policy=sender_policy
            ),
            "receiver": AgentNode(
                node_id="receiver", role="receiver", policy=receiver_policy
            ),
        },
        topology=topology,
        substrate=substrate,
        config=RuntimeConfig(max_rounds=2, termination_mode="all_final"),
    )

    result = runtime.run("完成一次隐写通信")

    second_observation = receiver_policy.observations[1]
    decoded = second_observation["environment"]["steganography"]
    self.assertEqual(decoded["decoded_messages"][0]["bits"], "0101")
    self.assertEqual(result.messages[0].content, "这是一条载密公开文本")
    self.assertEqual(result.substrate_state["encoded_message_count"], 1)
    self.assertIn("stego_embedded", {
        event.kind for event in result.substrate_events
    })
    json.dumps(result.to_dict(), ensure_ascii=False)

  def test_non_strict_decode_failure_delivers_only_one_safe_message(self) -> None:
    """验证解码失败不会重复投递，也不会把秘密请求发送给节点。"""
    substrate = SteganographySubstrate(
        tool=DecodeFailureStegoTool(),
        decoder_nodes={"receiver"},
        fail_fast=False,
    )
    substrate.reset(SubstrateResetContext(
        task="测试非严格解码失败",
        node_ids=("sender", "receiver"),
    ))
    action = AgentAction.message(
        "生成文本",
        target="receiver",
        metadata={"stego": {"secret_bits": "0101"}},
    )
    message = AgentMessage(
        message_id="msg-000001",
        sender="sender",
        recipient="receiver",
        content="生成文本",
        round_index=0,
        metadata=action.metadata,
    )

    result = substrate.step(SubstrateStepContext(
        round_index=0,
        actions={"sender": action},
        messages=(message,),
    ))

    self.assertEqual(len(result.messages), 1)
    self.assertEqual(result.messages[0].content, "这是一条载密公开文本")
    self.assertNotIn("stego", result.messages[0].metadata)
    self.assertEqual(
        [event.kind for event in result.events].count("stego_error"),
        1,
    )


@dataclasses.dataclass(frozen=True)
class FakeAlgorithmConfig:
  """验证字典配置转换的假 StegoKit Config。"""

  level: int = 1


@dataclasses.dataclass(frozen=True)
class FakeNoMaterial:
  """验证空密码材料转换的假 StegoKit Material。"""


class FakeRegistry:
  """提供 StegoKit AlgorithmSpec 所需字段的假注册表。"""

  def get_spec(self, algorithm: str):
    """返回与测试算法对应的 Config 和 Material 类型。"""
    del algorithm
    return SimpleNamespace(
        encode_config_type=FakeAlgorithmConfig,
        decode_config_type=FakeAlgorithmConfig,
        encode_material_type=FakeNoMaterial,
        decode_material_type=FakeNoMaterial,
    )


class FakeDispatcher:
  """记录 adapter 传入参数的假 StegoDispatcher。"""

  def __init__(self) -> None:
    """初始化注册表和调用记录。"""
    self.registry = FakeRegistry()
    self.embed_kwargs = None
    self.extract_kwargs = None

  def embed(self, **kwargs):
    """记录编码参数并返回 StegoKit 形状的结果对象。"""
    self.embed_kwargs = kwargs
    return SimpleNamespace(
        text="cover text",
        generated_token_ids=[7, 8],
        consumed_bits=4,
        encode_time_seconds=0.2,
        embedding_capacity=2.0,
        metadata={"source": "fake-dispatcher"},
    )

  def extract(self, **kwargs):
    """记录解码参数并返回 StegoKit 形状的结果对象。"""
    self.extract_kwargs = kwargs
    return SimpleNamespace(
        bits="0101",
        decode_time_seconds=0.1,
        metadata={"source": "fake-dispatcher"},
    )


class StegoKitAdapterTest(unittest.TestCase):
  """本项目请求到 StegoKit 官方便利接口的映射测试。"""

  @mock.patch("stegopot.infrastructure.integrations.stegokit.adapter.load_stegokit")
  def test_adapter_creates_dispatcher_from_bundled_tool(
      self,
      load_stegokit_mock: mock.Mock,
  ) -> None:
    """验证适配器通过统一加载器创建项目内工具 dispatcher。

    参数：
      load_stegokit_mock: 被替换的项目内 StegoKit 加载函数。
    """
    dispatcher = object()
    dispatcher_factory = mock.Mock(return_value=dispatcher)
    load_stegokit_mock.return_value = SimpleNamespace(
        StegoDispatcher=dispatcher_factory,
    )

    adapter = StegoKitAdapter(
        model=object(),
        tokenizer=object(),
        verbose=True,
    )

    self.assertIs(adapter._dispatcher, dispatcher)
    dispatcher_factory.assert_called_once_with(verbose=True)

  def test_adapter_maps_embed_and_extract_arguments(self) -> None:
    """验证模型、生成参数、Config、Material 和 token ID 的映射。"""
    dispatcher = FakeDispatcher()
    model = object()
    tokenizer = object()
    adapter = StegoKitAdapter(
        model=model,
        tokenizer=tokenizer,
        dispatcher=dispatcher,
    )
    generation = StegoGenerationConfig(
        max_new_tokens=64,
        temperature=0.8,
        top_k=32,
        top_p=0.9,
        precision=16,
        stop_on_eos=True,
    )
    embed_result = adapter.embed(StegoEmbedRequest(
        algorithm="fake",
        secret_bits="0101",
        messages=[{"role": "user", "content": "生成文本"}],
        generation=generation,
        config={"level": 3},
        material={},
    ))
    extract_result = adapter.extract(StegoExtractRequest(
        algorithm="fake",
        generated_token_ids=embed_result.generated_token_ids,
        messages=[{"role": "user", "content": "生成文本"}],
        generation=generation,
        max_bits=embed_result.consumed_bits,
        config={"level": 3},
        material={},
    ))

    self.assertIs(dispatcher.embed_kwargs["model"], model)
    self.assertIs(dispatcher.embed_kwargs["tokenizer"], tokenizer)
    self.assertEqual(dispatcher.embed_kwargs["secret_bits"], "0101")
    self.assertEqual(dispatcher.embed_kwargs["max_new_tokens"], 64)
    self.assertEqual(dispatcher.embed_kwargs["precision"], 16)
    self.assertIsInstance(
        dispatcher.embed_kwargs["config"], FakeAlgorithmConfig
    )
    self.assertIsInstance(
        dispatcher.embed_kwargs["material"], FakeNoMaterial
    )
    self.assertEqual(dispatcher.extract_kwargs["generated_token_ids"], [7, 8])
    self.assertEqual(dispatcher.extract_kwargs["max_bits"], 4)
    self.assertEqual(extract_result.bits, "0101")


class BundledStegoKitTest(unittest.TestCase):
  """项目内置 StegoKit 工具仓库的结构测试。"""

  def test_bundled_stegokit_source_is_available(self) -> None:
    """验证子模块包含可由加载器使用的 Python 包入口。"""
    repository = bundled_stegokit_path()

    self.assertTrue((repository / "pyproject.toml").is_file())
    self.assertTrue((repository / "stegokit" / "__init__.py").is_file())


if __name__ == "__main__":
  unittest.main()
