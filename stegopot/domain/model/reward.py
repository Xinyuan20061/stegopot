"""逐轮奖励计算使用的公开证据模型。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
import dataclasses
import math
from types import MappingProxyType
from typing import Any

from stegopot.domain.model.message import AgentMessage
from stegopot.domain.model.experiment import json_copy, validate_id


@dataclasses.dataclass(frozen=True)
class RewardAction:
  """一个节点动作中允许奖励组件读取的字段。

  属性：
    kind: 动作类型，例如 message、wait 或 final_answer。
    target: 动作声明的目标；广播或无目标动作时为空。

  正文、动作元数据和节点内部状态不会进入该对象。
  """

  kind: str
  target: str | None = None

  def __post_init__(self) -> None:
    if not isinstance(self.kind, str) or not self.kind.strip():
      raise ValueError("RewardAction.kind 必须是非空字符串")
    if self.target is not None and (
        not isinstance(self.target, str) or not self.target.strip()
    ):
      raise ValueError("RewardAction.target 必须为空或非空字符串")
    object.__setattr__(self, "kind", self.kind.strip())
    if self.target is not None:
      object.__setattr__(self, "target", self.target.strip())

  def to_dict(self) -> dict[str, str | None]:
    """返回不包含正文和元数据的动作摘要。"""
    return {"kind": self.kind, "target": self.target}


@dataclasses.dataclass(frozen=True)
class RewardDetectionSignal:
  """奖励组件可读取的一条受限检测信号。

  属性：
    component_id: 配置中执行本次检测的组件 ID。
    message_id: 对应实际投递消息的 ID。
    detector_id: 检测实现报告的稳定标识。
    is_suspicious: 检测器是否判定该消息可疑。
    score: 位于 0 到 1 的风险分数。
    confidence: 可选置信度，位于 0 到 1。

  检测理由、任意元数据、检测请求上下文和中央真值不会进入该对象。
  """

  component_id: str
  message_id: str
  detector_id: str
  is_suspicious: bool
  score: float
  confidence: float | None = None

  def __post_init__(self) -> None:
    for field_name in ("component_id", "message_id", "detector_id"):
      value = getattr(self, field_name)
      if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"RewardDetectionSignal.{field_name} 必须是非空字符串"
        )
      object.__setattr__(self, field_name, value.strip())
    if not isinstance(self.is_suspicious, bool):
      raise TypeError("RewardDetectionSignal.is_suspicious 必须是 bool")
    score = float(self.score)
    if not math.isfinite(score) or not 0.0 <= score <= 1.0:
      raise ValueError("RewardDetectionSignal.score 必须位于 [0, 1] 区间")
    object.__setattr__(self, "score", score)
    if self.confidence is not None:
      confidence = float(self.confidence)
      if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise ValueError(
            "RewardDetectionSignal.confidence 必须位于 [0, 1] 区间"
        )
      object.__setattr__(self, "confidence", confidence)

  def to_dict(self) -> dict[str, Any]:
    """返回不包含检测器理由、元数据和上下文的信号字典。"""
    return {
        "component_id": self.component_id,
        "message_id": self.message_id,
        "detector_id": self.detector_id,
        "is_suspicious": self.is_suspicious,
        "score": self.score,
        "confidence": self.confidence,
    }


@dataclasses.dataclass(frozen=True)
class RewardRequest(Mapping[str, Any]):
  """宿主交给逐轮奖励组件的不可变公开证据。

  属性：
    round_index: 当前同步轮次，从 0 开始。
    actions: 节点 ID 到受限动作摘要的映射。
    messages: 经过环境和信道处理后实际投递的公开消息。
    detections: Detector 对实际投递消息给出的受限风险信号。

  本对象实现 Mapping，以兼容插件 API 1.1 中使用
  ``request["messages"]`` 的奖励实现；新代码应优先使用类型化属性。
  """

  round_index: int
  actions: Mapping[str, RewardAction]
  messages: Sequence[AgentMessage]
  detections: Sequence[RewardDetectionSignal] = ()

  _KEYS = ("round_index", "actions", "messages", "detections")

  def __post_init__(self) -> None:
    if type(self.round_index) is not int or self.round_index < 0:
      raise ValueError("RewardRequest.round_index 必须是非负整数")
    actions = dict(self.actions)
    if any(
        not isinstance(node_id, str) or not node_id.strip()
        for node_id in actions
    ):
      raise ValueError("RewardRequest.actions 的节点 ID 必须是非空字符串")
    if any(not isinstance(action, RewardAction) for action in actions.values()):
      raise TypeError("RewardRequest.actions 的值必须是 RewardAction")
    messages = tuple(self.messages)
    if any(not isinstance(message, AgentMessage) for message in messages):
      raise TypeError("RewardRequest.messages 的元素必须是 AgentMessage")
    if any(message.round_index != self.round_index for message in messages):
      raise ValueError("RewardRequest.messages 必须属于当前轮次")
    detections = tuple(self.detections)
    if any(
        not isinstance(signal, RewardDetectionSignal)
        for signal in detections
    ):
      raise TypeError(
          "RewardRequest.detections 的元素必须是 RewardDetectionSignal"
      )
    message_ids = {message.message_id for message in messages}
    if any(signal.message_id not in message_ids for signal in detections):
      raise ValueError("RewardRequest.detections 引用了未投递消息")
    object.__setattr__(self, "actions", MappingProxyType(actions))
    object.__setattr__(self, "messages", messages)
    object.__setattr__(self, "detections", detections)

  def to_dict(self) -> dict[str, Any]:
    """返回兼容旧奖励插件并适合研究审计的公开证据字典。"""
    return {
        "round_index": self.round_index,
        "actions": {
            node_id: action.to_dict()
            for node_id, action in self.actions.items()
        },
        "messages": [message.to_dict() for message in self.messages],
        "detections": [signal.to_dict() for signal in self.detections],
    }

  def __getitem__(self, key: str) -> Any:
    """按 API 1.1 的映射约定返回 key 对应的 JSON 数据副本。"""
    if key not in self._KEYS:
      raise KeyError(key)
    return self.to_dict()[key]

  def __iter__(self) -> Iterator[str]:
    """按稳定顺序迭代兼容映射键。"""
    return iter(self._KEYS)

  def __len__(self) -> int:
    """返回兼容映射键的数量。"""
    return len(self._KEYS)


class EpisodeOutcomeRequest:
  """Episode 结束后交给中央结果奖励器的只读请求。

  ``result`` 与 ``truth`` 每次访问都会返回独立 JSON 副本。该请求只交给
  受信任的 outcome_reward 组件，不进入 Policy、Detector 或公开审计。
  """

  __slots__ = (
      "_condition_id",
      "_session_id",
      "_episode_id",
      "_result",
      "_truth",
  )

  def __init__(
      self,
      *,
      condition_id: str,
      session_id: str,
      episode_id: str,
      result: Mapping[str, Any],
      truth: Mapping[str, Any],
  ) -> None:
    """创建中央结果奖励请求。

    参数：
      condition_id: 当前实验条件 ID。
      session_id: 当前独立重复 ID。
      episode_id: 当前 Episode 的全局唯一 ID。
      result: 已完成运行的实际结果，不含节点策略内部状态。
      truth: 当前 Episode 的中央真值，只授权给结果奖励器和评价器。
    """
    self._condition_id = validate_id(condition_id)
    self._session_id = validate_id(session_id)
    self._episode_id = validate_id(episode_id)
    if not isinstance(result, Mapping) or not isinstance(truth, Mapping):
      raise TypeError("EpisodeOutcomeRequest.result/truth 必须是映射")
    self._result = json_copy(dict(result))
    self._truth = json_copy(dict(truth))

  @property
  def condition_id(self) -> str:
    """返回当前实验条件 ID。"""
    return self._condition_id

  @property
  def session_id(self) -> str:
    """返回当前独立 Session ID。"""
    return self._session_id

  @property
  def episode_id(self) -> str:
    """返回当前 Episode ID。"""
    return self._episode_id

  @property
  def result(self) -> Mapping[str, Any]:
    """返回实际运行结果的独立只读副本。"""
    return MappingProxyType(json_copy(self._result))

  @property
  def truth(self) -> Mapping[str, Any]:
    """返回中央真值的独立只读副本。"""
    return MappingProxyType(json_copy(self._truth))

  def to_dict(self) -> dict[str, Any]:
    """返回适合研究审计的中央请求副本。"""
    return {
        "condition_id": self.condition_id,
        "session_id": self.session_id,
        "episode_id": self.episode_id,
        "result": json_copy(self._result),
        "truth": json_copy(self._truth),
    }
