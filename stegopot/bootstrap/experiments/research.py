"""schema_version=2 的通用受控模型实验准备与执行。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from stegopot.application.services.data.pipeline import DatasetPipeline
from stegopot.application.services.research.engine import ResearchExperimentEngine
from stegopot.application.services.runtime.events import InMemoryEventBus
from stegopot.application.services.runtime.model import ModelRuntime
from stegopot.bootstrap.experiments.builtin import builtin_plugin
from stegopot.bootstrap.experiments.components import ComponentSession
from stegopot.domain.model.capability import Capability, MissingCapabilityError
from stegopot.domain.model.context import ExperimentContext, ResearchExperimentResult
from stegopot.domain.model.data import SplitPolicy
from stegopot.domain.model.diagnostic import Diagnostic, PreflightContext, PreflightError
from stegopot.domain.model.events import RuntimeEvent
from stegopot.domain.model.experiment import ComponentSpec, json_copy
from stegopot.infrastructure.llm.audit import CallBudget
from stegopot.infrastructure.plugins.catalog import PluginCatalog
from stegopot.infrastructure.storage.artifacts import FileArtifactStore
from stegopot.infrastructure.settings.diagnostics import environment_manifest
from stegopot.infrastructure.settings.experiment import validate_config


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass(frozen=True)
class PreparedResearchExperiment:
  """已校验但尚未加载模型或创建输出目录的研究配置。"""

  config: Mapping[str, Any] = field(metadata=_description("填入默认值的配置副本。"))
  catalog: PluginCatalog = field(
      repr=False, metadata=_description("本次运行独占且已冻结的组件目录。"))
  resources: Mapping[str, ComponentSpec] = field(
      metadata=_description("组件可以显式引用的资源声明。"))
  credentials: Mapping[str, str] = field(
      repr=False, metadata=_description("按工厂声明收集的凭证值。"))
  required_capabilities: Sequence[Capability] = field(
      metadata=_description("全部实验插件合并后的后端能力要求。"))
  diagnostics: Sequence[Diagnostic] = field(
      default_factory=tuple, metadata=_description("不阻止运行的预检信息。"))


class _EventAudit:
  """把组件生命周期事件桥接到通用 EventBus。"""

  def __init__(self, bus: InMemoryEventBus, run_id: str) -> None:
    self._bus = bus
    self._run_id = run_id

  def emit(self, event: Mapping[str, Any]) -> None:
    kind = str(event.get("kind", "plugin.event"))
    self._bus.emit(RuntimeEvent(kind, self._run_id, data=dict(event)))


def prepare_research_experiment(
    value: Mapping[str, Any], *, catalog: PluginCatalog | None = None,
    environment: Mapping[str, str] | None = None,
) -> PreparedResearchExperiment:
  """完成组件、引用、凭证和 capability 预检，不构造模型。"""
  config = validate_config(value)
  if config.get("schema_version") != "2":
    raise ValueError("通用研究入口只接受 schema_version=2")
  if catalog is None:
    catalog = PluginCatalog(builtin_plugin())
    catalog.load(config["plugins"])
  resources = {
      name: ComponentSpec.from_dict(spec)
      for name, spec in config["resources"].items()
  }
  source_env = os.environ if environment is None else environment
  credentials: dict[str, str] = {}
  diagnostics: list[Diagnostic] = []
  requirements: set[Capability] = set()
  visiting: set[str] = set()

  def check(spec: ComponentSpec, kind: str, path: str) -> None:
    """递归检查单个组件及其显式资源引用。"""
    definition = catalog.validate(spec, kind, path=path)
    requirements.update(definition.requires_capabilities)
    context = PreflightContext(path=path)
    for slot, expected_kind in definition.references.items():
      if slot not in spec.config:
        continue
      resource_name = spec.config[slot]
      if resource_name not in resources:
        raise ValueError(f"组件 {spec.type} 引用了未声明资源 {resource_name}")
      if resource_name in visiting:
        raise ValueError("组件资源依赖存在循环")
      visiting.add(resource_name)
      try:
        check(
            resources[resource_name], expected_kind,
            f"resources.{resource_name}.config")
      finally:
        visiting.remove(resource_name)
    for field_name in definition.credentials:
      if field_name not in spec.config:
        continue
      env_name = spec.config[field_name]
      if not isinstance(env_name, str) or not env_name.isidentifier():
        raise ValueError("凭证配置必须填写环境变量名")
      secret = source_env.get(env_name)
      if not secret:
        raise PreflightError([Diagnostic(
            "credential.missing", f"{path}.{field_name}",
            "缺少声明的环境凭证",
            "在工作区 .env 或当前进程中设置该环境变量",
            component=spec.type)])
      credentials[env_name] = secret
    if definition.preflight is not None:
      try:
        issues = tuple(definition.preflight(json_copy(spec.config), context))
      except Exception as exc:
        raise PreflightError([Diagnostic(
            "preflight.hook_failed", path, "组件纯预检钩子执行失败",
            f"检查插件预检实现；错误类型：{type(exc).__name__}",
            component=spec.type)]) from exc
      if any(not isinstance(item, Diagnostic) for item in issues):
        raise TypeError("组件预检必须返回 Diagnostic 序列")
      diagnostics.extend(
          replace(item, component=item.component or spec.type)
          for item in issues)

  adapter = ComponentSpec.from_dict(config["runtime"]["adapter"])
  check(adapter, "model_adapter", "runtime.adapter.config")
  roots = [
      (ComponentSpec.from_dict(config["dataset"]["source"]),
       "dataset", "dataset.source.config"),
      (ComponentSpec.from_dict(config["scenario"]),
       "scenario", "scenario.config"),
  ]
  roots.extend(
      (ComponentSpec.from_dict(item), kind, f"{name}[{index}].config")
      for name, kind in (
          ("dataset.transforms", "transform"),
          ("dataset.validators", "validator"),
          ("analyzers", "analyzer"),
          ("metrics", "metric"),
          ("reporters", "reporter"))
      for index, item in enumerate(_path_value(config, name))
  )
  for spec, kind, path in roots:
    check(spec, kind, path)
  adapter_definition = catalog.definition(adapter.type)
  provided = frozenset(adapter_definition.provides_capabilities)
  if not requirements.issubset(provided):
    raise MissingCapabilityError(requirements, provided)
  catalog.freeze()
  return PreparedResearchExperiment(
      json_copy(config), catalog, resources, credentials,
      tuple(sorted(requirements, key=lambda item: item.value)),
      tuple(diagnostics))


def run_research_experiment(
    prepared: PreparedResearchExperiment, *, output: str | Path,
    event_bus: InMemoryEventBus | None = None,
) -> tuple[ResearchExperimentResult, Path]:
  """构造组件并运行通用 Dataset -> Scenario -> Analysis 生命周期。"""
  config = prepared.config
  run_id = (
      datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
      + "-" + uuid4().hex[:10])
  directory = Path(output).expanduser().resolve() / run_id
  store = FileArtifactStore(directory)
  bus = event_bus or InMemoryEventBus()
  audit = _EventAudit(bus, run_id)
  budget = CallBudget(config["runtime"]["max_model_calls"])
  session = ComponentSession(
      prepared.catalog, resources=prepared.resources,
      credentials=prepared.credentials, audit=audit, budget=budget,
      max_output_tokens=config["runtime"]["max_output_tokens"])
  runtime = None
  try:
    adapter_spec = ComponentSpec.from_dict(config["runtime"]["adapter"])
    adapter = session.create(adapter_spec, "model_adapter")
    runtime = ModelRuntime(adapter, event_bus=bus, own_adapter=False)
    runtime.require(prepared.required_capabilities)
    context = ExperimentContext(
        run_id=run_id, seed=config["seed"], config=config,
        runtime=runtime, artifact_store=store, event_bus=bus,
        metadata={
            "stegopot_config_schema": "2",
            "plugins": prepared.catalog.describe(),
            "environment": environment_manifest(),
            "model_adapter": adapter.adapter_id,
            "model_id": adapter.model_id,
        })
    dataset_config = config["dataset"]
    split = dataset_config["split"]
    pipeline = DatasetPipeline(
        source=session.create(
            ComponentSpec.from_dict(dataset_config["source"]), "dataset"),
        transforms=tuple(
            session.create(ComponentSpec.from_dict(item), "transform")
            for item in dataset_config["transforms"]),
        validators=tuple(
            session.create(ComponentSpec.from_dict(item), "validator")
            for item in dataset_config["validators"]),
        split=SplitPolicy(
            split["train"], split["validation"], split["test"],
            split["seed"], split["group_key"]))
    dataset = pipeline.prepare(dataset_config["count"], context)
    engine = ResearchExperimentEngine(
        scenario=session.create(
            ComponentSpec.from_dict(config["scenario"]), "scenario"),
        analyzers=tuple(
            session.create(ComponentSpec.from_dict(item), "analyzer")
            for item in config["analyzers"]),
        metrics=tuple(
            session.create(ComponentSpec.from_dict(item), "metric")
            for item in config["metrics"]),
        reporters=tuple(
            session.create(ComponentSpec.from_dict(item), "reporter")
            for item in config["reporters"]))
    result = engine.run(dataset, context, partitions=config["partitions"])
    return result, directory
  finally:
    if runtime is not None:
      runtime.close()
    session.close()
    store.close()


def _path_value(config: Mapping[str, Any], path: str) -> Sequence[Any]:
  """读取本模块使用的固定一层或两层配置路径。"""
  value: Any = config
  for part in path.split("."):
    value = value[part]
  return value
