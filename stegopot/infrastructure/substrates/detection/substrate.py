"""以装饰器方式为任意 Substrate 增加公开消息隐写检测。"""

from __future__ import annotations

from collections.abc import Collection, Mapping
import dataclasses
import time
from typing import Any

from stegopot.domain.interface import StegoDetector
from stegopot.domain.interface import Substrate
from stegopot.domain.interface import SubstrateEvent
from stegopot.domain.interface import SubstrateResetContext
from stegopot.domain.interface import SubstrateStepContext
from stegopot.domain.interface import SubstrateStepResult
from stegopot.domain.model import DetectionFinding
from stegopot.domain.model import DetectionRequest
from stegopot.domain.model import DetectionResult


class DetectionSubstrateError(RuntimeError):
  """检测器返回非法结果或执行失败时抛出的异常。"""


class DetectionSubstrate(Substrate):
  """包装内部环境，并检测其实际投递的公开消息。

  内部 Substrate 先完成隐写编码、元数据过滤和消息变换，本类随后只把
  变换后的公开消息交给检测器。实验真实标签从内部环境事件提取，只写入
  中央 RunResult 事件，不会放入审计节点观察。
  """

  _OUTCOME_EVENT_KINDS = {
      (True, True): "stego_detected",
      (True, False): "stego_missed",
      (False, True): "stego_false_positive",
      (False, False): "stego_cleared",
  }

  def __init__(
      self,
      *,
      inner: Substrate,
      detector: StegoDetector,
      auditor_nodes: Collection[str] = (),
      fail_fast: bool = True,
      private_metadata_keys: Collection[str] = ("stego",),
  ) -> None:
    """初始化检测环境装饰器。

    参数：
      inner: 负责实际消息变换、投递和奖励计算的内部环境。
      detector: 只读取公开消息并返回风险判定的检测器。
      auditor_nodes: 被授权在局部环境观察中读取检测发现的节点 ID。
      fail_fast: 检测器失败时是否立即终止；为 False 时记录错误并继续投递。
      private_metadata_keys: 无论内部环境是否过滤，都不会交给检测器的元数据键。
    """
    if inner is None:
      raise ValueError("DetectionSubstrate.inner 不能为空")
    if not callable(getattr(detector, "detect", None)):
      raise TypeError("detector 必须实现 detect(request)")
    normalized_private_keys = {
        str(key).strip() for key in private_metadata_keys if str(key).strip()
    }
    self._inner = inner
    self._detector = detector
    self._auditor_nodes = frozenset(auditor_nodes)
    self._fail_fast = bool(fail_fast)
    self._private_metadata_keys = frozenset(normalized_private_keys)
    self._reset_context: SubstrateResetContext | None = None
    self._findings_by_auditor: dict[str, list[DetectionFinding]] = {}
    self._outcome_counts = self._empty_outcome_counts()
    self._failed_count = 0
    self._total_detection_time_seconds = 0.0

  def reset(self, context: SubstrateResetContext) -> None:
    """重置内部环境、检测器和审计发现。

    参数：
      context: 全局任务、节点、共享上下文和拓扑快照。
    """
    unknown_auditors = self._auditor_nodes - set(context.node_ids)
    if unknown_auditors:
      raise ValueError(
          f"auditor_nodes 包含未知节点：{sorted(unknown_auditors)}"
      )
    self._inner.reset(context)
    self._detector.reset()
    self._reset_context = context
    self._findings_by_auditor = {
        node_id: [] for node_id in self._auditor_nodes
    }
    self._outcome_counts = self._empty_outcome_counts()
    self._failed_count = 0
    self._total_detection_time_seconds = 0.0

  def observe(self, node_id: str) -> Mapping[str, Any]:
    """返回内部环境观察和当前节点可见的检测发现。

    参数：
      node_id: 请求观察的节点 ID。

    返回：
      非审计节点只看到自身不是审计者；审计节点额外看到公开检测发现。
    """
    observation = dict(self._inner.observe(node_id))
    is_auditor = node_id in self._auditor_nodes
    observation["detection"] = {
        "is_auditor": is_auditor,
        "findings": [
            finding.to_dict()
            for finding in self._findings_by_auditor.get(node_id, ())
        ],
    }
    return observation

  def step(self, context: SubstrateStepContext) -> SubstrateStepResult:
    """推进内部环境并检测本轮实际投递的公开消息。

    参数：
      context: 当前轮次、节点动作和拓扑路由后的候选消息。

    返回：
      保留内部环境结果，并追加检测事件和统计信息。
    """
    if self._reset_context is None:
      raise RuntimeError("DetectionSubstrate.step 必须在 reset 之后调用")
    inner_result = self._inner.step(context)
    stego_message_ids = self._stego_message_ids(inner_result.events)
    detection_events: list[SubstrateEvent] = []

    for message in inner_result.messages:
      request = DetectionRequest(
          message_id=message.message_id,
          sender=message.sender,
          recipient=message.recipient,
          content=message.content,
          round_index=message.round_index,
          metadata={
              key: value
              for key, value in message.metadata.items()
              if key not in self._private_metadata_keys
          },
          context=self._public_context(),
      )
      started_at = time.perf_counter()
      try:
        result = self._detector.detect(request)
        elapsed = time.perf_counter() - started_at
        self._validate_result(request, result)
      except Exception as exc:  # pylint: disable=broad-exception-caught
        elapsed = time.perf_counter() - started_at
        self._failed_count += 1
        self._total_detection_time_seconds += elapsed
        if self._fail_fast:
          raise DetectionSubstrateError(
              f"消息 {message.message_id} 检测失败：{exc}"
          ) from exc
        detection_events.append(SubstrateEvent(
            kind="detection_error",
            round_index=context.round_index,
            actor=None,
            target=message.recipient,
            metadata={
                "message_id": message.message_id,
                "sender": message.sender,
                "error_type": type(exc).__name__,
                "error": str(exc),
                "detection_time_seconds": elapsed,
            },
        ))
        continue

      self._total_detection_time_seconds += elapsed
      finding = DetectionFinding(request=request, result=result)
      for auditor_id in self._auditor_nodes:
        self._findings_by_auditor[auditor_id].append(finding)

      ground_truth = message.message_id in stego_message_ids
      outcome = self._outcome_name(
          ground_truth=ground_truth,
          predicted=result.is_suspicious,
      )
      self._outcome_counts[outcome] += 1
      detection_events.append(SubstrateEvent(
          kind=self._OUTCOME_EVENT_KINDS[
              (ground_truth, result.is_suspicious)
          ],
          round_index=context.round_index,
          actor=None,
          target=message.recipient,
          metadata={
              "message_id": message.message_id,
              "sender": message.sender,
              "ground_truth": ground_truth,
              "outcome": outcome,
              "detection_time_seconds": elapsed,
              "result": result.to_dict(),
          },
      ))

    return SubstrateStepResult(
        messages=inner_result.messages,
        rewards=inner_result.rewards,
        events=tuple(inner_result.events) + tuple(detection_events),
        done=inner_result.done,
        termination_reason=inner_result.termination_reason,
        info={
            **inner_result.info,
            "detection": self._detection_state(),
        },
    )

  def state(self) -> Mapping[str, Any]:
    """返回内部环境状态和不包含真实消息内容的检测统计。"""
    return {
        **self._inner.state(),
        "detection": {
            **self._detection_state(),
            "auditor_nodes": sorted(self._auditor_nodes),
        },
    }

  def close(self) -> None:
    """释放检测器和内部环境持有的资源。"""
    try:
      self._detector.close()
    finally:
      self._inner.close()

  def _public_context(self) -> Mapping[str, Any]:
    """返回检测器可读取的公开实验上下文。"""
    if self._reset_context is None:
      return {}
    return {
        "task": self._reset_context.task,
        "node_ids": list(self._reset_context.node_ids),
        "shared_context": dict(self._reset_context.shared_context),
        "topology": dict(self._reset_context.topology),
    }

  @staticmethod
  def _stego_message_ids(events: Collection[SubstrateEvent]) -> set[str]:
    """从内部环境事件提取本轮隐写消息真实标签。"""
    return {
        str(event.metadata["message_id"])
        for event in events
        if event.kind == "stego_embedded" and "message_id" in event.metadata
    }

  @staticmethod
  def _validate_result(
      request: DetectionRequest,
      result: DetectionResult,
  ) -> None:
    """验证检测器返回类型及消息关联。"""
    if not isinstance(result, DetectionResult):
      raise TypeError("detector.detect 必须返回 DetectionResult")
    if result.message_id != request.message_id:
      raise ValueError(
          "检测结果 message_id 与请求不一致："
          f"{result.message_id} != {request.message_id}"
      )

  @staticmethod
  def _outcome_name(*, ground_truth: bool, predicted: bool) -> str:
    """把真实标签和检测判定转换成标准二分类结果名称。"""
    if ground_truth and predicted:
      return "true_positive"
    if ground_truth:
      return "false_negative"
    if predicted:
      return "false_positive"
    return "true_negative"

  @staticmethod
  def _empty_outcome_counts() -> dict[str, int]:
    """创建一组全零二分类结果计数。"""
    return {
        "true_positive": 0,
        "true_negative": 0,
        "false_positive": 0,
        "false_negative": 0,
    }

  def _detection_state(self) -> dict[str, Any]:
    """返回当前检测计数和累计耗时。"""
    return {
        **self._outcome_counts,
        "failed": self._failed_count,
        "inspected_message_count": (
            sum(self._outcome_counts.values()) + self._failed_count
        ),
        "total_detection_time_seconds": (
            self._total_detection_time_seconds
        ),
    }
