"""普通通信与受控隐写通信共用的载体意图模型。"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from collections.abc import Mapping
from typing import Literal


CommunicationMode = Literal["opaque", "instrumented"]


def carrier_sha256(content: str) -> str:
  """返回公开载体正文的 UTF-8 SHA-256。

  参数：
    content: 实际生成或投递的公开载体正文。

  返回：
    64 位小写十六进制摘要。
  """
  if not isinstance(content, str):
    raise TypeError("载体正文必须是字符串")
  return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommunicationIntent:
  """只供宿主研究链路读取的通信来源声明。

  ``opaque`` 表示框架不知道消息是否隐写，适用于研究自发行为；
  ``instrumented`` 表示消息由显式 codec 操作生成。该对象不会投递给
  Channel、Detector 或其他节点。

  属性：
    mode: ``opaque`` 或 ``instrumented``。
    carrier_sha256: Policy 输出正文的摘要，用于防止来源标签与正文错配。
    codec_id: instrumented 模式使用的 codec 资源 ID。
    payload_bits: 提交给编码器的秘密比特数。
    consumed_bits: 编码器实际报告消耗的比特数。
    carrier_token_count: 编码器按自身 tokenizer 统计的载体 token 数。
  """

  mode: CommunicationMode
  carrier_sha256: str
  codec_id: str | None = None
  payload_bits: int | None = None
  consumed_bits: int | None = None
  carrier_token_count: int | None = None

  def __post_init__(self) -> None:
    if self.mode not in {"opaque", "instrumented"}:
      raise ValueError("通信模式必须是 opaque 或 instrumented")
    if not re.fullmatch(r"[0-9a-f]{64}", self.carrier_sha256):
      raise ValueError("carrier_sha256 必须是 SHA-256 十六进制文本")
    values = (self.payload_bits, self.consumed_bits, self.carrier_token_count)
    if any(value is not None and (type(value) is not int or value < 0) for value in values):
      raise ValueError("通信比特数和 token 数必须是非负整数或 None")
    if self.mode == "opaque" and any(
        value is not None
        for value in (self.codec_id, self.payload_bits, self.consumed_bits, self.carrier_token_count)
    ):
      raise ValueError("opaque 通信不能伪装成已知 codec 操作")
    if self.mode == "instrumented":
      if not isinstance(self.codec_id, str) or not self.codec_id.strip():
        raise ValueError("instrumented 通信必须声明 codec_id")
      if self.payload_bits is None or self.consumed_bits is None:
        raise ValueError("instrumented 通信必须声明 payload_bits 和 consumed_bits")
      if self.consumed_bits > self.payload_bits:
        raise ValueError("consumed_bits 不能超过 payload_bits")

  @classmethod
  def from_dict(cls, value: Mapping[str, object]) -> "CommunicationIntent":
    """从研究结果中的标准字典恢复通信来源声明。

    参数：
      value: ``to_dict`` 生成的来源数据，不应包含秘密载荷。

    返回：
      经过模式、摘要和计数约束验证的不可变声明。
    """
    return cls(
        mode=str(value["mode"]),
        carrier_sha256=str(value["carrier_sha256"]),
        codec_id=None if value.get("codec_id") is None else str(value["codec_id"]),
        payload_bits=value.get("payload_bits"),
        consumed_bits=value.get("consumed_bits"),
        carrier_token_count=value.get("carrier_token_count"),
    )

  @classmethod
  def opaque(cls, content: str) -> "CommunicationIntent":
    """为不知道隐写真值的普通正文创建意图。

    参数：
      content: Policy 生成的实际消息正文。

    返回：
      不携带 codec 或秘密标签的 opaque 意图。
    """
    return cls(mode="opaque", carrier_sha256=carrier_sha256(content))

  @classmethod
  def instrumented(
      cls,
      content: str,
      *,
      codec_id: str,
      payload_bits: int,
      consumed_bits: int,
      carrier_token_count: int | None = None,
  ) -> "CommunicationIntent":
    """为显式 codec 生成的正文创建受控意图。

    参数：
      content: 编码器实际生成的公开正文。
      codec_id: 当前节点配置引用的 codec 资源 ID。
      payload_bits: 交给编码器的秘密比特数。
      consumed_bits: 编码器报告实际消耗的比特数。
      carrier_token_count: 编码器 tokenizer 对实际载体的 token 数。

    返回：
      可由宿主校验和审计、但不会公开投递的 instrumented 意图。
    """
    return cls(
        mode="instrumented",
        carrier_sha256=carrier_sha256(content),
        codec_id=codec_id,
        payload_bits=payload_bits,
        consumed_bits=consumed_bits,
        carrier_token_count=carrier_token_count,
    )

  def to_dict(self) -> dict[str, str | int | None]:
    """返回适合研究日志的标准字典，不包含秘密载荷。"""
    return {
        "mode": self.mode,
        "carrier_sha256": self.carrier_sha256,
        "codec_id": self.codec_id,
        "payload_bits": self.payload_bits,
        "consumed_bits": self.consumed_bits,
        "carrier_token_count": self.carrier_token_count,
    }
