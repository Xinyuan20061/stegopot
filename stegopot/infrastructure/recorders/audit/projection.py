"""公开审计事件的白名单投影；未知事件默认不公开。"""

from collections.abc import Mapping
from typing import Any


def public_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
  """只公开信道正文与最小运行状态。

  参数：
    event: 研究视角事件，可能包含私有目标、提示词和真实标签。

  返回：
    公开事件，或不允许公开时的 None。正文可能由模型主动泄露信息，
    此函数只保证不附带后台私有字段，不保证消息文本自身安全。
  """
  kind = event.get("kind")
  data = event.get("data", {})
  if kind == "runtime.started":
    payload = {"topology": data.get("topology", {})}
  elif kind == "runtime.message":
    message = data.get("message", {})
    payload = {"message": {
        key: message.get(key)
        for key in ("message_id", "sender", "recipient", "round_index", "content")
    }}
  elif kind == "runtime.completed":
    payload = {key: data.get(key) for key in ("completed_rounds", "termination_reason")}
  elif kind == "runtime.failed":
    payload = {"error_type": data.get("error_type")}
  else:
    return None
  return {
      "kind": kind, "actor": event.get("actor"),
      "round_index": event.get("round_index"), "data": payload,
  }
