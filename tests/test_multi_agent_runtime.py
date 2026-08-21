"""自定义拓扑多智能体运行框架测试。"""

from __future__ import annotations

import json
import unittest

from meltingpot.utils.llm import MockLLMClient
from meltingpot.utils.multi_agent import AgentNode
from meltingpot.utils.multi_agent import AgentTopology
from meltingpot.utils.multi_agent import MessageRouter
from meltingpot.utils.multi_agent import MessageRoutingError
from meltingpot.utils.multi_agent import MultiAgentBuilder
from meltingpot.utils.multi_agent import MultiAgentRuntime
from meltingpot.utils.multi_agent import RuntimeConfig
from meltingpot.utils.policies import AgentAction
from meltingpot.utils.policies import Policy


class ScriptedPolicy(Policy[int]):
  """按顺序返回预设动作、并保存收到的观察。"""

  def __init__(self, actions: list[AgentAction]) -> None:
    """初始化脚本策略。

    参数：
      actions: 每次 step 按顺序返回的动作；耗尽后返回 wait。
    """
    self.actions = tuple(actions)
    self.observations: list[object] = []

  def initial_state(self) -> int:
    """返回指向第一条预设动作的索引。"""
    return 0

  def step(self, observation, prev_state: int):
    """保存观察并返回当前索引对应的动作。"""
    self.observations.append(observation)
    if prev_state >= len(self.actions):
      return AgentAction.wait(), prev_state + 1
    return self.actions[prev_state], prev_state + 1


class TopologyTest(unittest.TestCase):
  """通信拓扑测试。"""

  def test_custom_directed_topology_preserves_edge_direction(self) -> None:
    """验证自定义边只允许指定方向通信。"""
    topology = AgentTopology(("a", "b", "c"))
    topology.connect("a", "b").connect("b", "c")

    self.assertTrue(topology.can_send("a", "b"))
    self.assertFalse(topology.can_send("b", "a"))
    self.assertEqual(topology.outgoing_neighbors("b"), ("c",))
    self.assertEqual(topology.incoming_neighbors("b"), ("a",))

  def test_predefined_topologies_are_available(self) -> None:
    """验证环形、星形和全连接拓扑构造器。"""
    ring = AgentTopology.ring(("a", "b", "c"))
    star = AgentTopology.star("center", ("x", "y"))
    complete = AgentTopology.complete(("a", "b", "c"))

    self.assertEqual(
        ring.edges,
        (("a", "b"), ("b", "c"), ("c", "a")),
    )
    self.assertTrue(star.can_send("x", "center"))
    self.assertEqual(len(complete.edges), 6)


class MessageRouterTest(unittest.TestCase):
  """拓扑消息路由测试。"""

  def test_broadcast_only_reaches_outgoing_neighbors(self) -> None:
    """验证广播不会越过发送者的直接出邻居。"""
    topology = AgentTopology(("a", "b", "c"))
    topology.connect("a", "b")
    router = MessageRouter(topology)

    messages = router.route(
        sender="a",
        action=AgentAction.message("hello", target="*"),
        round_index=0,
    )

    self.assertEqual([message.recipient for message in messages], ["b"])

  def test_invalid_direct_target_is_rejected(self) -> None:
    """验证没有直连边时无法定向发送消息。"""
    topology = AgentTopology(("a", "b"))
    router = MessageRouter(topology)

    with self.assertRaises(MessageRoutingError):
      router.route(
          sender="a",
          action=AgentAction.message("hello", target="b"),
          round_index=0,
      )


class MultiAgentRuntimeTest(unittest.TestCase):
  """同步多智能体运行器测试。"""

  def test_messages_are_visible_on_the_next_round(self) -> None:
    """验证同轮消息不会被后执行的节点提前观察到。"""
    sender_policy = ScriptedPolicy([
        AgentAction.message("first", target="receiver"),
        AgentAction.final_answer("sender done"),
    ])
    receiver_policy = ScriptedPolicy([
        AgentAction.wait(),
        AgentAction.final_answer("receiver done"),
    ])
    topology = AgentTopology(("sender", "receiver"))
    topology.connect("sender", "receiver")
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
        config=RuntimeConfig(max_rounds=3, termination_mode="all_final"),
    )

    result = runtime.run("测试同步投递")

    self.assertEqual(receiver_policy.observations[0]["inbox"], [])
    second_inbox = receiver_policy.observations[1]["inbox"]
    self.assertEqual(second_inbox[0]["content"], "first")
    self.assertEqual(result.completed_rounds, 2)
    self.assertEqual(result.termination_reason, "all_final_answers")

  def test_non_strict_routing_records_and_drops_invalid_message(self) -> None:
    """验证非严格路由模式会记录非法目标并继续运行。"""
    policy_a = ScriptedPolicy([
        AgentAction.message("blocked", target="b"),
    ])
    policy_b = ScriptedPolicy([AgentAction.wait()])
    topology = AgentTopology(("a", "b"))
    runtime = MultiAgentRuntime(
        nodes={
            "a": AgentNode(node_id="a", role="a", policy=policy_a),
            "b": AgentNode(node_id="b", role="b", policy=policy_b),
        },
        topology=topology,
        config=RuntimeConfig(
            max_rounds=1,
            termination_mode="max_rounds",
            strict_routing=False,
        ),
    )

    result = runtime.run("测试非法路由")

    self.assertEqual(result.messages, ())
    self.assertEqual(len(result.rounds[0].routing_errors), 1)

  def test_run_result_can_be_serialized_to_json(self) -> None:
    """验证运行结果可以直接写入 JSON 日志。"""
    policy = ScriptedPolicy([AgentAction.final_answer("done")])
    topology = AgentTopology(("single",))
    runtime = MultiAgentRuntime(
        nodes={
            "single": AgentNode(
                node_id="single", role="worker", policy=policy
            )
        },
        topology=topology,
        config=RuntimeConfig(max_rounds=1, termination_mode="any_final"),
    )

    result = runtime.run("测试序列化", shared_context={"value": 1})

    serialized = json.dumps(result.to_dict(), ensure_ascii=False)
    self.assertIn("测试序列化", serialized)
    self.assertIn("done", serialized)

  def test_llm_builder_runs_multiple_mock_nodes(self) -> None:
    """验证 LLM 构建器、提示词、解析器和运行器可以完整联通。"""
    builder = MultiAgentBuilder()
    builder.add_llm_node(
        node_id="a",
        role="sender",
        client=MockLLMClient(responses=[
            '{"kind":"message","content":"ping","target":"b"}'
        ]),
    )
    builder.add_llm_node(
        node_id="b",
        role="receiver",
        client=MockLLMClient(responses=['{"kind":"wait"}']),
    )
    builder.connect("a", "b")
    runtime = builder.build(config=RuntimeConfig(
        max_rounds=1,
        termination_mode="max_rounds",
    ))

    result = runtime.run("发送 ping")

    self.assertEqual(len(result.messages), 1)
    self.assertEqual(result.messages[0].content, "ping")
    self.assertEqual(result.messages[0].recipient, "b")


if __name__ == "__main__":
  unittest.main()
