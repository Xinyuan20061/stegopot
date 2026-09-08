"""将用户威胁模型声明编译成可执行、可封印的有效清单。"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from stegopot.domain.model.experiment import ExperimentPlan
from stegopot.domain.model.information import (
    ALL_NODES,
    InformationFlowView,
    node_principal,
)
from stegopot.domain.model.threat import ThreatModelManifest, ThreatModelSpec


def _digest(value: Any) -> str:
  """返回标准 JSON 数据的稳定 SHA-256 摘要。"""
  payload = json.dumps(
      value,
      ensure_ascii=False,
      sort_keys=True,
      separators=(",", ":"),
      allow_nan=False,
  ).encode("utf-8")
  return hashlib.sha256(payload).hexdigest()


class ThreatModelCompiler:
  """根据固定计划展开组件可见字段和宿主边界。"""

  def compile(
      self,
      plan: ExperimentPlan,
      spec: ThreatModelSpec,
  ) -> ThreatModelManifest:
    """编译 plan/spec，不构造组件、读取凭证或执行模型。

    参数：
      plan: 已完成节点、拓扑和评分器展开的中央实验计划。
      spec: 已通过配置模式和领域验证的威胁模型声明。

    返回：
      可直接注入运行管线并写入审计工件的不可变有效清单。
    """
    if not isinstance(plan, ExperimentPlan):
      raise TypeError("plan 必须是 ExperimentPlan")
    if not isinstance(spec, ThreatModelSpec):
      raise TypeError("spec 必须是 ThreatModelSpec")
    plan_data = plan.to_dict()
    topology = [
        {
            "trial_id": trial.trial_id,
            "nodes": [node.node_id for node in trial.nodes],
            "edges": [list(edge) for edge in trial.edges],
        }
        for trial in plan.trials
    ]
    policy_fields = [
        "task",
        "round_index",
        "self_identity",
        "local_topology",
        "inbox",
        "previous_action",
        "shared_context",
        "own_private_context",
        "own_reward",
    ]
    if spec.policy_view.public_channel_history:
      policy_fields.append("delivered_public_channel_history")
    detector_fields = [
        "delivered_message_id",
        "sender",
        "recipient",
        "content",
        "round_index",
    ]
    if spec.detector_view.public_experiment_context:
      detector_fields.append("public_experiment_context")
    component_views = {
        "policy": policy_fields,
        "substrate": [
            "task",
            "node_ids",
            "topology",
            "shared_context",
            "previous_episode_scalar_feedback",
            "actions",
            "routed_candidate_messages",
        ],
        "channel": ["candidate_message_identity", "candidate_message_content"],
        "detector": detector_fields,
        "reward": [
            "action_kinds",
            "action_targets",
            "delivered_messages",
            "bounded_detection_signals",
            "authorized_information_assets",
        ],
        "outcome_reward": [
            "condition_id",
            "session_id",
            "episode_id",
            "run_result",
            "truth",
            "authorized_information_assets",
        ],
        "evaluator": [
            "central_trial_spec",
            "run_result",
            "truth",
            "authorized_information_assets",
        ],
        "public_audit": ["topology", "delivered_messages", "minimal_status"],
        "research_audit": ["plan", "component_calls", "results", "failures"],
    }
    information_flows = {
        trial.trial_id: _compile_information_flow(trial)
        for trial in plan.trials
    }
    return ThreatModelManifest(
        schema_version="stegopot.threat-model/2",
        trust_model=spec.trust_model,
        policy_view=spec.policy_view,
        detector_view=spec.detector_view,
        audit=spec.audit,
        component_views=component_views,
        enforced_boundaries=(
            "policy_receives_only_own_private_context",
            "truth_is_reserved_for_central_evaluation_and_research_audit",
            "channel_receives_metadata_free_message_and_cannot_change_identity",
            "detector_receives_only_final_delivered_message_and_declared_public_context",
            "reward_receives_no_detector_reason_metadata_context_or_central_truth",
            "outcome_reward_returns_only_node_scalar_feedback",
            "truth_never_enters_policy_observation_or_policy_state_transfer",
            "policy_state_persists_only_inside_its_declared_session",
            "episode_substrate_and_message_inboxes_reset_before_each_episode",
            "public_audit_uses_unknown_event_deny_by_default_projection",
            "typed_information_assets_are_projected_by_principal_deny_by_default",
            "information_class_limits_cannot_be_widened_by_visible_to",
        ),
        assumptions=(
            "plugins_are_trusted_in_process",
            "host_visibility_contract_is_not_operating_system_isolation",
            "public_message_content_may_itself_disclose_private_information",
        ),
        plan_sha256=_digest(plan_data),
        topology_sha256=_digest(topology),
        information_flows=information_flows,
    )


def _compile_information_flow(trial) -> InformationFlowView:
  """把 trial 的显式信息声明编译成不含值的逐主体目录。"""
  principals = {
      principal
      for asset in trial.information
      for principal in asset.visible_to
      if principal != ALL_NODES
  }
  principals.update(node_principal(node.node_id) for node in trial.nodes)
  views = {principal: [] for principal in sorted(principals)}
  assets = {}
  for asset in trial.information:
    assets[asset.name] = asset.to_dict(include_value=False)
    for principal in views:
      if asset.is_visible_to(principal):
        views[principal].append(asset.name)
  specification = {
      asset.name: asset.to_dict(include_value=True)
      for asset in trial.information
  }
  return InformationFlowView(
      trial_id=trial.trial_id,
      assets=assets,
      principal_assets={name: tuple(values) for name, values in views.items()},
      specification_sha256=_digest(specification),
  )
