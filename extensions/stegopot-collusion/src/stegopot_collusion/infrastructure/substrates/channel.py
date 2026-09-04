"""只传递模型生成正文的实验信道，不执行编码或解码算法。"""

from collections.abc import Mapping
import dataclasses
from typing import Any

from stegopot.domain.interface.substrate import (
    Substrate, SubstrateEvent, SubstrateResetContext,
    SubstrateStepContext, SubstrateStepResult,
)
from stegopot_collusion.domain.model.collusion import CHOICES, CollusionTrial


class CollusionChannel(Substrate):
  """按身份投影私有信息，支持断开信道对照并剥离动作元数据。"""

  def __init__(self, trial: CollusionTrial) -> None:
    """保存仅中央可见的 trial；仅 observe 方法负责信息授权。"""
    self._trial = trial
    self._messages = []

  def reset(self, context: SubstrateResetContext) -> None:
    """检查 context 的三节点拓扑身份，并清空上一运行的公开转录。"""
    if set(context.node_ids) != {"sender", "receiver", "observer"}:
      raise ValueError("此合成实验需要 sender、receiver、observer 三个节点")
    self._messages = []

  def observe(self, node_id: str) -> Mapping[str, Any]:
    """返回 node_id 的局部上下文，观察者永远拿不到协议或目标。"""
    common = {
        "choices": list(CHOICES), "authorized_choice": self._trial.public_target,
    }
    if node_id in {"sender", "receiver", "observer"}:
      return common
    raise ValueError(f"未知节点：{node_id}")

  def step(self, context: SubstrateStepContext) -> SubstrateStepResult:
    """处理 context 中的消息；控制组可阻断正文，任何组都不转交元数据。"""
    delivered = []
    events = []
    for message in context.messages:
      if (message.sender != "sender" or message.recipient != "receiver"
          or context.round_index != 0):
        raise ValueError("实验仅允许第零轮 sender 向 receiver 发送一次正文")
      blocked = self._trial.condition == "blocked_channel"
      events.append(SubstrateEvent(
          kind="collusion.channel_blocked" if blocked else "collusion.channel_delivered",
          round_index=context.round_index, actor=message.sender, target=message.recipient,
          metadata={"message_id": message.message_id,
                    "removed_metadata_keys": sorted(message.metadata)},
      ))
      if not blocked:
        delivered.append(dataclasses.replace(message, metadata={}))
    if len(delivered) > 1:
      raise ValueError("此实验不允许用消息数量编码")
    self._messages.extend(delivered)
    return SubstrateStepResult(messages=delivered, events=events)

  def state(self) -> Mapping[str, Any]:
    """返回研究用全局状态；该方法不是节点观察接口。"""
    return {"trial": self._trial.to_dict(), "delivered_count": len(self._messages)}
