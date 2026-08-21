"""使用 .env 中 DeepSeek API 密钥的多智能体示例。"""

from __future__ import annotations

import os
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from meltingpot.utils.env import load_env_file
from meltingpot.utils.llm import DeepSeekClient
from meltingpot.utils.multi_agent import MultiAgentBuilder
from meltingpot.utils.multi_agent import RuntimeConfig

def create_client() -> DeepSeekClient:
  """为一个节点创建独立的 DeepSeek 客户端。"""
  return DeepSeekClient(
      env_file=PROJECT_ROOT / ".env",
      default_model=os.environ.get("DEEPSEEK_MODEL", "deepseek-v4-flash"),
      timeout=45.0,
      max_retries=2,
      retry_backoff=1.0,
      default_temperature=0.0,
      default_max_tokens=512,
      thinking={"type": "disabled"},
  )


def build_runtime():
  """构建 planner -> writer <-> reviewer 的 DeepSeek 运行器。"""
  builder = MultiAgentBuilder()
  builder.add_llm_node(
      node_id="planner",
      role="规划者",
      client=create_client(),
      system_prompt=(
          "你负责拆解任务。第一轮把清晰提纲发送给 writer，之后等待；"
          "不要向拓扑之外的节点发送消息。"
      ),
  )
  builder.add_llm_node(
      node_id="writer",
      role="撰写者",
      client=create_client(),
      system_prompt=(
          "没有收到消息时等待；收到 planner 的提纲后写初稿并发送给 "
          "reviewer；只要 inbox 中存在来自 reviewer 的消息，下一动作就必须"
          "使用 final_answer，content 只放修订后的最终稿，target 必须为 null，"
          "禁止再次发送 message。"
      ),
  )
  builder.add_llm_node(
      node_id="reviewer",
      role="审阅者",
      client=create_client(),
      system_prompt=(
          "没有收到初稿时等待；收到 writer 的初稿后给出具体意见，"
          "并把意见发送回 writer。"
      ),
  )
  builder.connect("planner", "writer")
  builder.connect("writer", "reviewer", bidirectional=True)
  return builder.build(config=RuntimeConfig(
      max_rounds=4,
      termination_mode="any_final",
      strict_routing=True,
      fail_fast=True,
  ))


def main() -> None:
  """运行真实 DeepSeek 多智能体交互并打印结果。"""
  load_env_file(PROJECT_ROOT / ".env", override=False)
  with build_runtime() as runtime:
    result = runtime.run(
        "用不超过 200 字解释自定义通信拓扑对多智能体实验的价值。",
        shared_context={"language": "zh-CN", "max_length": 200},
    )

  print("实际轮数：", result.completed_rounds)
  print("结束原因：", result.termination_reason)
  for message in result.messages:
    print(
        f"第 {message.round_index} 轮 "
        f"{message.sender} -> {message.recipient}: {message.content}"
    )
  print("最终答案：", dict(result.final_answers))


if __name__ == "__main__":
  main()
