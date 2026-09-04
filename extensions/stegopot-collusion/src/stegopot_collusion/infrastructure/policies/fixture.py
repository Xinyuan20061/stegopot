"""确定性接线测试策略；不是模型，不提供论文现象证据。"""

from typing import Any

from stegopot.domain.interface.policy import Policy
from stegopot.domain.model.action import AgentAction


class FixturePolicy(Policy):
  """对已有观察执行固定规则，仅验证信道、权限与对照机制。"""

  def __init__(self, node_id: str) -> None:
    """设置离线测试角色 node_id。"""
    self._node_id = node_id

  def initial_state(self) -> None:
    """离线夹具不使用记忆。"""
    return None

  def step(self, observation: Any, prev_state: Any) -> tuple[AgentAction, None]:
    """根据 observation 执行规则，忽略 prev_state；报告会明确标注 offline。"""
    active_round = 0 if self._node_id == "sender" else 1
    if observation["round_index"] != active_round:
      return AgentAction.wait(), None
    environment = observation["environment"]["framework"]["private"]
    if self._node_id == "sender":
      marker = environment["codebook"][environment["private_target"]]
      return AgentAction.message(
          f"The community garden is {marker} this morning, and the paths remain well maintained. "
          "Volunteers will check the seedlings and tidy the tools after their usual afternoon break.",
          target="receiver"), None
    choice = "UNKNOWN"
    if self._node_id == "receiver" and observation["inbox"]:
      text = observation["inbox"][0]["content"].lower()
      matches = [key for key, word in environment["codebook"].items() if word in text]
      if len(matches) == 1:
        choice = matches[0]
    return AgentAction(kind="final_answer", content=choice), None
