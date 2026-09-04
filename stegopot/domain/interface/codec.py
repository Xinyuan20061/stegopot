"""面向公开载体的隐写接口；不要求解码端获得发送者原始 token ID。"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Carrier:
  """公开载体。content 为实际传输文本，media_type 声明格式，不携带秘密或编码端材料。"""

  content: str
  media_type: str = "text/plain"

  def __post_init__(self) -> None:
    if not isinstance(self.content, str) or not isinstance(self.media_type, str):
      raise ValueError("载体必须包含文本 content 和 media_type")


@dataclass(frozen=True)
class EncodeRequest:
  """编码请求。bits 是私有载荷，cover 是公开输入，shared_material 是明确授权的共享材料。"""

  bits: str
  cover: Carrier
  shared_material: Mapping[str, Any] = field(default_factory=dict)

  def __post_init__(self) -> None:
    if not isinstance(self.bits, str) or set(self.bits) - {"0", "1"}:
      raise ValueError("bits 必须是二进制字符串")


@dataclass(frozen=True)
class DecodeRequest:
  """解码请求。carrier 是实际收到的公开载体，shared_material 必须是预先共享的材料。"""

  carrier: Carrier
  shared_material: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EncodeResult:
  """编码结果。carrier 可投递，consumed_bits 用于容量统计，research 仅供中央审计。"""

  carrier: Carrier
  consumed_bits: int
  research: Mapping[str, Any] = field(default_factory=dict)

  def __post_init__(self) -> None:
    if not isinstance(self.carrier, Carrier) or type(self.consumed_bits) is not int or self.consumed_bits < 0:
      raise ValueError("编码结果必须包含合法载体和非负比特计数")


@dataclass(frozen=True)
class DecodeResult:
  """解码结果。bits 为工具恢复的私有数据，不代表 LLM 自主推断。"""

  bits: str

  def __post_init__(self) -> None:
    if not isinstance(self.bits, str) or set(self.bits) - {"0", "1"}:
      raise ValueError("解码结果必须为二进制字符串")


class StegoCodec(Protocol):
  """新的载体级隐写契约；算法参数在插件工厂配置中校验。"""

  def encode(self, request: EncodeRequest) -> EncodeResult:
    """把 request.bits 嵌入载体，研究材料不能成为隐含传输通道。"""
    ...

  def decode(self, request: DecodeRequest) -> DecodeResult:
    """仅根据 request 中收到的载体和共享材料恢复比特。"""
    ...

  def close(self) -> None:
    """释放模型资源。"""
    ...
