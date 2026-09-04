"""与具体隐写算法无关的确定性公开信道干预。"""

from dataclasses import replace
from stegopot.domain.model.message import AgentMessage


class BlockChannel:
  """阻断所有传入正文，用于明确配置的通信消融。"""

  def transform(self, message: AgentMessage) -> None:
    """丢弃 message，不创建替代消息。"""
    return None


class ReplaceChannel:
  """在公开正文中进行字面替换，不修改身份字段。"""

  def __init__(self, search: str, replacement: str) -> None:
    """以非空 search 匹配正文，使用 replacement 替换，不执行正则或代码。"""
    if not search:
      raise ValueError("search 不能为空")
    self._search = search
    self._replacement = replacement

  def transform(self, message: AgentMessage) -> AgentMessage:
    """返回只修改 message.content 的新消息。"""
    return replace(message, content=message.content.replace(self._search, self._replacement))
