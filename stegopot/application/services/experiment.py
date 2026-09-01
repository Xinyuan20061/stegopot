"""可复现检测实验的场景配置、运行入口和统一报告。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import dataclasses
from datetime import datetime, timezone
import random
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from stegopot.application.engine import MultiAgentRuntime
from stegopot.application.engine import RunResult
from stegopot.application.services.evaluation import EvaluationSummary
from stegopot.application.services.evaluation import evaluate_run


@dataclasses.dataclass(frozen=True)
class ExperimentScenario:
  """一次可复现检测实验的工具无关配置。

  属性：
    name: 场景名称，用于报告和文件命名。
    task: 交给全部智能体节点的全局任务文本。
    seed: 本次运行使用并写入共享上下文的随机种子。
    shared_context: 对全部节点和检测器公开的结构化实验背景。
    tags: 用于筛选和分组实验的标签。
  """

  name: str
  task: str
  seed: int = 0
  shared_context: Mapping[str, Any] = dataclasses.field(default_factory=dict)
  tags: tuple[str, ...] = ()

  def __post_init__(self) -> None:
    for field_name in ("name", "task"):
      value = getattr(self, field_name)
      if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ExperimentScenario.{field_name} 必须是非空字符串")
      object.__setattr__(self, field_name, value.strip())
    object.__setattr__(self, "seed", int(self.seed))
    object.__setattr__(
        self,
        "shared_context",
        MappingProxyType(dict(self.shared_context)),
    )
    normalized_tags = tuple(
        tag.strip()
        for tag in self.tags
        if isinstance(tag, str) and tag.strip()
    )
    object.__setattr__(self, "tags", normalized_tags)

  def to_dict(self) -> dict[str, Any]:
    """返回适合记录和 JSON 序列化的场景配置。"""
    return {
        "name": self.name,
        "task": self.task,
        "seed": self.seed,
        "shared_context": dict(self.shared_context),
        "tags": list(self.tags),
    }


@dataclasses.dataclass(frozen=True)
class ExperimentReport:
  """一次实验的场景、运行结果和评估指标。

  属性：
    run_id: 当前实验运行的唯一 ID。
    created_at: 报告创建时的 UTC ISO 8601 时间。
    scenario: 本次运行使用的场景配置。
    result: MultiAgentRuntime 返回的完整运行结果。
    evaluation: 根据中央事件计算出的评估摘要。
  """

  run_id: str
  created_at: str
  scenario: ExperimentScenario
  result: RunResult
  evaluation: EvaluationSummary

  def to_dict(self) -> dict[str, Any]:
    """返回包含完整转录和指标的可序列化报告字典。"""
    return {
        "run_id": self.run_id,
        "created_at": self.created_at,
        "scenario": self.scenario.to_dict(),
        "result": self.result.to_dict(),
        "evaluation": self.evaluation.to_dict(),
    }


def run_experiment(
    runtime: MultiAgentRuntime,
    *,
    scenario: ExperimentScenario,
    run_id: str | None = None,
    recorder: Callable[[Mapping[str, Any]], Any] | None = None,
) -> ExperimentReport:
  """运行一次场景、计算评估指标并可选持久化报告。

  参数：
    runtime: 已装配节点、拓扑、隐写环境和检测环境的运行器。
    scenario: 本次实验使用的任务、种子、上下文和标签。
    run_id: 调用方指定的运行 ID；为空时自动生成 UUID。
    recorder: 可选报告写入函数，接收 report.to_dict() 的结果。

  返回：
    包含完整运行结果和统一评估指标的 ExperimentReport。
  """
  actual_run_id = run_id or uuid4().hex
  if not isinstance(actual_run_id, str) or not actual_run_id.strip():
    raise ValueError("run_id 必须是非空字符串")
  actual_run_id = actual_run_id.strip()
  shared_context = {
      **scenario.shared_context,
      "experiment": {
          "run_id": actual_run_id,
          "scenario": scenario.name,
          "seed": scenario.seed,
          "tags": list(scenario.tags),
      },
  }
  previous_random_state = random.getstate()
  random.seed(scenario.seed)
  try:
    result = runtime.run(
        scenario.task,
        shared_context=shared_context,
    )
  finally:
    random.setstate(previous_random_state)
  report = ExperimentReport(
      run_id=actual_run_id,
      created_at=datetime.now(timezone.utc).isoformat(),
      scenario=scenario,
      result=result,
      evaluation=evaluate_run(result),
  )
  if recorder is not None:
    recorder(report.to_dict())
  return report
