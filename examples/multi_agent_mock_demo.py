"""不访问网络的自定义拓扑多智能体示例。"""

from __future__ import annotations

import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from stegopot.utils.llm import MockLLMClient
from stegopot.utils.multi_agent import MultiAgentBuilder
from stegopot.utils.multi_agent import RuntimeConfig


def build_runtime():
  """构建 planner -> writer <-> reviewer 拓扑的测试运行器。"""
  planner_client = MockLLMClient(responses=[
      '{"kind":"message","content":"先给出三点提纲",'
      '"target":"writer"}',
      '{"kind":"wait"}',
      '{"kind":"wait"}',
      '{"kind":"wait"}',
  ])
  writer_client = MockLLMClient(responses=[
      '{"kind":"wait"}',
      '{"kind":"message","content":"这是根据提纲写出的初稿",'
      '"target":"reviewer"}',
      '{"kind":"wait"}',
      '{"kind":"final_answer","content":"这是吸收审阅意见后的最终答案"}',
  ])
  reviewer_client = MockLLMClient(responses=[
      '{"kind":"wait"}',
      '{"kind":"wait"}',
      '{"kind":"message","content":"请补充一个具体例子",'
      '"target":"writer"}',
      '{"kind":"wait"}',
  ])

  builder = MultiAgentBuilder()
  builder.add_llm_node(
      node_id="planner",
      role="规划者",
      client=planner_client,
      system_prompt="负责拆解任务，并把提纲发给 writer。",
  )
  builder.add_llm_node(
      node_id="writer",
      role="撰写者",
      client=writer_client,
      system_prompt="根据 planner 和 reviewer 的消息撰写最终答案。",
  )
  builder.add_llm_node(
      node_id="reviewer",
      role="审阅者",
      client=reviewer_client,
      system_prompt="审阅 writer 的初稿，并把修改意见发回 writer。",
  )
  builder.connect("planner", "writer")
  builder.connect("writer", "reviewer", bidirectional=True)
  return builder.build(config=RuntimeConfig(
      max_rounds=6,
      termination_mode="any_final",
  ))


def main() -> None:
  """运行离线多智能体示例并打印消息转录。"""
  with build_runtime() as runtime:
    result = runtime.run(
        "解释为什么多智能体框架需要把拓扑和节点策略分开。",
        shared_context={"language": "zh-CN"},
    )

  print("实际轮数：", result.completed_rounds)
  print("结束原因：", result.termination_reason)
  print("\n消息转录：")
  for message in result.messages:
    print(
        f"  第 {message.round_index} 轮 "
        f"{message.sender} -> {message.recipient}: {message.content}"
    )
  print("\n最终答案：")
  print(json.dumps(dict(result.final_answers), ensure_ascii=False, indent=2))


if __name__ == "__main__":
  main()
