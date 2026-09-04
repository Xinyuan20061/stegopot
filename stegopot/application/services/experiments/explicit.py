"""内置的显式节点实验，不包含特定论文或隐写协议。"""

from collections.abc import Mapping, Sequence
from typing import Any

from stegopot.domain.model.experiment import ComponentSpec, ExperimentPlan, NodeSpec, TrialSpec


class ExplicitScenario:
  """把经过校验的节点、拓扑和私有观察配置转换为独立试验。"""

  def __init__(self, config: Mapping[str, Any]) -> None:
    """保存 config 中的任务、节点、边和可选重复次数。"""
    self._config = config

  def plan(self, seed: int) -> ExperimentPlan:
    """生成固定计划；seed 仅供扩展使用，不写入节点共享上下文。"""
    data = self._config
    nodes = [NodeSpec(item["id"], item.get("role", item["id"]),
                      ComponentSpec.from_dict(item["policy"])) for item in data["nodes"]]
    trials = [TrialSpec(
        trial_id=f"trial-{index + 1:04d}", task=data["task"], nodes=nodes, edges=data["edges"],
        substrate=ComponentSpec.from_dict(data.get("substrate", {"type": "core.communication"})),
        shared_context=data.get("shared_context", {}), node_contexts=data.get("node_contexts", {}),
        truth=data.get("truth", {}), max_rounds=data.get("max_rounds", 2),
    ) for index in range(data.get("repeat", 1))]
    return ExperimentPlan(trials, (ComponentSpec("core.metrics"),))


class BasicEvaluator:
  """提供与任务无关的运行计数；不把完成运行等同于完成实验目标。"""

  def evaluate(self, trial: TrialSpec, result: Mapping[str, Any]) -> Mapping[str, Any]:
    """统计 trial 的实际 result 中消息、轮次和最终答案数量，不推断任务成功。"""
    return {"messages": len(result.get("messages", [])),
            "rounds": result.get("completed_rounds", 0),
            "final_answers": len(result.get("final_answers", {}))}

  def summarize(self, records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """汇总全部 records，分别保留完成、失败和跳过数量。"""
    return {"planned": len(records),
            **{status: sum(record["status"] == status for record in records)
               for status in ("completed", "failed", "skipped")}}
