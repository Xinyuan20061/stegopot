"""通用 Scenario、Analyzer、Metric 与 Reporter 协议。"""

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from stegopot.domain.model.context import (
    ExperimentContext,
    ResearchExperimentResult,
    SampleRunRecord,
)
from stegopot.domain.model.data import Sample


class ResearchScenario(Protocol):
  """定义一个样本如何在实验上下文中发生。"""

  def setup(self, context: ExperimentContext) -> None:
    """在数据执行前准备场景状态。"""
    ...
  def run(self, sample: Sample, context: ExperimentContext) -> Any:
    """执行一个样本并返回不受 Core 解释的输出。"""
    ...

  def teardown(self, context: ExperimentContext) -> None:
    """无论成功失败都释放场景状态。"""
    ...


class Analyzer(Protocol):
  """对 Scenario 输出执行任意外部研究算法。"""

  @property
  def analyzer_id(self) -> str:
    """返回分析器 ID。"""
    ...

  def analyze(self, sample: Sample, output: Any, context: ExperimentContext) -> Any:
    """返回分析结果；Core 不解释其算法语义。"""
    ...


class Metric(Protocol):
  """把样本、输出和分析结果映射为有限标量。"""

  @property
  def metric_id(self) -> str:
    """返回指标 ID。"""
    ...

  def evaluate(
      self, sample: Sample, output: Any, analyses: Mapping[str, Any],
      context: ExperimentContext,
  ) -> float:
    """返回一个有限指标值。"""
    ...


class Reporter(Protocol):
  """只消费通用记录并产生摘要或外部报告。"""

  @property
  def reporter_id(self) -> str:
    """返回 Reporter ID。"""
    ...

  def summarize(
      self, records: Sequence[SampleRunRecord], context: ExperimentContext,
  ) -> Mapping[str, Any]:
    """生成跨样本摘要。"""
    ...

  def report(self, result: ResearchExperimentResult, context: ExperimentContext) -> None:
    """保存或发送最终报告；不得修改已有记录。"""
    ...
