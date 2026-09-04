"""组合实验组件、审计存储和统一执行用例。"""

from datetime import datetime, timezone
from pathlib import Path
import time
from uuid import uuid4

from stegopot.application.services.experiments.runner import execute_trial, run_plan
from stegopot.bootstrap.experiments.components import ComponentSession
from stegopot.bootstrap.experiments.runtime import build_runtime
from stegopot.domain.model.experiment import ComponentSpec
from stegopot.infrastructure.llm.audit import CallBudget
from stegopot.infrastructure.recorders.audit.journal import AuditJournal
from stegopot.infrastructure.recorders.audit.integrity import file_digest
from stegopot.infrastructure.recorders.audit.report import render_report


class _Fanout:
  """强制先写宿主日志，再通知可选审计接收器；任一失败都中止。"""

  def __init__(self, journal):
    """设置不可移除的 journal，插件接收器在自身构造完成后追加。"""
    self.journal = journal
    self.sinks = []

  def emit(self, event):
    """将 event 写入全部接收器，不屏蔽持久化异常。"""
    self.journal.emit(event)
    for sink in self.sinks:
      sink.emit(event)


def run_experiment(prepared, *, output="outputs", progress=None):
  """运行已预检实验，返回报告和新建审计目录。

  参数：
    prepared: prepare_experiment 返回的固定计划、注册表和授权凭证。
    output: 结果父目录；每次创建唯一子目录，不覆盖旧实验。
    progress: 可选的逐试验通知回调，不应修改收到的记录。

  返回：
    (report, directory)。审计存储失败直接抛出异常，并保留未封印证据。
    max_seconds 是启动新试验的软截止时间，不强制终止正在进行的 Python 调用。
  """
  config = prepared.config
  limits = config["runtime"]
  run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
  directory = Path(output).resolve() / run_id
  secrets = tuple(prepared.credentials.values())
  journal = AuditJournal(directory, run_id=run_id, redact_values=secrets)
  budget = CallBudget(limits["max_model_calls"])
  started = time.monotonic()

  def session(audit):
    """将 audit 与当前固定注册表接线成独立组件会话。"""
    return ComponentSession(prepared.catalog, resources=prepared.resources,
                            credentials=prepared.credentials, audit=audit,
                            budget=budget, max_output_tokens=limits["max_output_tokens"])

  root_session = session(journal)
  try:
    manifest = {"schema_version": "stegopot.manifest/1", "run_id": run_id,
                "config": config, "plan": prepared.plan.to_dict(),
                "plugins": prepared.catalog.describe(),
                "sources": prepared.catalog.source_fingerprints(),
                "audit_profile": "research", "trusted_plugins": True}
    journal.write_artifact("manifest.json", manifest)
    evaluators = [(spec.type, root_session.create(spec, "evaluator")) for spec in prepared.plan.evaluators]

    def execute(trial, carrier, skip):
      """为 trial 建立独立审计；carrier 是前序原文，skip 是宿主跳过原因。"""
      child = AuditJournal(directory / trial.trial_id, run_id=trial.trial_id, redact_values=secrets)
      audit = _Fanout(child)
      components = session(audit)
      calls_before = budget.used
      try:
        if time.monotonic() - started >= limits["max_seconds"]:
          skip = skip or "experiment_soft_deadline"
        runtime = None
        try:
          if not skip:
            for value in config["audit_sinks"]:
              # 工厂事件仅进入宿主日志，防止接收器在 emit 中递归调用自己。
              sink_session = session(child)
              components.adopt(sink_session)
              audit.sinks.append(sink_session.create(ComponentSpec.from_dict(value), "audit"))
            runtime = build_runtime(trial, session=components, audit=audit,
                                    config=config, replay_carrier=carrier)
        except Exception as exc:
          audit.emit({"kind": "component.failed", "data": {"type": type(exc).__name__, "message": str(exc)}})
          record = execute_trial(trial, runtime=None, audit=audit, evaluators=evaluators,
                                 skip_reason="component_construction_failed")
          record.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
        else:
          record = execute_trial(trial, runtime=runtime, audit=audit, evaluators=evaluators, skip_reason=skip)
        try:
          components.close()
        except Exception as exc:
          record.update(status="failed", error={"type": type(exc).__name__, "message": str(exc)})
          child.emit({"kind": "component.close_failed", "data": record["error"]})
        record["model_calls"] = budget.used - calls_before
        child.write_artifact("result.json", record)
        child.seal(artifacts=["result.json"])
        return {**record, "artifact_dir": trial.trial_id,
                "seal_sha256": file_digest(child.directory / "seal.json")}
      finally:
        try:
          components.close()
        finally:
          child.close()

    report = run_plan(prepared.plan, execute=execute, evaluators=evaluators, progress=progress)
    root_session.close()
    report.update(run_id=run_id, model_calls=budget.used, usage=budget.usage,
                  models=sorted(budget.models), elapsed_seconds=time.monotonic() - started)
    journal.emit({"kind": "experiment.completed", "data": {"status": report["status"]}})
    journal.write_artifact("experiment-report.json", report)
    # 人类阅读版也从已脱敏的持久化结果生成，不能泄露工厂异常中的凭证。
    import json
    persisted = json.loads((directory / "experiment-report.json").read_text(encoding="utf-8"))
    (directory / "report.md").write_text(render_report(persisted), encoding="utf-8")
    journal.seal(artifacts=["manifest.json", "experiment-report.json", "report.md"])
    return persisted, directory
  except KeyboardInterrupt:
    journal.emit({"kind": "experiment.interrupted", "data": {"reason": "operator_cancelled"}})
    raise
  finally:
    try:
      root_session.close()
    finally:
      journal.close()
