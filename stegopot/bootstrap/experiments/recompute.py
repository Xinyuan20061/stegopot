"""从封印结果离线复算纯评价器指标，不重新运行节点或外部资源。"""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

from stegopot.bootstrap.experiments.builtin import builtin_plugin
from stegopot.bootstrap.experiments.components import PlanningContext
from stegopot.domain.model.experiment import ComponentSpec, TrialSpec, json_copy
from stegopot.infrastructure.plugins.catalog import PluginCatalog
from stegopot.infrastructure.recorders.audit.integrity import digest, verify_experiment


def recompute_experiment(
    directory: str | Path,
    *,
    expected_seal_sha256: str | None = None,
) -> dict[str, Any]:
  """核验实验后从固定计划和实际结果重新计算全部指标。

  参数：
    directory: 含 manifest、报告、审计链和子试验工件的运行目录。
    expected_seal_sha256: 可选外部根封印锚点；用于发现整组工件被替换。

  返回：
    ``stegopot.recompute/1`` 复算报告。``verified`` 只有在封印、当前
    插件源码指纹、逐试验指标和汇总指标全部一致时才为 True。

  说明：
    本函数不写入已封印目录，不创建模型、codec 或通用工具。评价器必须是
    无资源、无凭证的纯组件，否则预检和复算都会拒绝。
  """
  root = Path(directory).expanduser().resolve()
  verify_experiment(root, expected_seal_sha256=expected_seal_sha256)
  manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
  report = json.loads(
      (root / "experiment-report.json").read_text(encoding="utf-8")
  )
  catalog = PluginCatalog(builtin_plugin())
  catalog.load(manifest.get("config", {}).get("plugins", ()))
  current_sources = catalog.source_fingerprints()
  recorded_sources = manifest.get("sources", ())
  if current_sources != recorded_sources:
    raise ValueError("当前插件源码指纹与运行时清单不一致，拒绝伪复算")

  evaluator_specs = tuple(
      ComponentSpec.from_dict(item)
      for item in manifest["plan"].get("evaluators", ())
  )
  evaluators = []
  for spec in evaluator_specs:
    definition = catalog.validate(spec, "evaluator")
    if definition.references or definition.credentials:
      raise ValueError("评价器声明运行资源或凭证，不能离线复算")
    instance = definition.factory(json_copy(spec.config), PlanningContext())
    if any(
        not callable(getattr(instance, method, None))
        for method in ("evaluate", "summarize")
    ):
      raise TypeError(f"评价器 {spec.type} 不满足 evaluate/summarize 契约")
    evaluators.append((spec.type, instance))

  planned = {
      item["trial_id"]: TrialSpec.from_dict(item)
      for item in manifest["plan"]["trials"]
  }
  recomputed_records = []
  mismatches = []
  try:
    for record in report["trials"]:
      trial_id = record["trial"]["trial_id"]
      trial = planned[trial_id].for_principal("evaluator")
      metrics = {}
      if record.get("skip_reason") is None:
        for name, evaluator in evaluators:
          try:
            metrics[name] = json_copy(
                evaluator.evaluate(trial, json_copy(record.get("result", {})))
            )
          except Exception as exc:
            mismatches.append({
                "scope": "trial",
                "trial_id": trial_id,
                "component": name,
                "reason": "recompute_failed",
                "error_type": type(exc).__name__,
            })
      if metrics != record.get("metrics", {}):
        mismatches.append({
            "scope": "trial",
            "trial_id": trial_id,
            "reason": "metrics_mismatch",
            "recorded_sha256": digest(record.get("metrics", {})),
            "recomputed_sha256": digest(metrics),
        })
      copy = json_copy(record)
      copy["metrics"] = metrics
      recomputed_records.append(copy)

    aggregate = {}
    for name, evaluator in evaluators:
      try:
        aggregate[name] = json_copy(evaluator.summarize(
            json_copy(recomputed_records)
        ))
      except Exception as exc:
        mismatches.append({
            "scope": "summary",
            "component": name,
            "reason": "recompute_failed",
            "error_type": type(exc).__name__,
        })
    recorded_aggregate = report.get("summary", {}).get("metrics", {})
    if aggregate != recorded_aggregate:
      mismatches.append({
          "scope": "summary",
          "reason": "metrics_mismatch",
          "recorded_sha256": digest(recorded_aggregate),
          "recomputed_sha256": digest(aggregate),
      })
  finally:
    for _, evaluator in reversed(evaluators):
      close = getattr(evaluator, "close", None)
      if callable(close):
        close()

  return {
      "schema_version": "stegopot.recompute/1",
      "directory": str(root),
      "integrity_verified": True,
      "source_fingerprints_verified": True,
      "trial_count": len(recomputed_records),
      "evaluator_count": len(evaluators),
      "verified": not mismatches,
      "mismatches": mismatches,
      "summary_metrics_sha256": digest(aggregate),
  }
