"""公开通信信道干预的最小契约。"""

from typing import Protocol
from stegopot.domain.model.message import AgentMessage


class ChannelTransform(Protocol):
  """按顺序变换公开正文，不能改变消息身份或接收权限。"""

  def transform(self, message: AgentMessage) -> AgentMessage | None:
    """处理已剥离私有元数据的 message；返回 None 表示阻断，不允许新增投递目标。"""
    ...
