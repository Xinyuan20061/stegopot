"""配置预检与计划编译；执行前发现所有已声明的类型和引用错误。"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import os
from typing import Any

from stegopot.bootstrap.experiments.builtin import builtin_plugin
from stegopot.bootstrap.experiments.components import PlanningContext
from stegopot.domain.model.experiment import ComponentSpec, ExperimentPlan, json_copy
from stegopot.infrastructure.plugins.catalog import PluginCatalog
from stegopot.infrastructure.settings.experiment import validate_config


@dataclass(frozen=True)
class PreparedExperiment:
  """已校验配置。config/plan 为研究数据，catalog 为固定注册表，resources 为资源引用，credentials 不参与 repr。"""

  config: Mapping[str, Any]
  plan: ExperimentPlan
  catalog: PluginCatalog
  resources: Mapping[str, ComponentSpec]
  credentials: Mapping[str, str] = field(repr=False)


def prepare_experiment(
    value: Mapping[str, Any], *, catalog: PluginCatalog | None = None,
    environment: Mapping[str, str] | None = None,
) -> PreparedExperiment:
  """预检配置并展开计划，不创建模型客户端。

  参数：
    value: JSON/YAML 解析后的完整配置。
    catalog: 测试或嵌入调用者注入的注册表；为空时发现配置允许的 entry points。
    environment: 用于解析凭证的环境；为空时读取进程环境，只收集声明的字段。

  返回：
    可交给统一运行入口的准备结果。任何校验错误都发生在网络请求之前。
  """
  config = validate_config(value)
  if catalog is None:
    catalog = PluginCatalog(builtin_plugin())
    catalog.load(config["plugins"])
  resources = {name: ComponentSpec.from_dict(spec) for name, spec in config["resources"].items()}
  for spec in resources.values():
    kind = catalog.kind_of(spec.type)
    if kind not in {"llm", "codec"}:
      raise ValueError("resources 只接受模型或隐写 codec")
    catalog.validate(spec, kind)
  source_env = os.environ if environment is None else environment
  credentials = {}

  def check(spec, kind, chain=()):
    """递归校验 spec/kind 和 chain 资源依赖，解析显式凭证引用。"""
    definition = catalog.validate(spec, kind)
    if kind == "scenario" and (definition.references or definition.credentials):
      raise ValueError("场景插件只能生成计划，不能声明运行资源或凭证")
    for slot, expected in definition.references.items():
      if slot not in spec.config:
        continue
      name = spec.config[slot]
      if name not in resources:
        raise ValueError(f"组件 {spec.type} 引用未声明的资源槽位 {slot}")
      if name in chain:
        raise ValueError("资源依赖存在循环")
      check(resources[name], expected, (*chain, name))
    for slot in definition.credentials:
      if slot in spec.config:
        name = spec.config[slot]
        if not isinstance(name, str) or not name.isidentifier():
          raise ValueError("凭证配置必须是环境变量名称，不允许填写真实密钥")
        secret = source_env.get(name)
        if not secret:
          raise ValueError(f"组件 {spec.type} 缺少声明的环境凭证 {name}")
        credentials[name] = secret
    return definition

  scenario_spec = ComponentSpec.from_dict(config["scenario"])
  definition = check(scenario_spec, "scenario")
  scenario = definition.factory(json_copy(scenario_spec.config), PlanningContext())
  plan = scenario.plan(config["seed"])
  if not isinstance(plan, ExperimentPlan):
    raise TypeError("场景必须返回 ExperimentPlan，而不是自行执行实验")
  if len(plan.trials) > config["runtime"]["max_trials"]:
    raise ValueError("展开后的试验数超过 max_trials")
  trials = []
  known_policy_calls = 0
  for trial in plan.trials:
    ids = {node.node_id for node in trial.nodes}
    if set(config["policies"]) - ids:
      raise ValueError("策略覆盖引用场景中不存在的节点")
    nodes = tuple(replace(node, policy=ComponentSpec.from_dict(config["policies"][node.node_id]))
                  if node.node_id in config["policies"] else node for node in trial.nodes)
    trial = replace(trial, nodes=nodes,
                    edges=config.get("topology", {}).get("edges", trial.edges))
    if trial.max_rounds > config["runtime"]["max_rounds"]:
      raise ValueError("场景轮数超过宿主 max_rounds 上限")
    check(trial.substrate, "substrate")
    for node in nodes:
      check(node.policy, "policy")
      if node.policy.type == "core.llm" and not (trial.replay and node.node_id == trial.replay.sender):
        known_policy_calls += 1 if "active_round" in node.policy.config else trial.max_rounds
    trials.append(trial)
  evaluators = tuple(plan.evaluators) + tuple(ComponentSpec.from_dict(spec) for spec in config["evaluators"])
  if len({spec.type for spec in evaluators}) != len(evaluators):
    raise ValueError("中央评分器 ID 不能重复，请在插件内提供不同命名组件")
  for spec in evaluators:
    check(spec, "evaluator")
  for field_name, kind in (("channels", "channel"), ("detectors", "detector"),
                            ("rewards", "reward"), ("audit_sinks", "audit")):
    for value in config[field_name]:
      check(ComponentSpec.from_dict(value), kind)
  if known_policy_calls > config["runtime"]["max_model_calls"]:
    raise ValueError(f"已知 LLM 策略最多需要 {known_policy_calls} 次调用，超过 max_model_calls")
  catalog.freeze()
  return PreparedExperiment(config, ExperimentPlan(trials, evaluators), catalog, resources, credentials)
