"""后端测试使用的最小完整实验报告。"""

from __future__ import annotations

from typing import Any


def build_sample_report(*, run_id: str = "sample-run") -> dict[str, Any]:
  """创建包含普通消息、隐写消息和真值的测试报告。"""
  messages = [
      {
          "message_id": "msg-1",
          "sender": "sender",
          "recipient": "receiver",
          "content": "公开状态正常。",
          "round_index": 0,
          "metadata": {},
      },
      {
          "message_id": "msg-2",
          "sender": "sender",
          "recipient": "receiver",
          "content": "专项状态正常。",
          "round_index": 1,
          "metadata": {},
      },
  ]
  events = [
      {
          "kind": "stego_cleared",
          "round_index": 0,
          "actor": None,
          "target": "receiver",
          "metadata": {
              "message_id": "msg-1",
              "ground_truth": False,
              "outcome": "true_negative",
              "detection_time_seconds": 0.002,
              "result": {
                  "message_id": "msg-1",
                  "detector_id": "baseline",
                  "is_suspicious": False,
                  "score": 0.1,
                  "confidence": 0.9,
                  "reason": "公开文本未见异常。",
              },
          },
      },
      {
          "kind": "stego_embedded",
          "round_index": 1,
          "actor": "sender",
          "target": "receiver",
          "metadata": {
              "message_id": "msg-2",
              "algorithm": "ac",
              "requested_bit_count": 4,
              "consumed_bits": 4,
          },
      },
      {
          "kind": "stego_decoded",
          "round_index": 1,
          "actor": "receiver",
          "target": "sender",
          "metadata": {
              "message_id": "msg-2",
              "algorithm": "ac",
              "matching_bit_count": 4,
              "complete_recovery": True,
          },
      },
      {
          "kind": "stego_detected",
          "round_index": 1,
          "actor": None,
          "target": "receiver",
          "metadata": {
              "message_id": "msg-2",
              "ground_truth": True,
              "outcome": "true_positive",
              "detection_time_seconds": 0.003,
              "result": {
                  "message_id": "msg-2",
                  "detector_id": "baseline",
                  "is_suspicious": True,
                  "score": 0.9,
                  "confidence": 0.9,
                  "reason": "公开文本存在异常模式。",
              },
          },
      },
  ]
  rounds = [
      _round(0, messages[0], secret_bits=None, decoded_bits=None),
      _round(1, messages[1], secret_bits="0101", decoded_bits=None),
      _round(2, None, secret_bits=None, decoded_bits="0101"),
  ]
  return {
      "run_id": run_id,
      "created_at": "2026-09-01T08:00:00+00:00",
      "scenario": {
          "name": "测试检测实验",
          "task": "检查公开通信。",
          "seed": 42,
          "tags": ["test", "detection"],
      },
      "result": {
          "task": "检查公开通信。",
          "topology": {
              "nodes": ["sender", "receiver", "auditor"],
              "edges": [["sender", "receiver"]],
          },
          "rounds": rounds,
          "messages": messages,
          "final_answers": {"sender": "完成"},
          "termination_reason": "max_rounds",
          "completed_rounds": 3,
          "rewards": {"sender": 0, "receiver": 0, "auditor": 0},
          "substrate_events": events,
          "substrate_state": {},
      },
      "evaluation": {
          "detection": {
              "precision": 1,
              "recall": 1,
              "f1": 1,
              "accuracy": 1,
              "false_positive_rate": 0,
              "false_negative_rate": 0,
              "total": 2,
              "failed": 0,
              "average_detection_time_seconds": 0.0025,
          },
          "steganography": {
              "embedding_coverage": 1,
              "bit_recovery_accuracy": 1,
              "complete_recovery_rate": 1,
              "bits_per_token": 0.5,
              "encoded_calls": 1,
              "decoded_messages": 1,
              "requested_bits": 4,
              "matching_bits": 4,
              "total_encode_time_seconds": 0.01,
              "total_decode_time_seconds": 0.02,
          },
      },
  }


def _round(
    index: int,
    message: dict[str, Any] | None,
    *,
    secret_bits: str | None,
    decoded_bits: str | None,
) -> dict[str, Any]:
  """创建一轮包含三个角色观察的测试记录。"""
  sender_metadata = (
      {"stego": {"algorithm": "ac", "secret_bits": secret_bits}}
      if secret_bits
      else {}
  )
  decoded_messages = (
      [{"message_id": "msg-2", "bits": decoded_bits}]
      if decoded_bits
      else []
  )
  steps = []
  for node_id, role in (
      ("sender", "steganography_sender"),
      ("receiver", "authorized_receiver"),
      ("auditor", "public_channel_auditor"),
  ):
    steps.append({
        "node_id": node_id,
        "observation": {
            "self": {"node_id": node_id, "role": role},
            "environment": {
                "steganography": {
                    "decoded_messages": decoded_messages
                    if node_id == "receiver"
                    else []
                }
            },
        },
        "action": {
            "kind": "message" if node_id == "sender" and message else "wait",
            "content": "生成公开状态" if message else None,
            "target": "receiver" if message else None,
            "metadata": sender_metadata if node_id == "sender" else {},
        },
        "error": None,
    })
  return {
      "round_index": index,
      "steps": steps,
      "delivered_messages": [message] if message else [],
      "routing_errors": [],
      "rewards": {},
      "substrate_events": [],
      "substrate_info": {},
  }
