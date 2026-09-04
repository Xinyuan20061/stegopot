"""运行资源控制契约；实现由应用层提供，适配器不能反向依赖运行器。"""

from collections.abc import Mapping
from typing import Any, Literal, Protocol


class ExecutionGuard(Protocol):
  """绑定一次试验的宿主控制器；不向组件暴露其他节点或中央真值。"""

  def checkpoint(self) -> None:
    """检查取消、截止时间和已触发限制；不满足时抛出 ExecutionStopped。"""
    ...

  def reserve(self, kind: Literal["model", "tool"], *, node_id: str) -> None:
    """为 node_id 预占一次 kind 调用；拒绝发生在执行外部操作之前。"""
    ...

  def check_size(self, value: Any, *, kind: Literal["message", "context"]) -> None:
    """检查 value 的 UTF-8 JSON 大小；message 字符串只计算正文 UTF-8 字节。"""
    ...

  def record_usage(self, usage: Mapping[str, Any] | None) -> None:
    """累计服务端 usage；缺失数据标记为未知，不估算成真实零用量。"""
    ...
