"""场景、中央评价和逐轮奖励的公开扩展契约。"""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from stegopot.domain.model.experiment import ExperimentPlan, TrialSpec
from stegopot.domain.model.reward import RewardRequest


class ScenarioProvider(Protocol):
  """产生声明式计划，不运行模型或持有运行器。"""

  def plan(self, seed: int) -> ExperimentPlan:
    """以中央 seed 构建完整计划；种子不能自动成为节点观察。"""
    ...


class Evaluator(Protocol):
  """只在中央研究阶段读取真值的评分器。"""

  def evaluate(self, trial: TrialSpec, result: Mapping[str, Any]) -> Mapping[str, Any]:
    """用 trial 真值评价实际 result；运行失败时 result 为空，不能补写模型答案。"""
    ...

  def summarize(self, records: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
    """汇总全部 records，必须保留失败/跳过状态，不只选择成功样本。"""
    ...


class RewardFunction(Protocol):
  """根据公开投递与受限检测信号计算节点奖励，不直接修改策略。"""

  def score(self, request: RewardRequest) -> Mapping[str, float]:
    """接收不可变 request，不含未投递正文、私有最终答案或检测器诊断详情。"""
    ...
