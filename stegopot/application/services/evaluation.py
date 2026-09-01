"""运行多智能体实验并计算检测与隐写指标。"""

from __future__ import annotations

from collections.abc import Mapping
import dataclasses
from typing import Any

from stegopot.application.engine import MultiAgentRuntime
from stegopot.application.engine import RunResult
from stegopot.domain.model import DetectionMetrics


@dataclasses.dataclass(frozen=True)
class StegoMetrics:
  """根据隐写环境事件汇总的传输指标。

  属性：
    encoded_calls: 实际执行隐写编码的次数。
    delivered_stego_messages: 投递的隐写点对点消息数量。
    decoded_messages: 授权节点执行解码的消息数量。
    requested_bits: 编码调用请求嵌入的秘密比特总数。
    consumed_bits: 编码调用实际消费的秘密比特总数。
    expected_decoded_bits: 解码事件期望恢复的比特总数。
    decoded_bits: 解码器返回的比特总数。
    matching_bits: 与期望秘密前缀一致的比特总数。
    complete_recoveries: 完整恢复期望比特的解码消息数量。
    generated_tokens: 隐写编码生成的 token 总数。
    total_encode_time_seconds: 编码累计耗时。
    total_decode_time_seconds: 解码累计耗时。
  """

  encoded_calls: int = 0
  delivered_stego_messages: int = 0
  decoded_messages: int = 0
  requested_bits: int = 0
  consumed_bits: int = 0
  expected_decoded_bits: int = 0
  decoded_bits: int = 0
  matching_bits: int = 0
  complete_recoveries: int = 0
  generated_tokens: int = 0
  total_encode_time_seconds: float = 0.0
  total_decode_time_seconds: float = 0.0

  @property
  def embedding_coverage(self) -> float:
    """返回请求比特中实际被编码器消费的比例。"""
    return _safe_divide(self.consumed_bits, self.requested_bits)

  @property
  def bit_recovery_accuracy(self) -> float:
    """返回授权解码结果中逐比特匹配的比例。"""
    return _safe_divide(self.matching_bits, self.expected_decoded_bits)

  @property
  def complete_recovery_rate(self) -> float:
    """返回完成全部期望比特恢复的解码消息比例。"""
    return _safe_divide(self.complete_recoveries, self.decoded_messages)

  @property
  def bits_per_token(self) -> float:
    """返回每个生成 token 实际承载的秘密比特数。"""
    return _safe_divide(self.consumed_bits, self.generated_tokens)

  def to_dict(self) -> dict[str, Any]:
    """返回包含原始计数和派生指标的可序列化字典。"""
    return {
        **dataclasses.asdict(self),
        "embedding_coverage": self.embedding_coverage,
        "bit_recovery_accuracy": self.bit_recovery_accuracy,
        "complete_recovery_rate": self.complete_recovery_rate,
        "bits_per_token": self.bits_per_token,
    }


@dataclasses.dataclass(frozen=True)
class EvaluationSummary:
  """一次运行的检测指标和隐写传输指标。

  属性：
    detection: 根据中央真实标签计算的二分类检测指标。
    steganography: 根据隐写编码和解码事件计算的传输指标。
  """

  detection: DetectionMetrics
  steganography: StegoMetrics

  def to_dict(self) -> dict[str, Any]:
    """返回适合 JSON 序列化的评估摘要。"""
    return {
        "detection": self.detection.to_dict(),
        "steganography": self.steganography.to_dict(),
    }


def run_episode(
    runtime: MultiAgentRuntime,
    *,
    task: str,
    shared_context: Mapping[str, Any] | None = None,
) -> RunResult:
  """运行一次完整实验并返回统一运行结果。

  参数：
    runtime: 已完成节点、拓扑、Substrate 和终止条件装配的运行器。
    task: 全部节点共同接收的实验任务文本。
    shared_context: 对全部节点可见的结构化背景信息。

  返回：
    包含轮次、消息、奖励、环境事件和最终状态的运行结果。
  """
  return runtime.run(task, shared_context=shared_context)


def evaluate_run(result: RunResult) -> EvaluationSummary:
  """根据中央环境事件计算一次运行的统一评估摘要。

  参数：
    result: MultiAgentRuntime 返回的完整运行结果。

  返回：
    包含检测二分类指标和隐写传输指标的摘要。
  """
  return EvaluationSummary(
      detection=_calculate_detection_metrics(result),
      steganography=_calculate_stego_metrics(result),
  )


def _calculate_detection_metrics(result: RunResult) -> DetectionMetrics:
  """从检测事件累计 TP、TN、FP、FN、失败数和耗时。"""
  counts = {
      "true_positive": 0,
      "true_negative": 0,
      "false_positive": 0,
      "false_negative": 0,
  }
  failed = 0
  total_time = 0.0
  for event in result.substrate_events:
    if event.kind == "detection_error":
      failed += 1
      total_time += float(
          event.metadata.get("detection_time_seconds") or 0.0
      )
      continue
    outcome = event.metadata.get("outcome")
    if outcome not in counts:
      continue
    counts[str(outcome)] += 1
    total_time += float(
        event.metadata.get("detection_time_seconds") or 0.0
    )
  return DetectionMetrics(
      **counts,
      failed=failed,
      total_detection_time_seconds=total_time,
  )


def _calculate_stego_metrics(result: RunResult) -> StegoMetrics:
  """从隐写编码和解码事件累计容量与恢复指标。"""
  embedded_events: dict[tuple[int, str | None], Any] = {}
  delivered_stego_messages = 0
  decoded_events = []
  for event in result.substrate_events:
    if event.kind == "stego_embedded":
      delivered_stego_messages += 1
      embedded_events.setdefault(
          (event.round_index, event.actor),
          event,
      )
    elif event.kind == "stego_decoded":
      decoded_events.append(event)

  requested_bits = sum(
      int(event.metadata.get("requested_bit_count") or 0)
      for event in embedded_events.values()
  )
  consumed_bits = sum(
      int(event.metadata.get("consumed_bits") or 0)
      for event in embedded_events.values()
  )
  generated_tokens = sum(
      len(event.metadata.get("generated_token_ids") or ())
      for event in embedded_events.values()
  )
  expected_decoded_bits = sum(
      int(event.metadata.get("expected_bit_count") or 0)
      for event in decoded_events
  )
  decoded_bits = sum(
      int(event.metadata.get("decoded_bit_count") or 0)
      for event in decoded_events
  )
  matching_bits = sum(
      int(event.metadata.get("matching_bit_count") or 0)
      for event in decoded_events
  )
  complete_recoveries = sum(
      bool(event.metadata.get("complete_recovery"))
      for event in decoded_events
  )
  return StegoMetrics(
      encoded_calls=len(embedded_events),
      delivered_stego_messages=delivered_stego_messages,
      decoded_messages=len(decoded_events),
      requested_bits=requested_bits,
      consumed_bits=consumed_bits,
      expected_decoded_bits=expected_decoded_bits,
      decoded_bits=decoded_bits,
      matching_bits=matching_bits,
      complete_recoveries=complete_recoveries,
      generated_tokens=generated_tokens,
      total_encode_time_seconds=sum(
          float(event.metadata.get("encode_time_seconds") or 0.0)
          for event in embedded_events.values()
      ),
      total_decode_time_seconds=sum(
          float(event.metadata.get("decode_time_seconds") or 0.0)
          for event in decoded_events
      ),
  )


def _safe_divide(numerator: float, denominator: float) -> float:
  """执行零分母返回 0 的浮点除法。"""
  if denominator == 0:
    return 0.0
  return float(numerator) / float(denominator)
