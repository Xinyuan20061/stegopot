"""组合实验组件、执行控制与审计存储；不包含研究算法。"""

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from typing import Any
from uuid import uuid4

from stegopot.application.engine.control import ExecutionBudget
from stegopot.application.services.experiments.execution import (
    EpisodeExecutionContext,
    TrialExecution,
    execute_trial,
)
from stegopot.application.services.experiments.runner import run_plan
from stegopot.bootstrap.experiments.components import ComponentSession
from stegopot.bootstrap.experiments.prepare import PreparedExperiment
from stegopot.bootstrap.experiments.runtime import build_runtime
from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.model.execution import CancellationToken, ExecutionStopped, error_details
from stegopot.domain.model.experiment import ComponentSpec, PairedCarrier, TrialSpec
from stegopot.infrastructure.llm.audit import CallBudget
from stegopot.infrastructure.recorders.audit.journal import AuditJournal
from stegopot.infrastructure.recorders.audit.integrity import file_digest
from stegopot.infrastructure.recorders.audit.report import render_report
from stegopot.infrastructure.recorders.audit.trace import TracedAudit
from stegopot.infrastructure.settings.diagnostics import environment_manifest


class _Fanout:
  """强制先写宿主日志，再通知附加接收器；任一失败都向上传播。"""

  def __init__(self, journal: AuditJournal) -> None:
    """注入 journal；sinks 仅在工厂完成后追加，不拥有关闭责任。"""
    self.journal = journal
    self.sinks: list[AuditSink] = []

  def emit(self, event: Mapping[str, Any]) -> None:
    """将 event 同步写入全部接收器；失败不能转换成成功写入。"""
    self.journal.emit(event)
    for sink in self.sinks:
      sink.emit(event)


