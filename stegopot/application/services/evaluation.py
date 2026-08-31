"""基于 MultiAgentRuntime 的最小评估入口。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stegopot.application.engine import MultiAgentRuntime
from stegopot.application.engine import RunResult


def run_episode(
    runtime: MultiAgentRuntime,
    *,
    task: str,
    shared_context: Mapping[str, Any] | None = None,
) -> RunResult:
  """运行一次完整实验并返回统一运行结果。

  参数：
    runtime: 已完成节点、拓扑、Substrate 和终止条件装配的运行器。
    task: 全部节点共同接收的实验任务文本。
    shared_context: 对全部节点可见的结构化背景信息。

  返回：
    包含轮次、消息、奖励、环境事件和最终状态的运行结果。
  """
  return runtime.run(task, shared_context=shared_context)
