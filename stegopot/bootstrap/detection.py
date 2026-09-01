"""标准发送者、接收者和审计者检测实验的组合入口。"""

from __future__ import annotations

from stegopot.application.engine import MultiAgentRuntime
from stegopot.application.engine import RuntimeConfig
from stegopot.bootstrap.builder import MultiAgentBuilder
from stegopot.domain.interface import Policy
from stegopot.domain.interface import StegoDetector
from stegopot.domain.interface import StegoTool
from stegopot.infrastructure.substrates.detection import DetectionSubstrate
from stegopot.infrastructure.substrates.stego import SteganographySubstrate


class DetectionExperimentBuilder:
  """组装标准发送者、接收者和审计者三节点运行器。"""

  def __init__(
      self,
      *,
      stego_tool: StegoTool,
      detector: StegoDetector,
      sender_id: str = "sender",
      receiver_id: str = "receiver",
      auditor_id: str = "auditor",
      stego_fail_fast: bool = True,
      detection_fail_fast: bool = True,
  ) -> None:
    """初始化标准检测实验构建器。

    参数：
      stego_tool: 负责生成载密文本和恢复秘密比特的隐写工具。
      detector: 负责分析公开载体文本的可插拔检测器。
      sender_id: 编码发送节点的唯一 ID。
      receiver_id: 被授权读取解码结果的节点 ID。
      auditor_id: 被授权读取公开检测发现的节点 ID。
      stego_fail_fast: 隐写处理失败时是否立即终止实验。
      detection_fail_fast: 检测器失败时是否立即终止实验。
    """
    node_ids = tuple(
        self._normalize_id(value, field_name)
        for value, field_name in (
            (sender_id, "sender_id"),
            (receiver_id, "receiver_id"),
            (auditor_id, "auditor_id"),
        )
    )
    if len(set(node_ids)) != len(node_ids):
      raise ValueError("sender_id、receiver_id 和 auditor_id 必须互不相同")
    self._stego_tool = stego_tool
    self._detector = detector
    self._sender_id, self._receiver_id, self._auditor_id = node_ids
    self._stego_fail_fast = bool(stego_fail_fast)
    self._detection_fail_fast = bool(detection_fail_fast)
    self._built = False

  def build(
      self,
      *,
      sender_policy: Policy,
      receiver_policy: Policy,
      auditor_policy: Policy,
      config: RuntimeConfig | None = None,
      receiver_can_reply: bool = False,
  ) -> MultiAgentRuntime:
    """构建一个带隐写编码、授权解码和公开检测的运行器。

    参数：
      sender_policy: 发送节点使用的 LLM、规则或测试策略。
      receiver_policy: 授权接收节点使用的策略。
      auditor_policy: 审计节点读取检测发现后使用的策略。
      config: 轮数、终止和错误处理配置；为空时使用 Runtime 默认值。
      receiver_can_reply: 是否允许接收者通过反向边向发送者回复。

    返回：
      完成三节点、拓扑和两层 Substrate 组装的 MultiAgentRuntime。
    """
    if self._built:
      raise RuntimeError("DetectionExperimentBuilder 每个实例只能构建一次")
    builder = MultiAgentBuilder()
    builder.add_node(
        node_id=self._sender_id,
        role="steganography_sender",
        policy=sender_policy,
    )
    builder.add_node(
        node_id=self._receiver_id,
        role="authorized_receiver",
        policy=receiver_policy,
    )
    builder.add_node(
        node_id=self._auditor_id,
        role="public_channel_auditor",
        policy=auditor_policy,
    )
    builder.connect(
        self._sender_id,
        self._receiver_id,
        bidirectional=receiver_can_reply,
    )
    stego_substrate = SteganographySubstrate(
        tool=self._stego_tool,
        decoder_nodes={self._receiver_id},
        fail_fast=self._stego_fail_fast,
    )
    detection_substrate = DetectionSubstrate(
        inner=stego_substrate,
        detector=self._detector,
        auditor_nodes={self._auditor_id},
        fail_fast=self._detection_fail_fast,
    )
    self._built = True
    return builder.build(
        config=config,
        substrate=detection_substrate,
    )

  @staticmethod
  def _normalize_id(value: str, field_name: str) -> str:
    """验证并规范化一个节点 ID。"""
    if not isinstance(value, str) or not value.strip():
      raise ValueError(f"{field_name} 必须是非空字符串")
    return value.strip()
