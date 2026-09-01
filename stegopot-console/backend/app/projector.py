"""把核心研究报告转换为前端稳定读取模型。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

from app.models import ActionView
from app.models import DetectionMetricsView
from app.models import DetectionView
from app.models import EdgeView
from app.models import ExperimentView
from app.models import MessageView
from app.models import MetricsView
from app.models import NodeView
from app.models import ReportSummary
from app.models import ResearchTraceView
from app.models import ResearchView
from app.models import RoundView
from app.models import RunView
from app.models import SteganographyMetricsView
from app.models import TopologyView
from app.models import ViewScope

DETECTION_EVENT_KINDS = {
    "stego_detected",
    "stego_missed",
    "stego_false_positive",
    "stego_cleared",
    "detection_error",
}


class ProjectionError(ValueError):
  """核心报告缺少投影所需字段。"""


def project_experiment(
    document: Mapping[str, Any],
    *,
    scope: ViewScope = "public",
) -> ExperimentView:
  """将完整研究报告转换成公开或研究读取模型。

  参数：
    document: StegoPot ExperimentReport 的可序列化映射。
    scope: ``public`` 会移除秘密和逐消息真值，``research`` 额外返回真值轨迹。

  返回：
    完全由 JSON 基础类型组成的前端实验视图。
  """
  if scope not in ("public", "research"):
    raise ProjectionError(f"不支持的视图范围：{scope}")
  root = _mapping(document, "report")
  result = _mapping(root.get("result"), "result")
  scenario = _mapping(root.get("scenario"), "scenario")
  topology_data = _mapping(result.get("topology"), "result.topology")
  raw_messages = _sequence(result.get("messages"), "result.messages")
  raw_events = _sequence(
      result.get("substrate_events"),
      "result.substrate_events",
  )
  raw_rounds = _sequence(result.get("rounds"), "result.rounds")

  detections_by_message = _project_detections(raw_events)
  messages = _project_messages(raw_messages, detections_by_message)
  topology = _project_topology(topology_data, raw_rounds, messages, result)
  rounds = _project_rounds(raw_rounds)
  metrics = _project_metrics(_mapping(root.get("evaluation"), "evaluation"))
  detections = [
      detections_by_message[message.id]
      for message in messages
      if message.id in detections_by_message
  ]
  run = RunView(
      id=_required_string(root.get("run_id"), "run_id"),
      title=_required_string(scenario.get("name"), "scenario.name"),
      created_at=str(root.get("created_at") or ""),
      task=str(scenario.get("task") or result.get("task") or ""),
      seed=_integer(scenario.get("seed")),
      tags=[str(tag) for tag in _sequence_or_empty(scenario.get("tags"))],
      completed_rounds=_integer(result.get("completed_rounds"), len(rounds)),
      termination_reason=str(result.get("termination_reason") or "unknown"),
      message_count=len(messages),
      detection_count=len(detections),
  )
  research = (
      ResearchView(traces=_project_research_traces(
          messages=messages,
          rounds=raw_rounds,
          events=raw_events,
      ))
      if scope == "research"
      else None
  )
  final_answers = {
      str(node_id): str(answer)
      for node_id, answer in _mapping_or_empty(
          result.get("final_answers")
      ).items()
  }
  return ExperimentView(
      view_scope=scope,
      run=run,
      topology=topology,
      rounds=rounds,
      messages=messages,
      detections=detections,
      metrics=metrics,
      final_answers=final_answers,
      research=research,
  )


def project_summary(
    report_id: str,
    document: Mapping[str, Any],
) -> ReportSummary:
  """为报告列表生成不包含详细转录的摘要。"""
  view = project_experiment(document, scope="public")
  return ReportSummary(
      id=report_id,
      title=view.run.title,
      created_at=view.run.created_at,
      tags=view.run.tags,
      completed_rounds=view.run.completed_rounds,
      message_count=view.run.message_count,
      suspicious_count=sum(
          detection.is_suspicious is True for detection in view.detections
      ),
      f1=view.metrics.detection.f1,
      bit_recovery_accuracy=(
          view.metrics.steganography.bit_recovery_accuracy
      ),
  )


def _project_messages(
    raw_messages: Sequence[Any],
    detections: Mapping[str, DetectionView],
) -> list[MessageView]:
  """移除消息元数据，仅保留公开信道字段。"""
  messages: list[MessageView] = []
  for index, raw_value in enumerate(raw_messages):
    raw = _mapping(raw_value, f"result.messages[{index}]")
    message_id = _required_string(raw.get("message_id"), "message_id")
    messages.append(MessageView(
        id=message_id,
        round_index=_integer(raw.get("round_index")),
        sender=_required_string(raw.get("sender"), "message.sender"),
        recipient=_required_string(raw.get("recipient"), "message.recipient"),
        content=str(raw.get("content") or ""),
        detection=detections.get(message_id),
    ))
  return messages


def _project_detections(
    raw_events: Sequence[Any],
) -> dict[str, DetectionView]:
  """从中央事件提取检测器的公开判定字段。"""
  projected: dict[str, DetectionView] = {}
  for raw_value in raw_events:
    event = _mapping_or_empty(raw_value)
    kind = str(event.get("kind") or "")
    if kind not in DETECTION_EVENT_KINDS:
      continue
    metadata = _mapping_or_empty(event.get("metadata"))
    message_id = str(metadata.get("message_id") or "").strip()
    if not message_id:
      continue
    elapsed_ms = _number(metadata.get("detection_time_seconds")) * 1000.0
    if kind == "detection_error":
      projected[message_id] = DetectionView(
          message_id=message_id,
          detector_id="unavailable",
          verdict="error",
          reason=str(metadata.get("error") or "检测器执行失败"),
          elapsed_ms=elapsed_ms,
      )
      continue
    result = _mapping_or_empty(metadata.get("result"))
    suspicious = bool(result.get("is_suspicious"))
    projected[message_id] = DetectionView(
        message_id=message_id,
        detector_id=str(result.get("detector_id") or "unknown"),
        verdict="suspicious" if suspicious else "clear",
        is_suspicious=suspicious,
        score=_optional_number(result.get("score")),
        confidence=_optional_number(result.get("confidence")),
        reason=str(result.get("reason") or "未提供检测说明"),
        elapsed_ms=elapsed_ms,
    )
  return projected


def _project_topology(
    raw_topology: Mapping[str, Any],
    raw_rounds: Sequence[Any],
    messages: Sequence[MessageView],
    result: Mapping[str, Any],
) -> TopologyView:
  """结合观察中的角色信息生成拓扑读取模型。"""
  roles = _node_roles(raw_rounds)
  sent_counts: dict[str, int] = defaultdict(int)
  received_counts: dict[str, int] = defaultdict(int)
  for message in messages:
    sent_counts[message.sender] += 1
    received_counts[message.recipient] += 1
  rewards = _mapping_or_empty(result.get("rewards"))
  node_ids = [str(value) for value in _sequence_or_empty(
      raw_topology.get("nodes")
  )]
  nodes = [
      NodeView(
          id=node_id,
          label=_node_label(node_id),
          role=roles.get(node_id, "agent"),
          sent_count=sent_counts[node_id],
          received_count=received_counts[node_id],
          reward=_number(rewards.get(node_id)),
      )
      for node_id in node_ids
  ]
  edges: list[EdgeView] = []
  for index, raw_edge in enumerate(_sequence_or_empty(
      raw_topology.get("edges")
  )):
    edge = _sequence_or_empty(raw_edge)
    if len(edge) != 2:
      continue
    source, target = str(edge[0]), str(edge[1])
    edges.append(EdgeView(
        id=f"edge-{index}-{source}-{target}",
        source=source,
        target=target,
    ))
  return TopologyView(nodes=nodes, edges=edges)


def _project_rounds(raw_rounds: Sequence[Any]) -> list[RoundView]:
  """生成不包含观察和动作元数据的轮次列表。"""
  projected: list[RoundView] = []
  for index, raw_value in enumerate(raw_rounds):
    raw = _mapping(raw_value, f"result.rounds[{index}]")
    actions: list[ActionView] = []
    for step_value in _sequence_or_empty(raw.get("steps")):
      step = _mapping_or_empty(step_value)
      action = _mapping_or_empty(step.get("action"))
      actions.append(ActionView(
          node_id=str(step.get("node_id") or "unknown"),
          kind=str(action.get("kind") or "unknown"),
          target=_optional_string(action.get("target")),
          content=_optional_string(action.get("content")),
          error=_optional_string(step.get("error")),
      ))
    message_ids = [
        str(_mapping_or_empty(message).get("message_id"))
        for message in _sequence_or_empty(raw.get("delivered_messages"))
        if _mapping_or_empty(message).get("message_id")
    ]
    projected.append(RoundView(
        index=_integer(raw.get("round_index"), index),
        actions=actions,
        message_ids=message_ids,
        event_count=len(_sequence_or_empty(raw.get("substrate_events"))),
        routing_errors=[
            str(error)
            for error in _sequence_or_empty(raw.get("routing_errors"))
        ],
    ))
  return projected


def _project_metrics(evaluation: Mapping[str, Any]) -> MetricsView:
  """把内部评估字段投影为稳定且单位明确的指标。"""
  detection = _mapping_or_empty(evaluation.get("detection"))
  stego = _mapping_or_empty(evaluation.get("steganography"))
  return MetricsView(
      detection=DetectionMetricsView(
          precision=_number(detection.get("precision")),
          recall=_number(detection.get("recall")),
          f1=_number(detection.get("f1")),
          accuracy=_number(detection.get("accuracy")),
          false_positive_rate=_number(
              detection.get("false_positive_rate")
          ),
          false_negative_rate=_number(
              detection.get("false_negative_rate")
          ),
          inspected_messages=_integer(detection.get("total")),
          failed=_integer(detection.get("failed")),
          average_detection_ms=_number(
              detection.get("average_detection_time_seconds")
          ) * 1000.0,
      ),
      steganography=SteganographyMetricsView(
          embedding_coverage=_number(stego.get("embedding_coverage")),
          bit_recovery_accuracy=_number(
              stego.get("bit_recovery_accuracy")
          ),
          complete_recovery_rate=_number(
              stego.get("complete_recovery_rate")
          ),
          bits_per_token=_number(stego.get("bits_per_token")),
          encoded_messages=_integer(stego.get("encoded_calls")),
          decoded_messages=_integer(stego.get("decoded_messages")),
          requested_bit_count=_integer(stego.get("requested_bits")),
          recovered_bit_count=_integer(stego.get("matching_bits")),
          encode_time_ms=_number(
              stego.get("total_encode_time_seconds")
          ) * 1000.0,
          decode_time_ms=_number(
              stego.get("total_decode_time_seconds")
          ) * 1000.0,
      ),
  )


def _project_research_traces(
    *,
    messages: Sequence[MessageView],
    rounds: Sequence[Any],
    events: Sequence[Any],
) -> list[ResearchTraceView]:
  """在研究范围内关联秘密、解码结果和中央真实标签。"""
  embedded: dict[str, Mapping[str, Any]] = {}
  decoded: dict[str, Mapping[str, Any]] = {}
  outcomes: dict[str, str] = {}
  for event_value in events:
    event = _mapping_or_empty(event_value)
    metadata = _mapping_or_empty(event.get("metadata"))
    message_id = str(metadata.get("message_id") or "")
    if not message_id:
      continue
    if event.get("kind") == "stego_embedded":
      embedded[message_id] = metadata
    elif event.get("kind") == "stego_decoded":
      decoded[message_id] = metadata
    if metadata.get("outcome") is not None:
      outcomes[message_id] = str(metadata["outcome"])

  secret_bits: dict[str, str] = {}
  decoded_bits: dict[str, str] = {}
  messages_by_route: dict[tuple[int, str, str | None], list[str]] = defaultdict(list)
  for message in messages:
    messages_by_route[(
        message.round_index,
        message.sender,
        message.recipient,
    )].append(message.id)
  for round_value in rounds:
    round_data = _mapping_or_empty(round_value)
    round_index = _integer(round_data.get("round_index"))
    for step_value in _sequence_or_empty(round_data.get("steps")):
      step = _mapping_or_empty(step_value)
      node_id = str(step.get("node_id") or "")
      action = _mapping_or_empty(step.get("action"))
      stego = _mapping_or_empty(
          _mapping_or_empty(action.get("metadata")).get("stego")
      )
      bits = stego.get("secret_bits")
      if isinstance(bits, str):
        route = (round_index, node_id, _optional_string(action.get("target")))
        for message_id in messages_by_route.get(route, ()):
          secret_bits[message_id] = bits
      observation = _mapping_or_empty(step.get("observation"))
      environment = _mapping_or_empty(observation.get("environment"))
      stego_observation = _mapping_or_empty(environment.get("steganography"))
      for item_value in _sequence_or_empty(
          stego_observation.get("decoded_messages")
      ):
        item = _mapping_or_empty(item_value)
        item_id = str(item.get("message_id") or "")
        item_bits = item.get("bits")
        if item_id and isinstance(item_bits, str):
          decoded_bits[item_id] = item_bits

  traces: list[ResearchTraceView] = []
  for message in messages:
    embed = embedded.get(message.id, {})
    decode = decoded.get(message.id, {})
    traces.append(ResearchTraceView(
        message_id=message.id,
        is_stego=message.id in embedded,
        outcome=outcomes.get(message.id),
        algorithm=_optional_string(embed.get("algorithm")),
        secret_bits=secret_bits.get(message.id),
        decoded_bits=decoded_bits.get(message.id),
        requested_bit_count=_integer(embed.get("requested_bit_count")),
        consumed_bit_count=_integer(embed.get("consumed_bits")),
        matching_bit_count=_integer(decode.get("matching_bit_count")),
        complete_recovery=(
            bool(decode.get("complete_recovery")) if decode else None
        ),
    ))
  return traces


def _node_roles(rounds: Sequence[Any]) -> dict[str, str]:
  """从节点自己的局部观察中提取角色名称。"""
  roles: dict[str, str] = {}
  for round_value in rounds:
    for step_value in _sequence_or_empty(
        _mapping_or_empty(round_value).get("steps")
    ):
      step = _mapping_or_empty(step_value)
      identity = _mapping_or_empty(
          _mapping_or_empty(step.get("observation")).get("self")
      )
      node_id = str(identity.get("node_id") or step.get("node_id") or "")
      role = str(identity.get("role") or "")
      if node_id and role:
        roles.setdefault(node_id, role)
  return roles


def _node_label(node_id: str) -> str:
  """把机器节点 ID 转换为适合界面展示的名称。"""
  known = {
      "sender": "发送者",
      "receiver": "接收者",
      "auditor": "审计者",
  }
  return known.get(node_id, node_id.replace("_", " ").strip().title())


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
  """要求值为映射并返回。"""
  if not isinstance(value, Mapping):
    raise ProjectionError(f"{field_name} 必须是对象")
  return value


def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
  """值不是映射时返回空映射。"""
  return value if isinstance(value, Mapping) else {}


def _sequence(value: Any, field_name: str) -> Sequence[Any]:
  """要求值为非字符串序列并返回。"""
  if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
    raise ProjectionError(f"{field_name} 必须是数组")
  return value


def _sequence_or_empty(value: Any) -> Sequence[Any]:
  """值不是数组时返回空元组。"""
  if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
    return value
  return ()


def _required_string(value: Any, field_name: str) -> str:
  """要求值为非空字符串。"""
  if not isinstance(value, str) or not value.strip():
    raise ProjectionError(f"{field_name} 必须是非空字符串")
  return value.strip()


def _optional_string(value: Any) -> str | None:
  """把可选值转换成非空字符串。"""
  if value is None:
    return None
  normalized = str(value).strip()
  return normalized or None


def _number(value: Any) -> float:
  """把可选数值转换成浮点数，非法值返回零。"""
  try:
    return float(value or 0.0)
  except (TypeError, ValueError):
    return 0.0


def _optional_number(value: Any) -> float | None:
  """把可选数值转换成浮点数，非法值返回空。"""
  if value is None:
    return None
  try:
    return float(value)
  except (TypeError, ValueError):
    return None


def _integer(value: Any, default: int = 0) -> int:
  """把可选数值转换成整数，非法值返回默认值。"""
  try:
    return int(value)
  except (TypeError, ValueError):
    return default
