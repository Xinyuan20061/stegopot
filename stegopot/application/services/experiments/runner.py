"""宿主拥有的计划编排、Session 状态转交与配对重放。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from stegopot.application.services.experiments.execution import (
    EpisodeExecutionContext,
    TrialExecution,
)
from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.experiment import Evaluator
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.interface.trace import audit_span
from stegopot.domain.model.execution import ExecutionStopped, error_details
from stegopot.domain.model.experiment import (
    ExperimentPlan,
    PairedCarrier,
    SessionSpec,
    TrialSpec,
    json_copy,
)
from stegopot.domain.model.communication import CommunicationIntent, carrier_sha256


def run_plan(
    plan: ExperimentPlan,
    *,
    execute: Callable[
        [TrialSpec, PairedCarrier | None, str | None, EpisodeExecutionContext],
        TrialExecution,
    ],
    evaluators: Sequence[tuple[str, Evaluator]],
    progress: Callable[[Mapping[str, Any]], None] | None = None,
    control: ExecutionGuard | None = None,
    audit: AuditSink | None = None,
) -> dict[str, Any]:
  """按固定计划执行独立 Trial 和 Session 内有序 Episode。

  参数：
    plan: 已完成版本和能力校验的完整计划。
    execute: 接收执行单元、重放正文、跳过原因和生命周期上下文的宿主回调。
    evaluators: 完成逐样本评价后，负责汇总全部记录的具名评分器。
    progress: 可选进度通知，不参与结果生成或评分。
    control: 可选全局控制器，停止后不再执行汇总插件。
    audit: 可选研究接收器，用于关联汇总调用，不拥有其关闭责任。

  返回：
    标准研究报告；包含条件汇总，但保留扁平 trials 兼容完整性校验。
  """
  membership = {
      episode.episode_id: (session, index)
      for session in plan.sessions
      for index, episode in enumerate(session.episodes)
  }
  session_states: dict[str, Mapping[str, Any]] = {}
  session_feedback: dict[str, Mapping[str, float]] = {}
  unavailable_sessions: set[str] = set()
  records: list[dict[str, Any]] = []
  by_id: dict[str, dict[str, Any]] = {}

  for trial in plan.trials:
    carrier, skip = _counterfactual_input(trial, by_id)
    member = membership.get(trial.trial_id)
    lifecycle = _lifecycle_context(
        trial,
        member=member,
        session_states=session_states,
        session_feedback=session_feedback,
    )
    if member is not None and member[0].session_id in unavailable_sessions:
      skip = skip or "previous_episode_not_completed"

    execution = execute(trial, carrier, skip, lifecycle)
    if not isinstance(execution, TrialExecution):
      raise TypeError("执行回调必须返回 TrialExecution")
    record = dict(execution.record)
    records.append(record)
    by_id[trial.trial_id] = record
    _update_session_memory(
        member,
        execution=execution,
        status=record["status"],
        states=session_states,
        feedback=session_feedback,
        unavailable=unavailable_sessions,
    )
    if progress:
      progress(json_copy(record))

  aggregate, errors = _summarize(
      records,
      evaluators=evaluators,
      control=control,
      audit=audit,
  )
  summary = {
      "planned": len(records),
      **{
          status: sum(item["status"] == status for item in records)
          for status in ("completed", "failed", "skipped")
      },
      "conditions": _condition_summary(records),
      "metrics": aggregate,
  }
  return {
      "schema_version": "stegopot.report/1",
      "trials": records,
      "summary": summary,
      "errors": errors,
      "status": (
          "failed"
          if errors or any(item["status"] == "failed" for item in records)
          else (
              "partial"
              if any(item["status"] == "skipped" for item in records)
              else "completed"
          )
      ),
  }


def _counterfactual_input(
    trial: TrialSpec,
    completed: Mapping[str, Mapping[str, Any]],
) -> tuple[PairedCarrier | None, str | None]:
  """从已完成记录提取固定源载体；普通执行单元返回两个空值。"""
  paired = trial.paired_spec
  if paired is None:
    return None, None
  source = completed[paired.source_trial]
  candidates = [
      message
      for message in source["result"].get("messages", [])
      if message["sender"] == paired.sender
      and message["recipient"] == paired.recipient
      and (
          paired.source_message_id is None
          or message["message_id"] == paired.source_message_id
      )
  ]
  if source["status"] != "completed" or len(candidates) != 1:
    return None, "source_trial_has_no_unique_completed_carrier"
  message = candidates[0]
  lineages = [
      item
      for item in source["result"].get("substrate_state", {}).get("communications", ())
      if item.get("message_id") == message["message_id"]
  ]
  communication = (
      CommunicationIntent.from_dict(lineages[0]["intent"])
      if len(lineages) == 1 and isinstance(lineages[0].get("intent"), Mapping)
      else CommunicationIntent.opaque(message["content"])
  )
  return PairedCarrier(
      source_trial=paired.source_trial,
      source_message_id=message["message_id"],
      sender=message["sender"],
      recipient=message["recipient"],
      content=message["content"],
      sha256=carrier_sha256(message["content"]),
      group_id=paired.effective_group_id,
      treatment_id=paired.treatment_id,
      communication=communication,
  ), None


def _lifecycle_context(
    trial: TrialSpec,
    *,
    member: tuple[SessionSpec, int] | None,
    session_states: Mapping[str, Mapping[str, Any]],
    session_feedback: Mapping[str, Mapping[str, float]],
) -> EpisodeExecutionContext:
  """按 Session 成员关系构造当前执行单元的状态与反馈输入。"""
  if member is None:
    return EpisodeExecutionContext(
        condition_id=None,
        session_id=None,
        episode_id=trial.trial_id,
        episode_index=0,
        persist_policy_state=False,
    )
  session, episode_index = member
  return EpisodeExecutionContext(
      condition_id=session.condition_id,
      session_id=session.session_id,
      episode_id=trial.trial_id,
      episode_index=episode_index,
      persist_policy_state=session.persist_policy_state,
      initial_policy_states=(
          session_states.get(session.session_id)
          if session.persist_policy_state and episode_index > 0
          else None
      ),
      initial_feedback=(
          session_feedback.get(session.session_id, {})
          if episode_index > 0
          else {}
      ),
  )


def _update_session_memory(
    member: tuple[SessionSpec, int] | None,
    *,
    execution: TrialExecution,
    status: str,
    states: dict[str, Mapping[str, Any]],
    feedback: dict[str, Mapping[str, float]],
    unavailable: set[str],
) -> None:
  """只在完成 Episode 后更新对应 Session 的驻内存延续数据。"""
  if member is None:
    return
  session, episode_index = member
  if status == "completed":
    if episode_index + 1 < len(session.episodes):
      feedback[session.session_id] = execution.feedback
      if session.persist_policy_state:
        states[session.session_id] = execution.policy_states
    else:
      states.pop(session.session_id, None)
      feedback.pop(session.session_id, None)
  else:
    states.pop(session.session_id, None)
    feedback.pop(session.session_id, None)
    unavailable.add(session.session_id)


def _summarize(
    records: Sequence[Mapping[str, Any]],
    *,
    evaluators: Sequence[tuple[str, Evaluator]],
    control: ExecutionGuard | None,
    audit: AuditSink | None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
  """调用具名中央汇总器，隔离错误并保留已完成记录。"""
  aggregate = {}
  errors = []
  for name, evaluator in evaluators:
    try:
      if control is not None:
        control.checkpoint()
      with audit_span(audit, "evaluator.summarize"):
        aggregate[name] = json_copy(evaluator.summarize(json_copy(records)))
      if control is not None:
        control.checkpoint()
    except ExecutionStopped:
      break
    except Exception as exc:
      errors.append({"component": name, **error_details(exc)})
  return aggregate, errors


def _condition_summary(records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
  """按首次出现顺序汇总条件和独立 Session，不包含独立旧式 Trial。"""
  grouped: dict[str, dict[str, Any]] = {}
  for record in records:
    condition_id = record.get("condition_id")
    session_id = record.get("session_id")
    if condition_id is None or session_id is None:
      continue
    item = grouped.setdefault(condition_id, {
        "condition_id": condition_id,
        "session_ids": [],
        "planned": 0,
        "completed": 0,
        "failed": 0,
        "skipped": 0,
    })
    if session_id not in item["session_ids"]:
      item["session_ids"].append(session_id)
    item["planned"] += 1
    item[record["status"]] += 1
  return [
      {
          **item,
          "sessions": len(item["session_ids"]),
      }
      for item in grouped.values()
  ]
