"""离线分析文件级 API；所有输出新建，不改写来源实验。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from stegopot.application.services.analysis.attribution import build_path_graph, parse_interventions
from stegopot.application.services.analysis.dataset import SplitConfig, build_matched_datasets
from stegopot.application.services.analysis.localization import (
    LocalizationConfig,
    localize_datasets,
    merge_localization_maps,
)
from stegopot.application.services.analysis.migration import compare_path_graphs
from stegopot.bootstrap.analysis.config import analysis_protocol_fingerprint, load_analysis_config
from stegopot.domain.model.attribution import CausalPathGraph
from stegopot.domain.model.localization import (
    CapturedObservation,
    DataKind,
    LocalizationMap,
    ObservationAddress,
    SecretSpec,
    SurfaceKind,
)
from stegopot.infrastructure.analysis.localizers import (
    LinearSecretProbe,
    StructuredSecretProbe,
    TextSecretProbe,
)
from stegopot.infrastructure.analysis.sources.sealed_runs import (
    assert_runs_unchanged,
    load_public_text_observations,
    resolve_run_directories,
    run_provenance,
)
from stegopot.infrastructure.recorders.audit.integrity import file_digest
from stegopot.infrastructure.recorders.representations import (
    RepresentationReader,
    load_representation_observations,
)


def localize_runs(
    target: str | Path,
    *,
    config: str | Path,
    output: str | Path | None = None,
) -> tuple[LocalizationMap, Path]:
  """对一个封印运行或运行组执行离线秘密定位。

  参数：
    target: 单个运行目录、包含运行的目录或 runs JSON 清单。
    config: 独立分析 YAML/JSON，不是实验配置。
    output: 可选分析结果父目录；默认是分析配置工作区的 outputs。

  返回：
    LocalizationMap 和新建分析目录。中央标签不会写入输出或来源运行。
  """
  value, config_path = load_analysis_config(config)
  runs = resolve_run_directories(target)
  provenance = run_provenance(runs)
  run_ids = tuple(item["run_id"] for item in provenance)
  surface = SurfaceKind(value["surface"])
  if surface is SurfaceKind.TOKEN:
    selection = value.get("selection", {})
    observations = load_public_text_observations(
        runs, agent_id=selection.get("agent_id"), recipient=selection.get("recipient"),
        rounds=selection.get("rounds"), flow_order=selection.get("flow_order"))
    data_kind = DataKind.TEXT
  else:
    observations = _load_vector_observations(value, config_path, runs, surface)
    data_kind = DataKind.VECTOR if value["localizer"]["type"] == "vector" else DataKind.STRUCTURED
  secret = SecretSpec.from_dict(value["secret"])
  datasets, leakage = build_matched_datasets(
      observations, secret=secret, labels=value["labels"],
      matched_groups=value["matched_groups"], data_kind=data_kind,
      minimum_samples=value.get("minimum_samples", 6))
  split = value.get("split", {})
  null = value.get("null_test", {})
  localization_config = LocalizationConfig(
      split=SplitConfig(
          split.get("train_ratio", 0.6), split.get("validation_ratio", 0.2),
          split.get("test_ratio", 0.2), split.get("seed", 0)),
      null_repetitions=null.get("repetitions", 20),
      significance_alpha=null.get("alpha", 0.05),
      bootstrap_repetitions=value.get("bootstrap_repetitions", 200),
      top_k=value.get("aggregation", {}).get("top_k", 5),
  )
  protocol_fingerprint = analysis_protocol_fingerprint(value)
  analysis_id = _new_id("analysis")
  factory = _localizer_factory(value["localizer"])
  localization = localize_datasets(
      datasets, factory, localization_config, analysis_id=analysis_id,
      run_ids=run_ids, protocol_fingerprint=protocol_fingerprint,
      metadata={"leakage_audit": leakage.to_dict(), "dataset_count": len(datasets),
                "surface": surface.value},
  )
  parent = (Path(output).expanduser().resolve() if output is not None
            else config_path.parent.parent / "outputs")
  directory = parent / analysis_id
  directory.mkdir(parents=True, exist_ok=False)
  _write_json(directory / "localization.json", localization.to_dict())
  _write_json(directory / "null-tests.json", {
      "schema_version": "stegopot.null-tests/1", "analysis_id": analysis_id,
      "units": [{"unit": item.unit.to_dict(), **item.null_test.to_dict()}
                for item in localization.units],
  })
  (directory / "localization.md").write_text(_render_localization(localization),
                                               encoding="utf-8", newline="\n")
  manifest = {
      "schema_version": "stegopot.analysis-manifest/1", "analysis_id": analysis_id,
      "created_at": datetime.now(timezone.utc).isoformat(), "kind": "localization",
      "source_runs": list(provenance), "protocol_fingerprint": protocol_fingerprint,
      "config_protocol_sha256": protocol_fingerprint,
      "label_count": len(value["labels"]),
      "matched_group_count": len(set(value["matched_groups"].values())),
      "secret": secret.to_dict(), "surface": surface.value,
      "leakage_audit": leakage.to_dict(),
      "artifacts": {name: file_digest(directory / name) for name in (
          "localization.json", "localization.md", "null-tests.json")},
      "note": "中央标签值未写入分析输出；原实验只读且已重新核验。",
  }
  _write_json(directory / "analysis-manifest.json", manifest)
  _write_analysis_seal(directory, ("analysis-manifest.json", "localization.json",
                                   "localization.md", "null-tests.json"))
  assert_runs_unchanged(provenance)
  return localization, directory


def attribute_path(
    analysis: str | Path,
    *,
    interventions: str | Path | None = None,
) -> tuple[CausalPathGraph, Path]:
  """读取定位地图和真实反事实结果，写出 path.json。

  参数：
    analysis: 含 localization.json 的分析目录。
    interventions: 干预结果 JSON；默认 analysis/interventions.json。

  返回：
    研究级路径图及分析目录。缺少干预数据时不会伪造 causal_score。
  """
  directory = Path(analysis).expanduser().resolve()
  _verify_analysis_seal(directory, "analysis-seal.json")
  localization = LocalizationMap.from_dict(_read_json(directory / "localization.json"))
  source = (directory / "interventions.json" if interventions is None
            else Path(interventions).expanduser().resolve())
  value = _read_json(source)
  records = value.get("interventions") if isinstance(value, Mapping) else None
  if not isinstance(records, list) or not records:
    raise ValueError("干预文件必须包含非空 interventions 数组")
  graph = build_path_graph(localization, parse_interventions(records))
  _write_json(directory / "path.json", graph.to_dict())
  _write_named_seal(directory, "path-seal.json", ("path.json", "localization.json"))
  return graph, directory


def combine_localizations(
    analyses: Sequence[str | Path],
    *,
    output: str | Path | None = None,
) -> tuple[LocalizationMap, Path]:
  """把同一批运行的多表面定位地图组合成一个封印分析。

  参数：
    analyses: 两个或更多已封印定位分析目录。
    output: 可选结果父目录；默认使用第一张地图的同级目录。

  返回：
    组合 LocalizationMap 和新建分析目录。
  """
  directories = tuple(Path(item).expanduser().resolve() for item in analyses)
  if len(directories) < 2:
    raise ValueError("combine 至少需要两个定位分析目录")
  maps = []
  for directory in directories:
    _verify_analysis_seal(directory, "analysis-seal.json")
    maps.append(LocalizationMap.from_dict(_read_json(directory / "localization.json")))
  analysis_id = _new_id("analysis-combined")
  localization = merge_localization_maps(maps, analysis_id=analysis_id)
  parent = (Path(output).expanduser().resolve() if output is not None else directories[0].parent)
  directory = parent / analysis_id
  directory.mkdir(parents=True, exist_ok=False)
  _write_json(directory / "localization.json", localization.to_dict())
  _write_json(directory / "null-tests.json", {
      "schema_version": "stegopot.null-tests/1", "analysis_id": analysis_id,
      "units": [{"unit": item.unit.to_dict(), **item.null_test.to_dict()}
                for item in localization.units],
  })
  (directory / "localization.md").write_text(_render_localization(localization),
                                               encoding="utf-8", newline="\n")
  _write_json(directory / "analysis-manifest.json", {
      "schema_version": "stegopot.analysis-manifest/1", "analysis_id": analysis_id,
      "created_at": datetime.now(timezone.utc).isoformat(), "kind": "combined_localization",
      "source_analyses": [{"analysis_id": item.analysis_id,
                           "directory": str(source),
                           "seal_sha256": file_digest(source / "analysis-seal.json")}
                          for item, source in zip(maps, directories, strict=True)],
      "source_runs": list(localization.run_ids),
      "protocol_fingerprint": localization.protocol_fingerprint,
      "secret": localization.secret.to_dict(),
      "artifacts": {name: file_digest(directory / name) for name in (
          "localization.json", "localization.md", "null-tests.json")},
  })
  _write_analysis_seal(directory, ("analysis-manifest.json", "localization.json",
                                   "localization.md", "null-tests.json"))
  return localization, directory


def compare_paths(
    before: str | Path,
    after: str | Path,
    *,
    output: str | Path | None = None,
) -> tuple[dict[str, Any], Path]:
  """比较同一协议的两张路径图，并创建独立 migration 分析目录。"""
  before_graph = _read_graph(before)
  after_graph = _read_graph(after)
  report = compare_path_graphs(before_graph, after_graph).to_dict()
  parent = (Path(output).expanduser().resolve() if output is not None
            else Path(after).expanduser().resolve().parent)
  directory = parent / _new_id("migration")
  directory.mkdir(parents=True, exist_ok=False)
  _write_json(directory / "migration.json", report)
  _write_json(directory / "analysis-manifest.json", {
      "schema_version": "stegopot.analysis-manifest/1",
      "analysis_id": directory.name, "kind": "path_migration",
      "created_at": datetime.now(timezone.utc).isoformat(),
      "before_analysis_id": before_graph.analysis_id,
      "after_analysis_id": after_graph.analysis_id,
      "protocol_fingerprint": before_graph.protocol_fingerprint,
  })
  _write_analysis_seal(directory, ("analysis-manifest.json", "migration.json"))
  return report, directory


def _load_vector_observations(config, config_path, runs, surface):
  """验证表征包后转换为不带中央标签的观测。"""
  by_run = {}
  for run in runs:
    manifest = _read_json(run / "manifest.json")
    by_run[manifest["run_id"]] = run
  readers = []
  for item in config["representation_bundles"]:
    path = Path(item).expanduser()
    path = (config_path.parent / path).resolve() if not path.is_absolute() else path.resolve()
    index = _read_json(path / "index.json")
    run_id = index.get("run_id")
    if run_id not in by_run:
      raise ValueError(f"表征包 {path} 未绑定到本次来源运行")
    readers.append(RepresentationReader(path, source_run=by_run[run_id]))
  values = load_representation_observations(readers, surface=surface.value)
  return tuple(CapturedObservation(unit["run_id"], unit["trial_id"],
                                   ObservationAddress.from_dict(unit["address"]), vector, {})
               for unit, vector in values)


def _localizer_factory(spec):
  """构造返回全新定位器的工厂，避免 null test 共享状态。"""
  config = dict(spec.get("config", {}))
  classes = {"text": TextSecretProbe, "vector": LinearSecretProbe,
             "structured": StructuredSecretProbe}
  implementation = classes[spec["type"]]
  return lambda: implementation(**config)


def _new_id(prefix: str) -> str:
  """生成不可预测且不编码秘密的分析 ID。"""
  return datetime.now(timezone.utc).strftime(f"{prefix}-%Y%m%dT%H%M%SZ-") + uuid4().hex[:8]


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
  """独占写入 JSON，不覆盖已有研究证据。"""
  with path.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
    stream.write("\n")


def _read_json(path: Path) -> Any:
  """读取 UTF-8 JSON。"""
  return json.loads(path.read_text(encoding="utf-8"))


def _read_graph(value: str | Path) -> CausalPathGraph:
  """接受 path.json 或包含它的分析目录。"""
  path = Path(value).expanduser().resolve()
  if path.is_dir():
    _verify_analysis_seal(path, "analysis-seal.json")
    _verify_analysis_seal(path, "path-seal.json")
    path = path / "path.json"
  else:
    _verify_analysis_seal(path.parent, "path-seal.json")
  return CausalPathGraph.from_dict(_read_json(path))


def _write_analysis_seal(directory: Path, artifacts: Sequence[str]) -> None:
  """写入分析基础工件封印。"""
  _write_named_seal(directory, "analysis-seal.json", artifacts)


def _write_named_seal(directory: Path, name: str, artifacts: Sequence[str]) -> None:
  """独占写入指定工件摘要集合。"""
  _write_json(directory / name, {
      "schema_version": "stegopot.analysis-seal/1",
      "artifacts": {item: file_digest(directory / item) for item in artifacts},
  })


def _verify_analysis_seal(directory: Path, name: str) -> None:
  """验证分析工件摘要；没有外部锚点时不宣称数字签名。"""
  seal = _read_json(directory / name)
  if seal.get("schema_version") != "stegopot.analysis-seal/1":
    raise ValueError(f"未知分析封印版本：{name}")
  for artifact, checksum in seal.get("artifacts", {}).items():
    path = directory / artifact
    if Path(artifact).name != artifact or path.resolve().parent != directory:
      raise ValueError("分析封印包含越界路径")
    if file_digest(path) != checksum:
      raise ValueError(f"分析工件摘要不一致：{artifact}")


def _render_localization(value: LocalizationMap) -> str:
  """生成简洁、可审查的 Markdown 定位摘要。"""
  lines = [f"# Secret Localization: {value.analysis_id}", "",
           f"- Secret: `{value.secret.name}` ({value.secret.kind.value})",
           f"- Source runs: {', '.join(f'`{item}`' for item in value.run_ids)}",
           f"- Protocol: `{value.protocol_fingerprint}`", "", "## Surface Summary", "",
           "| Surface | Peak | Top-K Mean | Significant | Units |", "| --- | ---: | ---: | ---: | ---: |"]
  for item in value.surface_scores:
    lines.append(f"| {item.surface.value} | {item.peak_score:.4f} | {item.top_k_mean:.4f} | "
                 f"{item.significant_unit_ratio:.2%} | {item.unit_count} |")
  lines.extend(["", "## Units", "",
                "| Surface | Agent | Score | Null mean | p-value | Significant |",
                "| --- | --- | ---: | ---: | ---: | --- |"])
  for item in value.units:
    lines.append(f"| {item.unit.surface.value} | {item.unit.agent_id or '-'} | "
                 f"{item.metrics.score:.4f} | {item.null_test.mean_score:.4f} | "
                 f"{item.null_test.p_value:.4f} | {'yes' if item.significant else 'no'} |")
  return "\n".join(lines) + "\n"
