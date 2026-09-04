"""宿主拥有的试验执行与配对重放，不允许插件自行替换运行循环。"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from stegopot.application.engine.runtime import MultiAgentRuntime
from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.experiment import Evaluator
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.interface.trace import audit_span
from stegopot.domain.model.execution import ExecutionStopped, error_details
from stegopot.domain.model.experiment import ExperimentPlan, TrialSpec, json_copy


def execute_trial(
    trial: TrialSpec, *, runtime: MultiAgentRuntime | None, audit: AuditSink,
    evaluators: Sequence[tuple[str, Evaluator]], skip_reason: str | None = None,
    control: ExecutionGuard | None = None,
) -> dict[str, Any]:
  """运行并评分一次试验。

  参数：
    trial: 中央计划，只有 task/shared_context 会直接进入共同观察。
    runtime: 组合根组装的运行器；跳过时允许为 None，资源由组合根关闭。
    audit: 宿主审计接口，记录失败必须可持久化。
    evaluators: 具名中央评分器，只通过本阶段接触真值。
    skip_reason: 前序载体缺失或预算耗尽等原因，不将跳过伪装成阴性结果。
    control: 可选试验控制器；停止后不继续执行中央评分，关闭资源由组合根负责。

  返回：
    标准试验记录，包含原始结果、状态和命名空间指标。
  """
  audit.emit({"kind": "trial.planned", "data": trial.to_dict()})
  result = {}
  status = "skipped" if skip_reason else "completed"
  error = None
  errors = []
  if not skip_reason:
    try:
      if runtime is None:
        raise ValueError("非跳过试验必须提供运行器")
      result = runtime.run(trial.task, shared_context=trial.shared_context).to_dict()
    except Exception as exc:
      status = "failed"
      error = error_details(exc)
      errors.append(error)
      audit.emit({"kind": "trial.failed", "data": error})
  metrics = {}
  for name, evaluator in (() if skip_reason else evaluators):
    try:
      if control is not None:
        control.checkpoint()
      with audit_span(audit, "evaluator.evaluate"):
        metrics[name] = json_copy(evaluator.evaluate(trial, json_copy(result)))
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
  record = {"trial": trial.to_dict(), "status": status, "error": error, "errors": errors,
            "skip_reason": skip_reason, "result": result, "metrics": metrics,
            "message_source": "paired_replay" if trial.replay else "policy"}
  audit.emit({"kind": "trial.completed", "data": {
      "status": status, "metrics": metrics, "skip_reason": skip_reason,
  }})
  return record


def run_plan(
    plan: ExperimentPlan, *,
    execute: Callable[[TrialSpec, str | None, str | None], Mapping[str, Any]],
    evaluators: Sequence[tuple[str, Evaluator]],
    progress: Callable[[Mapping[str, Any]], None] | None = None,
    control: ExecutionGuard | None = None, audit: AuditSink | None = None,
) -> dict[str, Any]:
  """执行固定 plan，并将真实正文传给配对试验。

  参数：
    plan: 已完成版本和能力校验的完整计划。
    execute: 接收试验、可选重放正文和可选跳过原因的宿主回调。
    evaluators: 完成逐样本评价后，负责汇总全部记录的具名评分器。
    progress: 可选进度通知，不参与结果生成或评分。
    control: 可选全局控制器，停止后不再执行汇总插件。
    audit: 可选研究接收器，用于关联汇总调用，不拥有其关闭责任。

  返回：
    标准研究报告；插件指标被放在独立命名空间，不改变基础格式。
  """
  records = []
  by_id = {}
  for trial in plan.trials:
    carrier = None
    skip = None
    if trial.replay:
      source = by_id[trial.replay.source_trial]
      candidates = [message for message in source["result"].get("messages", [])
                    if message["sender"] == trial.replay.sender
                    and message["recipient"] == trial.replay.recipient]
      if source["status"] != "completed" or len(candidates) != 1:
        skip = "source_trial_has_no_unique_completed_carrier"
      else:
        carrier = candidates[0]["content"]
    record = dict(execute(trial, carrier, skip))
    records.append(record)
    by_id[trial.trial_id] = record
    if progress:
      progress(json_copy(record))
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
  return {"schema_version": "stegopot.report/1", "trials": records,
          "summary": {"planned": len(records),
                      **{status: sum(item["status"] == status for item in records)
                         for status in ("completed", "failed", "skipped")},
                      "metrics": aggregate},
          "errors": errors, "status": "failed" if errors or any(
              item["status"] == "failed" for item in records) else (
                  "partial" if any(item["status"] == "skipped" for item in records) else "completed")}
