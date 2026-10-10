"""与具体任务语义无关的 Experiment Engine。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import time
from typing import Any

from stegopot.domain.interface.research import Analyzer, Metric, Reporter, ResearchScenario
from stegopot.domain.model.context import (
    ExperimentContext,
    ResearchExperimentResult,
    SampleRunRecord,
)
from stegopot.domain.model.data import DatasetBundle
from stegopot.domain.model.events import EventKind, RuntimeEvent


class ResearchExperimentEngine:
  """执行 Scenario -> Analyze -> Evaluate -> Save 通用生命周期。"""

  def __init__(
      self, *, scenario: ResearchScenario,
      analyzers: Sequence[Analyzer] = (), metrics: Sequence[Metric] = (),
      reporters: Sequence[Reporter] = (),
  ) -> None:
    """注入全部实验语义组件；引擎只负责编排。"""
    self.scenario = scenario
    self.analyzers = tuple(analyzers)
    self.metrics = tuple(metrics)
    self.reporters = tuple(reporters)
    for values, attribute in ((self.analyzers, "analyzer_id"),
                              (self.metrics, "metric_id"),
                              (self.reporters, "reporter_id")):
      identifiers = [getattr(item, attribute) for item in values]
      if len(set(identifiers)) != len(identifiers):
        raise ValueError(f"{attribute} 不能重复")

  def run(
      self, dataset: DatasetBundle, context: ExperimentContext, *,
      partitions: Sequence[str] = ("train", "validation", "test"),
  ) -> ResearchExperimentResult:
    """执行指定数据切分并封印通用结果工件。"""
    selected = []
    for name in partitions:
      if name not in {"train", "validation", "test"}:
        raise ValueError(f"未知数据切分：{name}")
      selected.extend(getattr(dataset, name))
    if not selected:
      raise ValueError("选定的数据切分为空")
    self._emit(context, EventKind.RUN_START, {"sample_count": len(selected)})
    records = []
    status = "completed"
    failure = None
    setup_done = False
    try:
      self.scenario.setup(context)
      setup_done = True
      for sample in selected:
        started = time.perf_counter()
        output = self.scenario.run(sample, context)
        analyses = {item.analyzer_id: item.analyze(sample, output, context)
                    for item in self.analyzers}
        if analyses:
          self._emit(context, EventKind.ANALYZE,
                     {"sample_id": sample.sample_id, "analyzers": sorted(analyses)})
        metrics = {}
        for item in self.metrics:
          value = float(item.evaluate(sample, output, analyses, context))
          if not math.isfinite(value):
            raise ValueError(f"指标 {item.metric_id} 返回非有限数")
          metrics[item.metric_id] = value
        if metrics:
          self._emit(context, EventKind.EVALUATE,
                     {"sample_id": sample.sample_id, "metrics": sorted(metrics)})
        records.append(SampleRunRecord(
            sample.sample_id, output, analyses, metrics,
            {"duration_seconds": time.perf_counter() - started}))
    except Exception as exc:
      status = "failed"
      failure = {"type": type(exc).__name__, "message": str(exc)}
    finally:
      if setup_done:
        try:
          self.scenario.teardown(context)
        except Exception as exc:
          status = "failed"
          failure = failure or {"type": type(exc).__name__, "message": str(exc)}
    summary = {}
    for reporter in self.reporters:
      values = dict(reporter.summarize(records, context))
      for key, value in values.items():
        namespaced = f"{reporter.reporter_id}.{key}"
        if namespaced in summary:
          raise ValueError(f"Reporter 摘要字段重复：{namespaced}")
        summary[namespaced] = value
    if failure is not None:
      summary["failure"] = failure
    artifacts = self._save(dataset, records, summary, context, status)
    result = ResearchExperimentResult(
        context.run_id, status, records, summary, artifacts)
    for reporter in self.reporters:
      reporter.report(result, context)
    seal = context.artifact_store.seal({
        "run_id": context.run_id, "status": status,
        "dataset_fingerprint": dataset.fingerprint,
    })
    result = ResearchExperimentResult(
        context.run_id, status, records, summary,
        {**artifacts, "seal": seal})
    self._emit(context, EventKind.RUN_END, {"status": status, "record_count": len(records)})
    return result

  def _save(self, dataset, records, summary, context, status):
    """写入框架标准工件；复杂输出由插件自行使用 ArtifactStore。"""
    self._emit(context, EventKind.SAVE, {"status": status})
    config_ref = context.artifact_store.write_json("config.json", dict(context.config))
    metadata_ref = context.artifact_store.write_json("metadata.json", {
        "run_id": context.run_id, "seed": context.seed,
        "dataset_id": dataset.dataset_id, "dataset_fingerprint": dataset.fingerprint,
        **dict(context.metadata),
    })
    output_ref = context.artifact_store.write_jsonl("outputs.jsonl", [
        {"sample_id": item.sample_id, "analyses": _json_safe(dict(item.analyses)),
         "metrics": dict(item.metrics), "metadata": dict(item.metadata),
         "output": _json_safe(item.output)} for item in records
    ])
    metrics_ref = context.artifact_store.write_json("metrics.json", {
        "status": status, "summary": _json_safe(summary),
        "records": [{"sample_id": item.sample_id, "metrics": dict(item.metrics)}
                    for item in records],
    })
    return {"config": config_ref, "metadata": metadata_ref, "outputs": output_ref,
            "metrics": metrics_ref}

  @staticmethod
  def _emit(context, kind, data):
    """通过显式事件总线发送生命周期事件。"""
    context.event_bus.emit(RuntimeEvent(kind, context.run_id, data=data))


def _json_safe(value: Any) -> Any:
  """只转换常用 JSON 值；未知对象使用类型和 repr 的有界摘要。"""
  if value is None or isinstance(value, (str, int, float, bool)):
    return value
  if isinstance(value, Mapping):
    return {str(key): _json_safe(item) for key, item in value.items()}
  if isinstance(value, (list, tuple)):
    return [_json_safe(item) for item in value]
  to_manifest = getattr(value, "to_manifest", None)
  if callable(to_manifest):
    return _json_safe(to_manifest())
  shape = getattr(value, "shape", None)
  dtype = getattr(value, "dtype", None)
  if shape is not None and dtype is not None:
    return {
        "type": type(value).__name__,
        "shape": [int(item) for item in shape],
        "dtype": str(dtype),
        "device": str(getattr(value, "device", "unknown")),
    }
  logits = getattr(value, "logits", None)
  if logits is not None:
    return {"type": type(value).__name__, "logits": _json_safe(logits)}
  return {"type": type(value).__name__}
