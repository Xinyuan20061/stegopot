"""前后端共享的稳定只读数据模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ViewScope = Literal["public", "research"]


class ContractModel(BaseModel):
  """禁止额外字段的契约模型基类。"""

  model_config = ConfigDict(extra="forbid")


class RunView(ContractModel):
  """一次实验运行的基础信息。"""

  id: str
  title: str
  created_at: str
  task: str
  status: Literal["completed"] = "completed"
  seed: int
  tags: list[str] = Field(default_factory=list)
  completed_rounds: int
  termination_reason: str
  message_count: int
  detection_count: int


class NodeView(ContractModel):
  """拓扑中的可视化节点。"""

  id: str
  label: str
  role: str
  sent_count: int = 0
  received_count: int = 0
  reward: float = 0.0


class EdgeView(ContractModel):
  """拓扑中的有向通信边。"""

  id: str
  source: str
  target: str


class TopologyView(ContractModel):
  """由节点和有向边组成的拓扑快照。"""

  nodes: list[NodeView]
  edges: list[EdgeView]


class ActionView(ContractModel):
  """已移除私密元数据的节点动作。"""

  node_id: str
  kind: str
  target: str | None = None
  content: str | None = None
  error: str | None = None


class RoundView(ContractModel):
  """单个同步轮次的公开摘要。"""

  index: int
  actions: list[ActionView]
  message_ids: list[str]
  event_count: int
  routing_errors: list[str] = Field(default_factory=list)


class DetectionView(ContractModel):
  """针对一条公开消息的检测结论。"""

  message_id: str
  detector_id: str
  verdict: Literal["suspicious", "clear", "error"]
  is_suspicious: bool | None = None
  score: float | None = None
  confidence: float | None = None
  reason: str
  elapsed_ms: float


class MessageView(ContractModel):
  """前端能够展示的一条公开消息。"""

  id: str
  round_index: int
  sender: str
  recipient: str
  content: str
  detection: DetectionView | None = None


class DetectionMetricsView(ContractModel):
  """检测任务的核心评估指标。"""

  precision: float
  recall: float
  f1: float
  accuracy: float
  false_positive_rate: float
  false_negative_rate: float
  inspected_messages: int
  failed: int
  average_detection_ms: float


class SteganographyMetricsView(ContractModel):
  """隐写传输的核心评估指标。"""

  embedding_coverage: float
  bit_recovery_accuracy: float
  complete_recovery_rate: float
  bits_per_token: float
  encoded_messages: int
  decoded_messages: int
  requested_bit_count: int
  recovered_bit_count: int
  encode_time_ms: float
  decode_time_ms: float


class MetricsView(ContractModel):
  """检测与隐写指标集合。"""

  detection: DetectionMetricsView
  steganography: SteganographyMetricsView


class ResearchTraceView(ContractModel):
  """仅研究视图返回的单条消息真实轨迹。"""

  message_id: str
  is_stego: bool
  outcome: str | None = None
  algorithm: str | None = None
  secret_bits: str | None = None
  decoded_bits: str | None = None
  requested_bit_count: int = 0
  consumed_bit_count: int = 0
  matching_bit_count: int = 0
  complete_recovery: bool | None = None


class ResearchView(ContractModel):
  """与公开视图物理分离的研究真值集合。"""

  traces: list[ResearchTraceView]


class ExperimentView(ContractModel):
  """前端使用的完整实验读取模型。"""

  schema_version: Literal["1.0"] = "1.0"
  view_scope: ViewScope
  run: RunView
  topology: TopologyView
  rounds: list[RoundView]
  messages: list[MessageView]
  detections: list[DetectionView]
  metrics: MetricsView
  final_answers: dict[str, str]
  research: ResearchView | None = None


class ReportSummary(ContractModel):
  """报告列表中的轻量摘要。"""

  id: str
  title: str
  created_at: str
  tags: list[str]
  completed_rounds: int
  message_count: int
  suspicious_count: int
  f1: float
  bit_recovery_accuracy: float


class ReportListResponse(ContractModel):
  """报告列表响应。"""

  reports: list[ReportSummary]
  total: int


class HealthResponse(ContractModel):
  """后端健康状态。"""

  status: Literal["ok"] = "ok"
  contract_version: Literal["1.0"] = "1.0"
  report_count: int


class ImportResponse(ContractModel):
  """导入实验报告后的响应。"""

  id: str
  imported: bool = True
