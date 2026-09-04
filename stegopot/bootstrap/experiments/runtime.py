"""将标准 TrialSpec 接线到已有的多智能体引擎。"""

from stegopot.application.engine.pipeline import ExperimentPipeline
from stegopot.application.engine.runtime import MultiAgentRuntime, RuntimeConfig
from stegopot.bootstrap.builder import MultiAgentBuilder
from stegopot.bootstrap.experiments.components import ComponentSession
from stegopot.domain.interface.audit import AuditSink
from stegopot.domain.interface.execution import ExecutionGuard
from stegopot.domain.model.action import AgentAction
from stegopot.domain.model.experiment import ComponentSpec, TrialSpec
from stegopot.infrastructure.llm.scheduling import FixedActionPolicy, RoundPolicy


def build_runtime(
    trial: TrialSpec, *, session: ComponentSession, audit: AuditSink,
    config: dict, replay_carrier: str | None = None,
    control: ExecutionGuard | None = None,
) -> MultiAgentRuntime:
  """组装独立试验运行器，不实现具体实验算法。

  参数：
    trial: 已展开并校验的节点、拓扑和环境声明。
    session: 持有工厂和本次资源的组件会话。
    audit: 宿主审计接口。
    config: 已预检的全局信道、检测与奖励配置。
    replay_carrier: 已完成前序试验的原文，None 表示使用原节点策略。
    control: 本次试验的预算与取消接口，同时注入引擎和公开管线。
  """
  builder = MultiAgentBuilder()
  for node in trial.nodes:
    if trial.replay and node.node_id == trial.replay.sender:
      if replay_carrier is None:
        raise ValueError("重放试验没有源正文")
      policy = RoundPolicy(FixedActionPolicy(AgentAction.message(
          replay_carrier, target=trial.replay.recipient)), active_round=0)
    else:
      policy = session.create(node.policy, "policy", node_id=node.node_id)
    builder.add_node(node_id=node.node_id, role=node.role, policy=policy)
  for source, target in trial.edges:
    builder.connect(source, target)
  inner = session.create(trial.substrate, "substrate")

  def components(field, kind):
    """按 config 的 field 顺序组装 kind 组件，不依赖插件注册顺序。"""
    specs = [ComponentSpec.from_dict(value) for value in config[field]]
    return [(spec.type, session.create(spec, kind)) for spec in specs]

  pipeline = ExperimentPipeline(inner, audit=audit, node_contexts=trial.node_contexts,
                                channels=components("channels", "channel"),
                                detectors=components("detectors", "detector"),
                                rewards=components("rewards", "reward"), control=control)
  return builder.build(config=RuntimeConfig(max_rounds=trial.max_rounds, termination_mode="max_rounds",
                                            fail_fast=True, strict_routing=True),
                       substrate=pipeline, audit_sink=audit, control=control)
