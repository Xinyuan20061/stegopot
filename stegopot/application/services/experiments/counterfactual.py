"""生成固定同一实际载体、只改变处理组件的配对反事实计划。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from stegopot.domain.model.experiment import (
    ComponentSpec,
    CounterfactualSpec,
    ExperimentPlan,
    NodeSpec,
    TrialSpec,
)
from stegopot.domain.model.information import InformationAsset


class CounterfactualScenario:
  """把一个源 Trial 和多个处理条件展开成严格配对计划。"""

  def __init__(self, config: Mapping[str, Any]) -> None:
    """保存已通过组件模式校验的 config。

    参数：
      config: 包含 source、carrier 和 treatments 的反事实场景参数。
    """
    self._config = dict(config)

  def plan(self, seed: int) -> ExperimentPlan:
    """按配置顺序生成源 Trial 和全部反事实分支。

    参数：
      seed: 中央运行种子；显式配对计划不随机采样，因此不使用该值。

    返回：
      源 Trial 位于首位、每个处理条件引用该源载体的 ExperimentPlan。
    """
    del seed
    source_data = self._config["source"]
    source = _trial(source_data)
    carrier = self._config["carrier"]
    frozen = tuple(self._config.get("frozen_fields", (
        "task",
        "shared_context",
        "node_contexts",
        "truth",
        "topology",
        "policies",
        "substrate",
    )))
    group_id = self._config.get("group_id", source.trial_id)
    branches = []
    for treatment in self._config["treatments"]:
      treatment_id = treatment["id"]
      branches.append(replace(
          source,
          trial_id=treatment.get(
              "trial_id",
              f"{source.trial_id}.{treatment_id}",
          ),
          channels=_components(treatment.get("channels", [])),
          detectors=_components(treatment.get("detectors", [])),
          rewards=_components(treatment.get("rewards", [])),
          counterfactual=CounterfactualSpec(
              source_trial=source.trial_id,
              sender=carrier["sender"],
              recipient=carrier["recipient"],
              treatment_id=treatment_id,
              group_id=group_id,
              source_message_id=carrier.get("message_id"),
              frozen_fields=frozen,
          ),
          replay=None,
      ))
    return ExperimentPlan(
        trials=(source, *branches),
        evaluators=(ComponentSpec("core.metrics"),),
    )


def _trial(data: Mapping[str, Any]) -> TrialSpec:
  """将 source 配置转换为不包含论文专用语义的 TrialSpec。"""
  nodes = tuple(NodeSpec(
      node_id=item["id"],
      role=item.get("role", item["id"]),
      policy=ComponentSpec.from_dict(item["policy"]),
      tools={
          name: ComponentSpec.from_dict(spec)
          for name, spec in item.get("tools", {}).items()
      },
  ) for item in data["nodes"])
  return TrialSpec(
      trial_id=data.get("id", "source"),
      task=data["task"],
      nodes=nodes,
      edges=tuple(tuple(edge) for edge in data["edges"]),
      substrate=ComponentSpec.from_dict(
          data.get("substrate", {"type": "core.communication"})
      ),
      shared_context=data.get("shared_context", {}),
      node_contexts=data.get("node_contexts", {}),
      truth=data.get("truth", {}),
      max_rounds=data.get("max_rounds", 2),
      information=tuple(
          InformationAsset.from_dict(name, value)
          for name, value in data.get("information", {}).items()
      ),
      channels=_components(data.get("channels")),
      detectors=_components(data.get("detectors")),
      rewards=_components(data.get("rewards")),
  )


def _components(
    values: Sequence[Mapping[str, Any]] | None,
) -> tuple[ComponentSpec, ...] | None:
  """转换可选处理组件；None 保留继承全局配置的语义。"""
  if values is None:
    return None
  return tuple(ComponentSpec.from_dict(value) for value in values)
