"""将标准 TrialSpec 接线到已有的多智能体引擎。"""

from stegopot.application.engine.pipeline import ExperimentPipeline
from stegopot.application.engine.runtime import MultiAgentRuntime, RuntimeConfig
from stegopot.bootstrap.builder import MultiAgentBuilder
from stegopot.bootstrap.experiments.components import ComponentSession
from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.model.action import AgentAction
from stegopot.domain.model.experiment import PairedCarrier, TrialSpec
from stegopot.domain.model.threat import ThreatModelManifest
from stegopot.infrastructure.llm.scheduling import FixedActionPolicy, RoundPolicy


def build_runtime(
    trial: TrialSpec, *, session: ComponentSession, audit: AuditSink,
    config: dict, paired_carrier: PairedCarrier | None = None,
    threat_model: ThreatModelManifest,
    control: ExecutionGuard | None = None,
) -> MultiAgentRuntime:
  """组装独立试验运行器，不实现具体实验算法。

  参数：
    trial: 已展开并校验的节点、拓扑和环境声明。
    session: 持有工厂和本次资源的组件会话。
    audit: 宿主审计接口。
    config: 已预检的全局信道、检测与奖励配置。
    paired_carrier: 已完成源试验的固定载体；None 表示使用原节点策略。
    threat_model: 预检编译的有效威胁模型，控制策略历史和检测器上下文。
    control: 本次试验的预算与取消接口，同时注入引擎和公开管线。
  """
  builder = MultiAgentBuilder()
  tools = {}
  paired = trial.paired_spec
  for node in trial.nodes:
    if paired and node.node_id == paired.sender:
      if paired_carrier is None:
        raise ValueError("重放试验没有源正文")
      policy = RoundPolicy(FixedActionPolicy(AgentAction.message(
          paired_carrier.content, target=paired.recipient,
          communication=paired_carrier.communication,
      )), active_round=0)
    else:
      policy = session.create(node.policy, "policy", node_id=node.node_id)
    builder.add_node(node_id=node.node_id, role=node.role, policy=policy)
    tools[node.node_id] = {
        alias: session.create(spec, "tool", node_id=node.node_id)
        for alias, spec in node.tools.items()
    }
  for source, target in trial.edges:
    builder.connect(source, target)
  inner = session.create(trial.substrate, "substrate")

  def components(specs, kind):
    """按 Trial 固定顺序组装 specs 中的 kind 组件。"""
    return [(spec.type, session.create(spec, kind)) for spec in specs]

  pipeline = ExperimentPipeline(inner, audit=audit, node_contexts=trial.node_contexts,
                                channels=components(trial.channels or (), "channel"),
                                detectors=components(trial.detectors or (), "detector"),
                                rewards=components(trial.rewards or (), "reward"),
                                threat_model=threat_model,
                                information_views=_information_views(trial, threat_model),
                                control=control)
  return builder.build(config=RuntimeConfig(max_rounds=trial.max_rounds, termination_mode="max_rounds",
                                            fail_fast=True, strict_routing=True),
                       substrate=pipeline, audit_sink=audit, control=control,
                       tools=tools)


def _information_views(
    trial: TrialSpec,
    threat_model: ThreatModelManifest,
) -> dict[str, dict]:
  """按已编译清单返回当前 Trial 的主体信息值，不自行扩大可见范围。"""
  flow = threat_model.information_flows.get(trial.trial_id)
  if flow is None:
    if trial.information:
      raise ValueError("威胁模型缺少当前 Trial 的信息流目录")
    return {}
  result = {}
  for principal, names in flow.principal_assets.items():
    values = trial.information_for(principal)
    if set(values) != set(names):
      raise ValueError("实际信息投影与预检威胁模型不一致")
    result[principal] = values
  return result
