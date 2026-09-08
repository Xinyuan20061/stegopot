"""按 Condition、Session、Episode 生成通用连续适应计划。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from stegopot.domain.model.experiment import (
    ComponentSpec,
    EpisodeSpec,
    ExperimentPlan,
    NodeSpec,
    SessionSpec,
    validate_id,
)
from stegopot.domain.model.information import InformationAsset


class SessionScenario:
  """把声明式条件展开为彼此隔离的 Session 和有序 Episode。"""

  def __init__(self, config: Mapping[str, Any]) -> None:
    """保存已经通过严格模式校验的 config 副本。

    参数：
      config: 包含 conditions 的场景参数；每个条件声明节点、拓扑、
        Session 数量、状态持久方式和 Episode 序列。
    """
    self._config = dict(config)

  def plan(self, seed: int) -> ExperimentPlan:
    """按配置顺序确定性展开计划。

    参数：
      seed: 宿主中央种子；显式 Session 场景不随机采样，因此不使用该值。

    返回：
      含 SessionSpec 和扁平 Episode 执行顺序的 ExperimentPlan。
    """
    del seed
    sessions = []
    condition_ids = set()
    for condition in self._config["conditions"]:
      condition_id = validate_id(condition["id"])
      if condition_id in condition_ids:
        raise ValueError("core.sessions 的 condition id 不能重复")
      condition_ids.add(condition_id)
      nodes = tuple(
          NodeSpec(
              node_id=item["id"],
              role=item.get("role", item["id"]),
              policy=ComponentSpec.from_dict(item["policy"]),
              tools={
                  name: ComponentSpec.from_dict(spec)
                  for name, spec in item.get("tools", {}).items()
              },
          )
          for item in condition["nodes"]
      )
      edges = tuple(tuple(edge) for edge in condition["edges"])
      substrate = ComponentSpec.from_dict(
          condition.get("substrate", {"type": "core.communication"})
      )
      persist = condition.get("persist_policy_state", True)
      session_count = condition.get("session_count", 1)
      for session_index in range(session_count):
        session_id = validate_id(
            f"{condition_id}-session-{session_index + 1:04d}"
        )
        episodes = []
        local_episode_ids = set()
        for item in condition["episodes"]:
          local_id = validate_id(item["id"])
          if local_id in local_episode_ids:
            raise ValueError("同一 condition 的 episode id 不能重复")
          local_episode_ids.add(local_id)
          episodes.append(EpisodeSpec(
              trial_id=validate_id(f"{session_id}.{local_id}"),
              task=item["task"],
              nodes=nodes,
              edges=edges,
              substrate=substrate,
              shared_context=item.get("shared_context", {}),
              node_contexts=item.get("node_contexts", {}),
              truth=item.get("truth", {}),
              max_rounds=item.get("max_rounds", 2),
              information=tuple(
                  InformationAsset.from_dict(name, value)
                  for name, value in item.get("information", {}).items()
              ),
              channels=_components(item.get("channels")),
              detectors=_components(item.get("detectors")),
              rewards=_components(item.get("rewards")),
          ))
        sessions.append(SessionSpec(
            session_id=session_id,
            condition_id=condition_id,
            episodes=tuple(episodes),
            persist_policy_state=persist,
        ))
    return ExperimentPlan(sessions=tuple(sessions))


def _components(values):
  """转换 Episode 的可选组件覆盖；None 表示继承运行配置。"""
  if values is None:
    return None
  return tuple(ComponentSpec.from_dict(value) for value in values)
