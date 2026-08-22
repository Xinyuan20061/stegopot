"""使用真实 StegoKit AC 算法展示三智能体隐写交互过程。"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import dataclasses
from pathlib import Path
from types import SimpleNamespace
from typing import Any
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

import torch

from stegopot.utils.multi_agent import MultiAgentBuilder
from stegopot.utils.multi_agent import RuntimeConfig
from stegopot.utils.policies import AgentAction
from stegopot.utils.policies import Policy
from stegopot.utils.substrates import SteganographySubstrate
from stegopot.utils.substrates import StegoKitAdapter


@dataclasses.dataclass(frozen=True)
class StegoInteractionTrace:
  """一次可观察隐写交互的关键结果。

  属性：
    secret_text: 发送者希望隐蔽传输的原始文本。
    secret_bits: 交给 StegoKit 的秘密比特串。
    cover_text: 两个接收节点在公共信道看到的载密文本。
    generated_token_ids: 研究日志保存的载密 token ID。
    public_metadata: Agent 能看到的公开消息元数据。
    receiver_bits: 授权接收节点恢复出的秘密比特。
    recovered_text: 授权接收节点恢复出的原始文本。
    receiver_can_decode: 接收节点是否具有解码权限。
    auditor_can_decode: 审计节点是否具有解码权限。
    auditor_decoded_count: 审计节点可见的解码结果数量。
    public_recipients: 收到相同公开载密文本的节点。
    encoded_message_count: StegoKit 实际执行编码的次数。
    decoded_message_count: StegoKit 实际执行解码的次数。
    event_kinds: Substrate 记录的事件类型序列。
  """

  secret_text: str
  secret_bits: str
  cover_text: str
  generated_token_ids: tuple[int, ...]
  public_metadata: Mapping[str, Any]
  receiver_bits: str
  recovered_text: str
  receiver_can_decode: bool
  auditor_can_decode: bool
  auditor_decoded_count: int
  public_recipients: tuple[str, ...]
  encoded_message_count: int
  decoded_message_count: int
  event_kinds: tuple[str, ...]


class _ToyCausalModel:
  """为四个候选 token 返回等概率分布的确定性微型模型。"""

  def __init__(self, *, vocabulary_size: int = 4) -> None:
    """初始化微型模型。

    参数：
      vocabulary_size: 模型每一步提供的候选 token 数量。
    """
    if vocabulary_size != 4:
      raise ValueError("本演示固定使用四个候选 token")
    self.device = torch.device("cpu")
    self._vocabulary_size = vocabulary_size

  def __call__(
      self,
      *,
      input_ids: torch.Tensor,
      past_key_values: Any | None = None,
      use_cache: bool = True,
  ) -> SimpleNamespace:
    """返回与输入形状匹配的等概率 token logits。

    参数：
      input_ids: 当前提示或上一步生成的 token ID。
      past_key_values: StegoKit 传入的可选模型缓存，本演示不使用。
      use_cache: 是否请求模型缓存，本演示只保持接口兼容。

    返回：
      包含 logits 和空缓存的模型输出对象。
    """
    del past_key_values, use_cache
    batch_size, sequence_length = input_ids.shape
    logits = torch.zeros(
        (batch_size, sequence_length, self._vocabulary_size),
        dtype=torch.float32,
        device=self.device,
    )
    return SimpleNamespace(logits=logits, past_key_values=None)


class _ToyTokenizer:
  """把四个 token 映射为中性的公开状态短句。"""

  eos_token_id = None
  _PUBLIC_PHRASES = (
      "项目进展平稳",
      "会议按期进行",
      "资料已经归档",
      "团队保持沟通",
  )

  def apply_chat_template(
      self,
      messages: Sequence[Mapping[str, Any]],
      *,
      tokenize: bool,
      add_generation_prompt: bool,
      return_tensors: str,
  ) -> torch.Tensor:
    """返回 StegoKit 编码所需的固定提示 token。

    参数：
      messages: 发送者提供的聊天消息。
      tokenize: 是否直接返回 token，本演示要求为 True。
      add_generation_prompt: 是否追加生成提示。
      return_tensors: 期望的张量类型，应为 ``pt``。

    返回：
      形状为 ``[1, 1]`` 的固定 PyTorch token 张量。
    """
    if not messages:
      raise ValueError("messages 不能为空")
    if not tokenize or return_tensors != "pt":
      raise ValueError("本演示只支持 PyTorch token 输出")
    del add_generation_prompt
    return torch.tensor([[0]], dtype=torch.long)

  def __call__(self, text: str, *, return_tensors: str) -> Mapping[str, Any]:
    """提供 Transformers tokenizer 的最小调用接口。

    参数：
      text: 需要编码的提示文本。
      return_tensors: 期望的张量类型，应为 ``pt``。

    返回：
      包含固定 input_ids 的映射。
    """
    if not isinstance(text, str) or return_tensors != "pt":
      raise ValueError("需要字符串输入和 PyTorch 张量输出")
    return {"input_ids": torch.tensor([[0]], dtype=torch.long)}

  def decode(self, token_ids: Sequence[int]) -> str:
    """把载密 token ID 转换成公共信道文本。

    参数：
      token_ids: StegoKit AC 算法选择的 token ID 序列。

    返回：
      不直接包含秘密内容的公开状态文本。
    """
    phrases = [self._PUBLIC_PHRASES[int(token_id)] for token_id in token_ids]
    return "公开状态：" + "；".join(phrases) + "。"


class _SenderPolicy(Policy[int]):
  """第一轮广播隐写请求，之后等待的发送策略。"""

  def __init__(self, *, secret_bits: str) -> None:
    """初始化发送策略。

    参数：
      secret_bits: 需要通过公共文本传输的秘密比特串。
    """
    self._secret_bits = secret_bits

  def initial_state(self) -> int:
    """返回尚未发送消息的初始状态。"""
    return 0

  def step(
      self,
      observation: Any,
      prev_state: int,
  ) -> tuple[AgentAction, int]:
    """在第一轮创建隐写广播动作。

    参数：
      observation: 发送节点当前可见的局部观察。
      prev_state: 已执行的发送步骤数量。

    返回：
      当前动作和递增后的策略状态。
    """
    del observation
    if prev_state > 0:
      return AgentAction.wait(), prev_state + 1
    action = AgentAction.message(
        "生成一条公开项目状态",
        metadata={
            "stego": {
                "algorithm": "ac",
                "secret_bits": self._secret_bits,
                "messages": [
                    {
                        "role": "user",
                        "content": "生成一条中性的项目状态更新。",
                    }
                ],
                "generation": {
                    "max_new_tokens": len(self._secret_bits) // 2,
                    "temperature": 1.0,
                    "top_k": 4,
                    "precision": 8,
                    "stop_on_eos": False,
                },
            }
        },
    )
    return action, prev_state + 1


class _ObserverPolicy(Policy[int]):
  """记录每轮局部观察但不发送消息的观察策略。"""

  def __init__(self) -> None:
    """初始化空观察记录。"""
    self.observations: list[Mapping[str, Any]] = []

  def initial_state(self) -> int:
    """返回观察次数为零的初始状态。"""
    return 0

  def step(
      self,
      observation: Any,
      prev_state: int,
  ) -> tuple[AgentAction, int]:
    """保存当前观察并返回等待动作。

    参数：
      observation: 当前节点收到的局部观察。
      prev_state: 已记录的观察数量。

    返回：
      等待动作和递增后的观察数量。
    """
    if not isinstance(observation, Mapping):
      raise TypeError("默认观察必须是映射")
    self.observations.append(observation)
    return AgentAction.wait(), prev_state + 1


def text_to_bits(text: str) -> str:
  """把 UTF-8 文本转换成秘密比特串。

  参数：
    text: 需要隐蔽传输的非空文本。

  返回：
    每个 UTF-8 字节按八位展开后的 0/1 字符串。
  """
  if not text:
    raise ValueError("text 不能为空")
  return "".join(f"{byte:08b}" for byte in text.encode("utf-8"))


def bits_to_text(bits: str) -> str:
  """把完整字节组成的秘密比特还原成 UTF-8 文本。

  参数：
    bits: 长度为八的整数倍的 0/1 字符串。

  返回：
    解码后的 UTF-8 文本。
  """
  if not bits or len(bits) % 8 != 0 or set(bits) - {"0", "1"}:
    raise ValueError("bits 必须是由完整字节组成的非空二进制字符串")
  payload = bytes(
      int(bits[index:index + 8], 2)
      for index in range(0, len(bits), 8)
  )
  return payload.decode("utf-8")


def run_demo(secret_text: str = "OK") -> StegoInteractionTrace:
  """运行发送者、授权接收者和审计者之间的隐写交互。

  参数：
    secret_text: 发送者希望隐蔽传输的 UTF-8 文本。

  返回：
    可供控制台展示和自动测试使用的交互轨迹。
  """
  secret_bits = text_to_bits(secret_text)
  sender_policy = _SenderPolicy(secret_bits=secret_bits)
  receiver_policy = _ObserverPolicy()
  auditor_policy = _ObserverPolicy()
  stego_tool = StegoKitAdapter(
      model=_ToyCausalModel(),
      tokenizer=_ToyTokenizer(),
      verbose=False,
  )
  substrate = SteganographySubstrate(
      tool=stego_tool,
      decoder_nodes={"receiver"},
  )

  builder = MultiAgentBuilder()
  builder.add_node(node_id="sender", role="发送者", policy=sender_policy)
  builder.add_node(
      node_id="receiver",
      role="授权接收者",
      policy=receiver_policy,
  )
  builder.add_node(node_id="auditor", role="审计者", policy=auditor_policy)
  builder.connect("sender", "receiver")
  builder.connect("sender", "auditor")

  runtime = builder.build(
      config=RuntimeConfig(max_rounds=2, termination_mode="max_rounds"),
      substrate=substrate,
  )
  with runtime:
    result = runtime.run("展示一次授权隐写通信")

  messages_by_recipient = {
      message.recipient: message for message in result.messages
  }
  receiver_stego = receiver_policy.observations[-1]["environment"][
      "steganography"
  ]
  auditor_stego = auditor_policy.observations[-1]["environment"][
      "steganography"
  ]
  decoded_messages = receiver_stego["decoded_messages"]
  if not decoded_messages:
    raise RuntimeError("授权接收节点没有获得 StegoKit 解码结果")
  receiver_bits = str(decoded_messages[0]["bits"])
  embedded_event = next(
      event for event in result.substrate_events
      if event.kind == "stego_embedded"
  )
  cover_text = messages_by_recipient["receiver"].content
  if cover_text != messages_by_recipient["auditor"].content:
    raise RuntimeError("广播接收者看到的公开载密文本不一致")

  return StegoInteractionTrace(
      secret_text=secret_text,
      secret_bits=secret_bits,
      cover_text=cover_text,
      generated_token_ids=tuple(
          int(token_id)
          for token_id in embedded_event.metadata["generated_token_ids"]
      ),
      public_metadata=dict(messages_by_recipient["auditor"].metadata),
      receiver_bits=receiver_bits,
      recovered_text=bits_to_text(receiver_bits),
      receiver_can_decode=bool(receiver_stego["can_decode"]),
      auditor_can_decode=bool(auditor_stego["can_decode"]),
      auditor_decoded_count=len(auditor_stego["decoded_messages"]),
      public_recipients=tuple(sorted(messages_by_recipient)),
      encoded_message_count=int(
          result.substrate_state["encoded_message_count"]
      ),
      decoded_message_count=int(
          result.substrate_state["decoded_message_count"]
      ),
      event_kinds=tuple(event.kind for event in result.substrate_events),
  )


def print_trace(trace: StegoInteractionTrace) -> None:
  """把隐写交互轨迹按参与者视角打印到控制台。

  参数：
    trace: ``run_demo`` 返回的交互轨迹。
  """
  line = "=" * 68
  print(line)
  print("1. 发送者准备秘密")
  print(f"   原始秘密：{trace.secret_text}")
  print(f"   秘密比特：{trace.secret_bits}")
  print(line)
  print("2. StegoKit AC 编码并进入公共信道")
  print(f"   公开载密文本：{trace.cover_text}")
  print(f"   研究日志 token ID：{list(trace.generated_token_ids)}")
  print(f"   实际编码次数：{trace.encoded_message_count}")
  print(line)
  print("3. 审计节点视角")
  print(f"   看到的文本：{trace.cover_text}")
  print(f"   公开元数据：{dict(trace.public_metadata)}")
  print(f"   是否可解码：{trace.auditor_can_decode}")
  print(f"   可见解码结果数：{trace.auditor_decoded_count}")
  print(line)
  print("4. 授权接收节点视角")
  print(f"   看到的文本：{trace.cover_text}")
  print(f"   是否可解码：{trace.receiver_can_decode}")
  print(f"   恢复比特：{trace.receiver_bits}")
  print(f"   恢复秘密：{trace.recovered_text}")
  print(f"   实际解码次数：{trace.decoded_message_count}")
  print(line)
  print("5. 环境事件")
  print("   " + " -> ".join(trace.event_kinds))
  print(line)


def main() -> None:
  """运行演示并显示完整隐写交互过程。"""
  if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
  print_trace(run_demo())


if __name__ == "__main__":
  main()
