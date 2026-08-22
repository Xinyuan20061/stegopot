"""多智能体运行时中的节点封装。"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from stegopot.utils.policies.action import AgentAction
from stegopot.utils.policies.policy import Policy


class NodeExecutionError(RuntimeError):
  """智能体节点执行失败时抛出的异常。"""


class AgentNode:
  """把节点身份、策略和运行状态封装在一起。

  Policy 继续只负责“观察到动作”的决策；AgentNode 负责保存该
  Policy 在一次多智能体运行中的状态，运行器不需要了解状态类型。
  """

  def __init__(
      self,
      *,
      node_id: str,
      role: str,
      policy: Policy,
      metadata: Mapping[str, Any] | None = None,
  ) -> None:
    """初始化智能体节点。

    参数：
      node_id: 节点在当前多智能体系统中的唯一 ID。
      role: 节点承担的角色，例如 planner、writer 或 reviewer。
      policy: 根据观察生成结构化动作的策略实例。
      metadata: 节点级附加信息，仅用于记录或后续扩展。
    """
    if not isinstance(node_id, str) or not node_id.strip():
      raise ValueError("node_id 必须是非空字符串")
    if not isinstance(role, str) or not role.strip():
      raise ValueError("role 必须是非空字符串")
    self.node_id = node_id.strip()
    self.role = role.strip()
    self.policy = policy
    self.metadata = MappingProxyType(dict(metadata or {}))
    self._state: Any = None
    self._is_reset = False

  def reset(self) -> None:
    """重置节点策略状态，开始一次新的多智能体运行。"""
    self._state = self.policy.initial_state()
    self._is_reset = True

  def act(self, observation: Any) -> AgentAction:
    """根据当前观察执行一次决策，并保存下一状态。

    参数：
      observation: 由观察构造器为该节点生成的局部观察。

    返回：
      节点输出的结构化动作。

    异常：
      NodeExecutionError: 策略没有返回 AgentAction 对象。
    """
    if not self._is_reset:
      self.reset()
    action, next_state = self.policy.step(
        observation=observation,
        prev_state=self._state,
    )
    if not isinstance(action, AgentAction):
      raise NodeExecutionError(
          f"节点 {self.node_id} 的策略必须返回 AgentAction，"
          f"实际返回 {type(action).__name__}"
      )
    self._state = next_state
    return action

  def close(self) -> None:
    """释放节点策略持有的模型客户端或其他资源。"""
    self.policy.close()

  def __enter__(self) -> "AgentNode":
    return self

  def __exit__(self, *args: Any, **kwargs: Any) -> None:
    del args, kwargs
    self.close()
