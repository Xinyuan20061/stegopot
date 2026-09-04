"""核心载体级 StegoKit 适配；解码输入来自实际接收文本。"""

from stegopot.domain.interface.codec import Carrier, DecodeResult, EncodeResult
from stegopot.domain.interface.stego import StegoEmbedRequest, StegoExtractRequest, StegoGenerationConfig
from stegopot.infrastructure.integrations.stegokit.adapter import StegoKitAdapter


class StegoKitCodec:
  """将 StegoKit 算法接入新载体契约，不用编码端 token ID 偷渡信息。"""

  def __init__(self, *, adapter, tokenizer, algorithm="ac", generation=None, encode_config=None, decode_config=None):
    """设置工具依赖与算法参数。

    参数：
      adapter: 已注入的 StegoTool 兼容适配器，由本对象负责关闭。
      tokenizer: 与本地模型匹配的分词器，用于从真实载体重新分词。
      algorithm: StegoKit 算法名称。
      generation: 编解码共享的生成参数映射。
      encode_config: 算法特有编码配置。
      decode_config: 算法特有解码配置，不假设与编码配置字段相同。
    """
    self._adapter, self._tokenizer, self._algorithm = adapter, tokenizer, algorithm
    self._generation = StegoGenerationConfig(**(generation or {}))
    self._encode_config, self._decode_config = encode_config, decode_config

  def encode(self, request):
    """编码 request.bits；双方必须显式共享 messages/material，而非共享内部结果。"""
    shared = request.shared_material
    result = self._adapter.embed(StegoEmbedRequest(
        algorithm=self._algorithm, secret_bits=request.bits,
        messages=shared.get("messages", [{"role": "user", "content": request.cover.content}]),
        generation=self._generation, config=self._encode_config, material=shared.get("material")))
    tokens = self._tokenizer.encode(result.text, add_special_tokens=False)
    if list(tokens) != list(result.generated_token_ids):
      raise ValueError("当前 tokenizer 无法保持文本/token 往返一致，拒绝依靠隐藏 token ID 解码")
    if result.consumed_bits > len(request.bits):
      raise ValueError("工具报告的消耗比特超过输入长度")
    return EncodeResult(Carrier(result.text), result.consumed_bits,
                        {"algorithm": self._algorithm, "origin": "tool", "token_roundtrip_verified": True})

  def decode(self, request):
    """只对 request.carrier 的实际文本重新分词，显式共享参数须预先配置。"""
    shared = request.shared_material
    if request.carrier.media_type != "text/plain" or "messages" not in shared:
      raise ValueError("解码要求 text/plain 载体和预先共享的 messages")
    result = self._adapter.extract(StegoExtractRequest(
        algorithm=self._algorithm,
        generated_token_ids=self._tokenizer.encode(request.carrier.content, add_special_tokens=False),
        messages=shared["messages"], generation=self._generation,
        max_bits=shared.get("max_bits"), config=self._decode_config, material=shared.get("material")))
    return DecodeResult(result.bits)

  def close(self):
    """关闭本对象拥有的适配器；不关闭其他组件注入的共享资源。"""
    self._adapter.close()
