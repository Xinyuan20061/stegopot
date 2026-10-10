"""通用机制实验上下文与结果。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass
class ExperimentContext:
  """一次实验显式共享的运行能力，替代全局变量。"""

  run_id: str = field(metadata=_description("宿主创建的运行 ID。"))
  seed: int = field(metadata=_description("实验级随机种子。"))
  config: Mapping[str, Any] = field(metadata=_description("已校验且只读的实验配置。"))
  runtime: Any = field(repr=False, metadata=_description("实现 ModelRuntime 契约的实例。"))
  artifact_store: Any = field(repr=False, metadata=_description("实现 ArtifactStore 契约的实例。"))
  event_bus: Any = field(repr=False, metadata=_description("实现 EventBus 契约的实例。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("插件版本、数据版本和设备等复现元数据。"))

  def __post_init__(self) -> None:
    if not self.run_id:
      raise ValueError("run_id 不能为空")
    self.config = MappingProxyType(dict(self.config))
    self.metadata = MappingProxyType(dict(self.metadata))


@dataclass(frozen=True)
class SampleRunRecord:
  """Scenario 对一个通用 Sample 的执行记录。"""

  sample_id: str = field(metadata=_description("来源 Sample ID。"))
  output: Any = field(repr=False, metadata=_description("Scenario 的输出对象。"))
  analyses: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("Analyzer ID 到结果的映射。"))
  metrics: Mapping[str, float] = field(
      default_factory=dict, metadata=_description("Metric ID 到有限数值的映射。"))
  metadata: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("耗时和后端等非敏感执行信息。"))

  def __post_init__(self) -> None:
    if not self.sample_id:
      raise ValueError("sample_id 不能为空")
    object.__setattr__(self, "analyses", MappingProxyType(dict(self.analyses)))
    object.__setattr__(self, "metrics", MappingProxyType({
        str(key): float(value) for key, value in self.metrics.items()}))
    object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class ResearchExperimentResult:
  """通用 Experiment Engine 的最终结果。"""

  run_id: str = field(metadata=_description("实验运行 ID。"))
  status: str = field(metadata=_description("completed、failed 或 cancelled。"))
  records: Sequence[SampleRunRecord] = field(metadata=_description("逐样本执行记录。"))
  summary: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("跨样本指标与 Reporter 摘要。"))
  artifacts: Mapping[str, Any] = field(
      default_factory=dict, metadata=_description("输出工件逻辑名到引用的映射。"))

  def __post_init__(self) -> None:
    if self.status not in {"completed", "failed", "cancelled"}:
      raise ValueError("status 不受支持")
    object.__setattr__(self, "records", tuple(self.records))
    object.__setattr__(self, "summary", MappingProxyType(dict(self.summary)))
    object.__setattr__(self, "artifacts", MappingProxyType(dict(self.artifacts)))
