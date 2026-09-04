"""不绑定存储实现的审计写入契约。"""

from collections.abc import Mapping
from typing import Any, Protocol


class AuditSink(Protocol):
  """接收结构化审计事件；写入失败必须向调用者传播。"""

  def emit(self, event: Mapping[str, Any]) -> None:
    """立即持久化或接收一条事件。

    参数：
      event: 含 kind、actor、round_index 和 data 的标准映射；默认属于
        研究记录，公开字段必须由独立的白名单投影决定。
    """
    ...
