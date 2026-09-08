"""多智能体运行时中的节点封装。"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

from stegopot.domain.model import AgentAction
from stegopot.domain.interface import Policy
from stegopot.domain.model.execution import ContractViolation
from stegopot.domain.model.experiment import json_copy


class NodeExecutionError(RuntimeError):
  """智能体节点执行失败时抛出的异常。"""


_INITIAL_POLICY_STATE = object()


class AgentNode:
  """把节点身份、策略和运行状态封装在一起。

  Policy 继续只负责“观察到动作”的决策；AgentNode 负责保存该
  Policy 在当前 Session 中的状态，运行器不需要了解状态类型。独立 Trial
  仍只包含一次运行，连续 Episode 的状态转交由应用服务控制。
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

  def reset(self, state: Any = _INITIAL_POLICY_STATE) -> None:
    """重置或恢复节点策略状态。

    参数：
      state: 省略时调用 Policy.initial_state；传入值时恢复同一节点在前一
        Episode 返回的不透明状态。状态不做序列化，也不能跨 Session 使用。
    """
    self._state = (
        self.policy.initial_state()
        if state is _INITIAL_POLICY_STATE
        else state
    )
    self._is_reset = True

  def export_state(self) -> Any:
    """返回当前节点的不透明策略状态，供宿主在同一 Session 内传递。"""
    if not self._is_reset:
      raise RuntimeError("节点尚未初始化，不能导出策略状态")
    return self._state

  def act(self, observation: Any) -> AgentAction:
    """根据当前观察执行一次决策，并保存下一状态。

    参数：
      observation: 由观察构造器为该节点生成的局部观察。

    返回：
      节点输出的结构化动作。

    异常：
      ContractViolation: 策略没有返回动作与状态二元组，或动作不是 AgentAction。
    """
    if not self._is_reset:
      self.reset()
    outcome = self.policy.step(
        observation=observation,
        prev_state=self._state,
    )
    if not isinstance(outcome, (tuple, list)) or len(outcome) != 2:
      raise ContractViolation("策略必须返回动作和下一状态组成的二元组")
    action, next_state = outcome
    if not isinstance(action, AgentAction):
      raise ContractViolation(
          f"节点 {self.node_id} 的策略必须返回 AgentAction，"
          f"实际返回 {type(action).__name__}"
      )
    if (not isinstance(action.kind, str) or not action.kind
        or (action.content is not None and not isinstance(action.content, str))
        or (action.target is not None and not isinstance(action.target, str))):
      raise ContractViolation("动作类型、正文和目标必须满足字符串字段契约")
    try:
      json_copy(dict(action.metadata))
      if action.tool_call is not None:
        json_copy(action.tool_call.to_dict())
    except (TypeError, ValueError) as exc:
      raise ContractViolation("动作元数据和工具参数必须可标准 JSON 序列化") from exc
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
