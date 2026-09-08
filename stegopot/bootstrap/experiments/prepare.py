"""配置预检与计划编译；执行前发现所有已声明的类型和引用错误。"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
import os
from typing import Any

from stegopot.bootstrap.experiments.builtin import builtin_plugin
from stegopot.bootstrap.experiments.components import PlanningContext
from stegopot.application.services.threat_model import ThreatModelCompiler
from stegopot.domain.model.experiment import (
    ComponentSpec,
    EpisodeSpec,
    ExperimentPlan,
    json_copy,
)
from stegopot.domain.model.diagnostic import Diagnostic, PreflightContext, PreflightError
from stegopot.domain.model.threat import ThreatModelManifest, ThreatModelSpec
from stegopot.infrastructure.plugins.catalog import PluginCatalog
from stegopot.infrastructure.settings.experiment import validate_config


@dataclass(frozen=True)
class PreparedExperiment:
  """已校验配置、计划和威胁模型。

  属性：
    config: 已填入宿主默认值的标准配置副本。
    plan: 场景展开并应用拓扑、策略和评价器覆盖后的固定计划。
    threat_model: 根据最终计划编译的有效信息可见性清单。
    catalog: 已完成组件校验并冻结的插件注册表。
    resources: 配置声明的模型、codec 与通用 Tool 资源引用。
    credentials: 仅供组合根注入的授权凭证，不参与 repr。
    diagnostics: 不阻止运行的 warning 和 info 级预检结果。
  """

  config: Mapping[str, Any]
  plan: ExperimentPlan
  threat_model: ThreatModelManifest
  catalog: PluginCatalog
  resources: Mapping[str, ComponentSpec]
  credentials: Mapping[str, str] = field(repr=False)
  diagnostics: tuple[Diagnostic, ...] = ()


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
    if kind not in {"llm", "codec", "tool"}:
      raise ValueError("resources 只接受模型、隐写 codec 或通用工具")
    catalog.validate(spec, kind)
  source_env = os.environ if environment is None else environment
  credentials = {}
  diagnostics: list[Diagnostic] = []

  def check(spec, kind, chain=(), *, context=None):
    """递归校验 spec/kind 和 chain 资源依赖，解析显式凭证引用。"""
    context = context or PreflightContext(path=f"{kind}.config")
    definition = catalog.validate(spec, kind, path=context.path)
    if kind == "scenario" and (definition.references or definition.credentials):
      raise ValueError("场景插件只能生成计划，不能声明运行资源或凭证")
    if kind == "evaluator" and (definition.references or definition.credentials):
      raise ValueError("评价器必须可离线复算，不能声明运行资源或凭证")
    for slot, expected in definition.references.items():
      if slot not in spec.config:
        continue
      name = spec.config[slot]
      if name not in resources:
        raise ValueError(f"组件 {spec.type} 引用未声明的资源槽位 {slot}")
      if name in chain:
        raise ValueError("资源依赖存在循环")
      check(resources[name], expected, (*chain, name),
            context=PreflightContext(path=f"resources.{name}.config"))
    for slot in definition.credentials:
      if slot in spec.config:
        name = spec.config[slot]
        if not isinstance(name, str) or not name.isidentifier():
          raise ValueError("凭证配置必须是环境变量名称，不允许填写真实密钥")
        secret = source_env.get(name)
        if not secret:
          raise PreflightError([Diagnostic(
              "credential.missing", context.path + "." + slot, "缺少声明的环境凭证",
              "在工作区 .env 或当前进程中设置该环境变量", component=spec.type)])
        credentials[name] = secret
    if definition.preflight is not None:
      try:
        issues = tuple(definition.preflight(json_copy(spec.config), context))
        if any(not isinstance(issue, Diagnostic) for issue in issues):
          raise TypeError("预检钩子必须返回 Diagnostic 序列")
      except Exception as exc:
        raise PreflightError([Diagnostic(
            "preflight.hook_failed", context.path, "组件纯预检钩子执行失败",
            "检查钩子返回类型与纯函数约定；错误类型：" + type(exc).__name__,
            component=spec.type)]) from exc
      diagnostics.extend(replace(issue, component=issue.component or spec.type) for issue in issues)
    return definition

  scenario_spec = ComponentSpec.from_dict(config["scenario"])
  definition = check(scenario_spec, "scenario", context=PreflightContext("scenario.config"))
  scenario = definition.factory(json_copy(scenario_spec.config), PlanningContext())
  plan = scenario.plan(config["seed"])
  if not isinstance(plan, ExperimentPlan):
    raise TypeError("场景必须返回 ExperimentPlan，而不是自行执行实验")
  if len(plan.trials) > config["runtime"]["max_trials"]:
    raise ValueError("展开后的试验数超过 max_trials")
  trials = []
  known_policy_calls = 0
  for trial_index, trial in enumerate(plan.trials):
    ids = {node.node_id for node in trial.nodes}
    if set(config["policies"]) - ids:
      raise ValueError("策略覆盖引用场景中不存在的节点")
    nodes = tuple(replace(node, policy=ComponentSpec.from_dict(config["policies"][node.node_id]))
                  if node.node_id in config["policies"] else node for node in trial.nodes)
    trial = replace(trial, nodes=nodes,
                    edges=config.get("topology", {}).get("edges", trial.edges))
    paired = trial.paired_spec
    if paired and (paired.sender, paired.recipient) not in trial.edges:
      raise PreflightError([Diagnostic(
          "replay.missing_edge", f"plan.trials[{trial_index}].edges",
          "重放发送者与接收者之间没有授权通信边", "添加该方向的拓扑边")])
    if trial.max_rounds > config["runtime"]["max_rounds"]:
      raise ValueError("场景轮数超过宿主 max_rounds 上限")
    effective_channels = (
        tuple(ComponentSpec.from_dict(value) for value in config["channels"])
        if trial.channels is None else trial.channels
    )
    effective_detectors = (
        tuple(ComponentSpec.from_dict(value) for value in config["detectors"])
        if trial.detectors is None else trial.detectors
    )
    effective_rewards = (
        tuple(ComponentSpec.from_dict(value) for value in config["rewards"])
        if trial.rewards is None else trial.rewards
    )
    trial = replace(
        trial,
        channels=effective_channels,
        detectors=effective_detectors,
        rewards=effective_rewards,
    )
    check(trial.substrate, "substrate")
    for spec in trial.channels:
      check(spec, "channel")
    for spec in trial.detectors:
      check(spec, "detector")
    for spec in trial.rewards:
      check(spec, "reward")
    for node_index, node in enumerate(nodes):
      for tool_alias, tool_spec in node.tools.items():
        check(
            tool_spec,
            "tool",
            context=PreflightContext(
                path=(
                    f"plan.trials[{trial_index}].nodes[{node_index}]"
                    f".tools.{tool_alias}.config"
                ),
                node_id=node.node_id,
                max_rounds=trial.max_rounds,
            ),
        )
      if paired and node.node_id == paired.sender:
        # 重放实际使用宿主固定动作，不构造原策略，也不要求其运行资源或秘密材料。
        catalog.validate(node.policy, "policy")
        continue
      check(node.policy, "policy", context=PreflightContext(
          path=f"plan.trials[{trial_index}].nodes[{node_index}].policy.config",
          node_id=node.node_id, max_rounds=trial.max_rounds,
          outgoing=tuple(target for source, target in trial.edges if source == node.node_id),
          incoming=tuple(source for source, target in trial.edges if target == node.node_id),
          private=json_copy(trial.node_contexts.get(node.node_id, {})),
          tools=tuple(node.tools),
      ))
      if node.policy.type == "core.llm" and not (paired and node.node_id == paired.sender):
        known_policy_calls += 1 if "active_round" in node.policy.config else trial.max_rounds
    trials.append(trial)
  evaluators = tuple(plan.evaluators) + tuple(
      ComponentSpec.from_dict(spec) for spec in config["evaluators"]
  )
  if len({spec.type for spec in evaluators}) != len(evaluators):
    raise ValueError("中央评分器 ID 不能重复，请在插件内提供不同命名组件")
  for spec in evaluators:
    check(spec, "evaluator")
  outcome_rewards = tuple(plan.outcome_rewards) + tuple(
      ComponentSpec.from_dict(spec) for spec in config["outcome_rewards"]
  )
  if len({spec.type for spec in outcome_rewards}) != len(outcome_rewards):
    raise ValueError("结果奖励器 ID 不能重复，请在插件内提供不同命名组件")
  for spec in outcome_rewards:
    check(spec, "outcome_reward")
  for field_name, kind in (("audit_sinks", "audit"),):
    for value in config[field_name]:
      check(ComponentSpec.from_dict(value), kind)
  if known_policy_calls > config["runtime"]["max_model_calls"]:
    raise ValueError(f"已知 LLM 策略最多需要 {known_policy_calls} 次调用，超过 max_model_calls")
  if any(item.severity == "error" for item in diagnostics):
    raise PreflightError(diagnostics)
  prepared_by_id = {trial.trial_id: trial for trial in trials}
  standalone = tuple(
      prepared_by_id[trial.trial_id]
      for trial in plan.standalone_trials
  )
  sessions = tuple(
      replace(
          session,
          episodes=tuple(
              prepared_by_id[episode.episode_id]
              for episode in session.episodes
          ),
      )
      for session in plan.sessions
  )
  if any(
      not isinstance(episode, EpisodeSpec)
      for session in sessions
      for episode in session.episodes
  ):
    raise TypeError("Session 计划在预检后必须继续使用 EpisodeSpec")
  final_plan = ExperimentPlan(
      trials=standalone,
      evaluators=evaluators,
      sessions=sessions,
      outcome_rewards=outcome_rewards,
  )
  threat_model = ThreatModelCompiler().compile(
      final_plan,
      ThreatModelSpec.from_dict(config["threat_model"]),
  )
  catalog.freeze()
  return PreparedExperiment(
      config=config,
      plan=final_plan,
      threat_model=threat_model,
      catalog=catalog,
      resources=resources,
      credentials=credentials,
      diagnostics=tuple(diagnostics),
  )