def run_experiment(
    prepared: PreparedExperiment, *, output: str | Path = "outputs",
    progress: Callable[[Mapping[str, Any]], None] | None = None,
    cancellation: CancellationToken | None = None,
) -> tuple[dict[str, Any], Path]:
  """运行已预检实验，返回已脱敏报告和新建目录。

  参数：
    prepared: 固定计划、注册表和授权凭证，不能提供给节点或公开日志。
    output: 结果父目录；每次创建唯一子目录，不覆盖或续写已有证据。
    progress: 逐试验研究记录回调；异常向上传播，调用者不得泄露私有材料。
    cancellation: 调用方取消令牌，可从另一线程请求停止；已开始调用只能协作式结束。

  返回：
    (report, directory)。失败或停止有结构化原因；审计失败抛出并保留未封印目录。
    时间与大小预算不替代进程隔离，不能强制终止卡住的第三方 Python 代码。
  """
  config = prepared.config
  limits = config["runtime"]
  run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
  directory = Path(output).resolve() / run_id
  secrets = tuple(prepared.credentials.values())
  journal = AuditJournal(directory, run_id=run_id, redact_values=secrets)
  root_audit = TracedAudit(journal, run_id=run_id)
  calls = CallBudget(limits["max_model_calls"])
  control = ExecutionBudget(limits, cancellation=cancellation)
  started = time.monotonic()

  def session(audit: AuditSink, guard: ExecutionGuard) -> ComponentSession:
    """为 audit/guard 创建受控会话，只注入本次配置声明的资源。"""
    return ComponentSession(prepared.catalog, resources=prepared.resources,
                            credentials=prepared.credentials, audit=audit,
                            budget=calls, max_output_tokens=limits["max_output_tokens"], control=guard)

  root_guard = control.global_scope()
  root_session = session(root_audit, root_guard)
  try:
    threat_model = prepared.threat_model.to_dict()
    journal.write_artifact("threat-model.json", threat_model)
    threat_model_path = directory / "threat-model.json"
    manifest = {"schema_version": "stegopot.manifest/3", "run_id": run_id,
                "config": config, "plan": prepared.plan.to_dict(),
                "plugins": prepared.catalog.describe(), "sources": prepared.catalog.source_fingerprints(),
                "environment": environment_manifest(),
                "preflight": [item.to_dict() for item in prepared.diagnostics],
                "audit_profile": "research", "trusted_plugins": True,
                "threat_model": {"artifact": "threat-model.json",
                                 "sha256": file_digest(threat_model_path)}}
    journal.write_artifact("manifest.json", manifest)
    evaluators = []
    try:
      for spec in prepared.plan.evaluators:
        evaluators.append((spec.type, root_session.create(spec, "evaluator")))
    except ExecutionStopped:
      # 停止后不再构造评分资源，仍给所有计划试验留下明确的跳过记录。
      evaluators = []

    def execute(
        trial: TrialSpec,
        carrier: PairedCarrier | None,
        skip: str | None,
        lifecycle: EpisodeExecutionContext,
    ) -> TrialExecution:
      """执行一个计划单元并保留仅限同 Session 使用的不透明状态。

      参数：
        trial: 当前 Trial 或兼容表示的 Episode 声明。
        carrier: 独立配对反事实使用的源载体及其完整来源标识。
        skip: 上游失败、预算停止等宿主跳过原因。
        lifecycle: 当前 Condition、Session、Episode 身份和前序内存数据。

      返回：
        可持久化记录与只驻留内存的策略状态、标量反馈。
      """
      child = AuditJournal(directory / trial.trial_id, run_id=trial.trial_id, redact_values=secrets)
      fanout = _Fanout(child)
      audit = TracedAudit(
          fanout,
          run_id=run_id,
          trial_id=trial.trial_id,
          condition_id=lifecycle.condition_id,
          session_id=lifecycle.session_id,
          episode_id=lifecycle.episode_id,
      )
      guard = control.for_trial(trial.trial_id)
      components = session(audit, guard)
      calls_before = calls.used
      try:
        with audit.span("trial.execute"):
          runtime = None
          outcome_rewards = []
          stopped = None
          try:
            guard.checkpoint()
          except ExecutionStopped as exc:
            stopped = error_details(exc)
            skip = skip or exc.code
          try:
            if not skip:
              for value in config["audit_sinks"]:
                # 接收器自身的工厂事件只写宿主，避免 emit 中递归通知自身。
                sink_audit = TracedAudit(
                    child,
                    run_id=run_id,
                    trial_id=trial.trial_id,
                    condition_id=lifecycle.condition_id,
                    session_id=lifecycle.session_id,
                    episode_id=lifecycle.episode_id,
                )
                sink_session = session(sink_audit, guard)
                components.adopt(sink_session)
                fanout.sinks.append(sink_session.create(ComponentSpec.from_dict(value), "audit"))
              runtime = build_runtime(trial, session=components, audit=audit, config=config,
                                      paired_carrier=carrier,
                                      threat_model=prepared.threat_model, control=guard)
              outcome_rewards = [
                  (spec.type, components.create(spec, "outcome_reward"))
                  for spec in prepared.plan.outcome_rewards
              ]
          except Exception as exc:
            failure = error_details(exc)
            audit.emit({"kind": "component.failed", "data": failure})
            execution = execute_trial(
                trial,
                runtime=None,
                audit=audit,
                evaluators=(),
                lifecycle=lifecycle,
                skip_reason="component_construction_failed",
            )
            record = dict(execution.record)
            record.update(status="failed", error=failure, errors=[failure])
            execution = TrialExecution(record=record)
          else:
            execution = execute_trial(
                trial,
                runtime=runtime,
                audit=audit,
                evaluators=evaluators,
                outcome_rewards=outcome_rewards,
                lifecycle=lifecycle,
                skip_reason=skip,
                control=guard,
            )
            if stopped:
              record = dict(execution.record)
              record.update(error=stopped, errors=[stopped])
              execution = TrialExecution(record=record)
          if carrier is not None:
            record = dict(execution.record)
            counterfactual = dict(record.get("counterfactual") or {})
            counterfactual.update({
                "source_message_id": carrier.source_message_id,
                "carrier_sha256": carrier.sha256,
            })
            record["counterfactual"] = counterfactual
            execution = TrialExecution(
                record=record,
                policy_states=execution.policy_states,
                feedback=execution.feedback,
            )
          try:
            components.close()
          except Exception as exc:
            failure = error_details(exc)
            record = dict(execution.record)
            record["errors"].append(failure)
            record.update(status="failed", error=record.get("error") or failure)
            execution = TrialExecution(record=record)
            child.emit({"kind": "component.close_failed", "data": failure})
          record = dict(execution.record)
          record["model_calls"] = calls.used - calls_before
        child.write_artifact("result.json", record)
        child.seal(artifacts=["result.json"])
        return TrialExecution(
            record={
                **record,
                "artifact_dir": trial.trial_id,
                "seal_sha256": file_digest(child.directory / "seal.json"),
            },
            policy_states=execution.policy_states,
            feedback=execution.feedback,
        )
      finally:
        try:
          components.close()
        finally:
          child.close()

    report = run_plan(prepared.plan, execute=execute, evaluators=evaluators,
                      progress=progress, control=root_guard, audit=root_audit)
    root_session.close()
    execution = control.snapshot()
    if execution["stop_reason"] and report["status"] == "completed":
      report["status"] = "partial"
    report.update(run_id=run_id, model_calls=calls.used, usage=calls.usage,
                  models=sorted(calls.models), elapsed_seconds=time.monotonic() - started,
                  execution=execution)
    root_audit.emit({"kind": "experiment.completed", "data": {
        "status": report["status"], "execution": execution}})
    journal.write_artifact("experiment-report.json", report)
    persisted = json.loads((directory / "experiment-report.json").read_text(encoding="utf-8"))
    (directory / "report.md").write_text(render_report(persisted), encoding="utf-8")
    journal.seal(artifacts=["threat-model.json", "manifest.json",
                            "experiment-report.json", "report.md"])
    return persisted, directory
  except KeyboardInterrupt:
    root_audit.emit({"kind": "experiment.interrupted", "data": {"reason": "operator_cancelled"}})
    raise
  finally:
    try:
      root_session.close()
    finally:
      journal.close()
