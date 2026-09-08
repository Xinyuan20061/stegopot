"""单个 Trial 或 Episode 的运行、结果反馈与持久化记录。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import math
from types import MappingProxyType
from typing import Any

from stegopot.application.engine.runtime import MultiAgentRuntime
from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.experiment import Evaluator, OutcomeRewardFunction
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.interface.trace import audit_span
from stegopot.domain.model.execution import ExecutionStopped, error_details
from stegopot.domain.model.experiment import TrialSpec, json_copy, validate_id
from stegopot.domain.model.reward import EpisodeOutcomeRequest


@dataclass(frozen=True)
class EpisodeExecutionContext:
  """宿主传给单次 Episode 执行回调的生命周期上下文。

  属性：
    condition_id: 实验条件 ID；独立 Trial 时为空。
    session_id: 独立重复 ID；独立 Trial 时为空。
    episode_id: 当前执行单元 ID，与兼容字段 trial_id 相同。
    episode_index: 当前 Episode 在 Session 内的零基序号。
    persist_policy_state: 当前 Session 是否允许延续不透明策略状态。
    initial_policy_states: 前一 Episode 的完整节点状态；不得写入日志或报告。
    initial_feedback: 前一 Episode 产生、只按节点投影的标量反馈。
  """

  condition_id: str | None
  session_id: str | None
  episode_id: str
  episode_index: int
  persist_policy_state: bool
  initial_policy_states: Mapping[str, Any] | None = field(default=None, repr=False)
  initial_feedback: Mapping[str, float] = field(default_factory=dict)

  def __post_init__(self) -> None:
    validate_id(self.episode_id)
    if (self.condition_id is None) != (self.session_id is None):
      raise ValueError("condition_id 和 session_id 必须同时存在或同时为空")
    if self.condition_id is not None:
      assert self.session_id is not None
      validate_id(self.condition_id)
      validate_id(self.session_id)
    if type(self.episode_index) is not int or self.episode_index < 0:
      raise ValueError("episode_index 必须是非负整数")
    if type(self.persist_policy_state) is not bool:
      raise TypeError("persist_policy_state 必须是 bool")
    if self.initial_policy_states is not None:
      object.__setattr__(
          self,
          "initial_policy_states",
          MappingProxyType(dict(self.initial_policy_states)),
      )
    object.__setattr__(
        self,
        "initial_feedback",
        MappingProxyType(dict(self.initial_feedback)),
    )


@dataclass(frozen=True)
class TrialExecution:
  """单个执行单元的可持久化记录与仅驻内存延续数据。

  属性：
    record: 可写入结果文件的标准 JSON 记录。
    policy_states: 节点不透明状态，只能在同一 Session 内传给下一 Episode。
    feedback: 当前 Episode 汇总后的节点标量反馈。
  """

  record: Mapping[str, Any]
  policy_states: Mapping[str, Any] = field(default_factory=dict, repr=False)
  feedback: Mapping[str, float] = field(default_factory=dict)

  def __post_init__(self) -> None:
    object.__setattr__(self, "record", MappingProxyType(json_copy(dict(self.record))))
    object.__setattr__(
        self,
        "policy_states",
        MappingProxyType(dict(self.policy_states)),
    )
    object.__setattr__(self, "feedback", MappingProxyType(dict(self.feedback)))


def execute_trial(
    trial: TrialSpec,
    *,
    runtime: MultiAgentRuntime | None,
    audit: AuditSink,
    evaluators: Sequence[tuple[str, Evaluator]],
    outcome_rewards: Sequence[tuple[str, OutcomeRewardFunction]] = (),
    lifecycle: EpisodeExecutionContext | None = None,
    skip_reason: str | None = None,
    control: ExecutionGuard | None = None,
) -> TrialExecution:
  """运行、反馈并评分一个 Trial 或 Episode。

  参数：
    trial: 中央计划，只有 task/shared_context 会直接进入共同观察。
    runtime: 组合根组装的运行器；跳过时允许为 None，资源由组合根关闭。
    audit: 宿主审计接口，记录失败必须可持久化。
    evaluators: 具名中央评分器，只通过本阶段接触真值。
    outcome_rewards: 具名结果奖励器，读取结果与真值后只返回节点标量。
    lifecycle: Session/Episode 身份、前序状态和反馈；独立 Trial 时可省略。
    skip_reason: 前序失败或预算耗尽等原因，不将跳过伪装成阴性结果。
    control: 可选试验控制器；停止后不继续执行中央评分。

  返回：
    包含可持久化记录、同 Session 状态和下一 Episode 反馈的执行结果。
  """
  lifecycle = lifecycle or EpisodeExecutionContext(
      condition_id=None,
      session_id=None,
      episode_id=trial.trial_id,
      episode_index=0,
      persist_policy_state=False,
  )
  if lifecycle.episode_id != trial.trial_id:
    raise ValueError("生命周期 episode_id 必须与当前执行单元 ID 一致")
  audit.emit({"kind": "trial.planned", "data": trial.to_dict()})
  result: dict[str, Any] = {}
  policy_states: Mapping[str, Any] = {}
  status = "skipped" if skip_reason else "completed"
  error = None
  errors = []
  if not skip_reason:
    try:
      if runtime is None:
        raise ValueError("非跳过试验必须提供运行器")
      result = runtime.run(
          trial.task,
          shared_context=trial.shared_context,
          initial_policy_states=lifecycle.initial_policy_states,
          initial_rewards=lifecycle.initial_feedback,
      ).to_dict()
      policy_states = runtime.policy_states()
    except Exception as exc:
      status = "failed"
      error = error_details(exc)
      errors.append(error)
      audit.emit({"kind": "trial.failed", "data": error})

  outcome_values: dict[str, dict[str, float]] = {}
  if status == "completed":
    request = EpisodeOutcomeRequest(
        condition_id=lifecycle.condition_id or "standalone",
        session_id=lifecycle.session_id or trial.trial_id,
        episode_id=lifecycle.episode_id,
        result=result,
        truth=trial.truth,
        information=trial.information_for("outcome_reward"),
    )
    for name, reward in outcome_rewards:
      try:
        if control is not None:
          control.checkpoint()
        audit.emit({
            "kind": "outcome_reward.request",
            "data": {"component": name, "request": request.to_dict()},
        })
        with audit_span(audit, "outcome_reward.score"):
          values = _validate_node_rewards(
              reward.score(request),
              nodes={node.node_id for node in trial.nodes},
              component=name,
          )
        outcome_values[name] = values
        audit.emit({
            "kind": "outcome_reward.computed",
            "data": {"component": name, "rewards": values},
        })
        if control is not None:
          control.checkpoint()
      except Exception as exc:
        status = "failed"
        failure = {**error_details(exc), "component": name}
        errors.append(failure)
        error = error or failure
        audit.emit({"kind": "outcome_reward.failed", "data": failure})

  metrics = {}
  for name, evaluator in (() if skip_reason else evaluators):
    try:
      if control is not None:
        control.checkpoint()
      with audit_span(audit, "evaluator.evaluate"):
        metrics[name] = json_copy(evaluator.evaluate(
            trial.for_principal("evaluator"), json_copy(result)
        ))
      if control is not None:
        control.checkpoint()
    except ExecutionStopped as exc:
      status = "failed"
      if error is None:
        error = error_details(exc)
        errors.append(error)
      audit.emit({"kind": "evaluation.stopped", "data": error_details(exc)})
      break
    except Exception as exc:
      status = "failed"
      failure = {**error_details(exc), "component": name}
      errors.append(failure)
      error = error or failure
      audit.emit({"kind": "evaluation.failed", "data": failure})

  feedback = _aggregate_feedback(result, outcome_values)
  record = {
      "trial": trial.to_dict(),
      "condition_id": lifecycle.condition_id,
      "session_id": lifecycle.session_id,
      "episode_id": lifecycle.episode_id,
      "episode_index": lifecycle.episode_index,
      "status": status,
      "error": error,
      "errors": errors,
      "skip_reason": skip_reason,
      "result": result,
      "metrics": metrics,
      "outcome_rewards": outcome_values,
      "initial_feedback": dict(lifecycle.initial_feedback),
      "feedback": feedback,
      "message_source": (
          "paired_replay"
          if trial.replay is not None
          else "paired_counterfactual" if trial.counterfactual is not None else "policy"
      ),
      "counterfactual": None if trial.paired_spec is None else {
          "group_id": trial.paired_spec.effective_group_id,
          "treatment_id": trial.paired_spec.treatment_id,
          "source_trial": trial.paired_spec.source_trial,
      },
  }
  audit.emit({
      "kind": "trial.completed",
      "data": {
          "status": status,
          "metrics": metrics,
          "outcome_rewards": outcome_values,
          "feedback": feedback,
          "skip_reason": skip_reason,
      },
  })
  if status != "completed":
    policy_states = {}
    feedback = {}
  return TrialExecution(
      record=record,
      policy_states=policy_states,
      feedback=feedback,
  )


def _validate_node_rewards(
    values: Mapping[str, float],
    *,
    nodes: set[str],
    component: str,
) -> dict[str, float]:
  """验证结果奖励映射仅包含当前 Episode 节点和有限标量。"""
  if not isinstance(values, Mapping):
    raise TypeError(f"结果奖励器 {component} 必须返回 Mapping")
  unknown = set(values) - nodes
  if unknown:
    raise ValueError(f"结果奖励器 {component} 返回未知节点：{sorted(unknown)}")
  normalized = {}
  for node_id, value in values.items():
    if isinstance(value, bool) or not isinstance(value, (int, float)):
      raise TypeError(f"结果奖励器 {component} 的分值必须是数值")
    number = float(value)
    if not math.isfinite(number):
      raise ValueError(f"结果奖励器 {component} 的分值必须有限")
    normalized[node_id] = number
  return normalized


def _aggregate_feedback(
    result: Mapping[str, Any],
    outcome_values: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
  """合并逐轮累计奖励和全部结果奖励，作为下一 Episode 的标量反馈。"""
  feedback = {
      node_id: float(value)
      for node_id, value in result.get("rewards", {}).items()
  }
  for values in outcome_values.values():
    for node_id, value in values.items():
      feedback[node_id] = feedback.get(node_id, 0.0) + value
  return feedback
