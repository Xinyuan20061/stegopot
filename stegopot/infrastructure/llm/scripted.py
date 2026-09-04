"""明确标记为规则策略的离线节点，用于内核和第三方插件开发。"""

from collections.abc import Mapping, Sequence
from typing import Any

from stegopot.domain.interface.policy import Policy
from stegopot.domain.model.action import AgentAction


class ScriptedPolicy(Policy[int]):
  """顺序执行配置中的动作，不声称这些动作由 LLM 生成。"""

  def __init__(self, actions: Sequence[Mapping[str, Any]]) -> None:
    """以 actions 定义每步动作，执行完后保持等待。"""
    self._actions = tuple(AgentAction(**dict(item)) for item in actions)

  def initial_state(self) -> int:
    """返回从第一项动作开始的状态。"""
    return 0

  def step(self, observation: Any, prev_state: int) -> tuple[AgentAction, int]:
    """忽略 observation，返回 prev_state 所指动作并推进索引。"""
    action = self._actions[prev_state] if prev_state < len(self._actions) else AgentAction.wait()
    return action, prev_state + 1


class EchoPolicy(Policy[None]):
  """从实际收件箱返回最新正文的规则策略。"""

  def initial_state(self) -> None:
    """返回无内部状态。"""
    return None

  def step(self, observation: Any, prev_state: None) -> tuple[AgentAction, None]:
    """读取 observation 的实际 inbox；prev_state 不包含预测答案。"""
    inbox = observation.get("inbox", [])
    return (AgentAction.final_answer(inbox[-1]["content"]) if inbox else AgentAction.wait()), None
