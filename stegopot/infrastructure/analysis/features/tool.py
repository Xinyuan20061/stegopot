"""Tool 事件的固定结构化特征。"""

from collections.abc import Mapping
from typing import Any


def tool_event_features(event: Mapping[str, Any]) -> dict[str, Any]:
  """只保留工具身份、操作、参数形状和结果状态，不加入中央标签。"""
  arguments = event.get("arguments", {})
  arguments = arguments if isinstance(arguments, Mapping) else {}
  return {"tool": event.get("tool"), "operation": event.get("operation"),
          "argument_keys": sorted(str(key) for key in arguments),
          "argument_count": len(arguments), "status": event.get("status")}

