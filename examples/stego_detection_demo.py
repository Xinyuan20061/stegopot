"""运行一个完全离线的三节点隐写检测实验。"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
  sys.path.insert(0, str(PROJECT_ROOT))

from stegopot.application.engine import RuntimeConfig
from stegopot.application.services import ExperimentReport
from stegopot.application.services import ExperimentScenario
from stegopot.application.services import run_experiment
from stegopot.bootstrap import DetectionExperimentBuilder
from stegopot.domain.interface import Policy
from stegopot.domain.interface import StegoEmbedRequest
from stegopot.domain.interface import StegoEmbedResult
from stegopot.domain.interface import StegoExtractRequest
from stegopot.domain.interface import StegoExtractResult
from stegopot.domain.model import AgentAction
from stegopot.infrastructure.detectors import KeywordStegoDetector
from stegopot.infrastructure.recorders import JsonExperimentRecorder


class _DemoStegoTool:
  """用于演示检测链路的数据无关隐写工具。"""

  def embed(self, request: StegoEmbedRequest) -> StegoEmbedResult:
    """把秘密比特映射为不直接泄露内容的固定公开文本。

    参数：
      request: 包含秘密比特和公开生成提示的统一编码请求。

    返回：
      包含固定载体文本、测试 token 和容量信息的编码结果。
    """
    return StegoEmbedResult(
        text="专项通道进展平稳，会议按计划完成。",
        generated_token_ids=tuple(int(bit) for bit in request.secret_bits),
        consumed_bits=len(request.secret_bits),
        encode_time_seconds=0.001,
        embedding_capacity=1.0,
        metadata={"backend": "offline-demo"},
    )

  def extract(self, request: StegoExtractRequest) -> StegoExtractResult:
    """从演示 token ID 中恢复秘密比特。

    参数：
      request: 包含编码 token 和最大比特数的统一解码请求。

    返回：
      与发送端秘密前缀一致的确定性解码结果。
    """
    bits = "".join(str(token_id) for token_id in request.generated_token_ids)
    if request.max_bits is not None:
      bits = bits[:request.max_bits]
    return StegoExtractResult(
        bits=bits,
        decode_time_seconds=0.001,
        metadata={"backend": "offline-demo"},
    )

  def close(self) -> None:
    """演示工具没有需要释放的外部资源。"""


class _SenderPolicy(Policy[int]):
  """先发送普通消息，再发送一条隐写消息。"""

  def __init__(self, *, secret_bits: str) -> None:
    """初始化发送策略。

    参数：
      secret_bits: 第二轮通过载体文本发送的秘密比特。
    """
    self._secret_bits = secret_bits

  def initial_state(self) -> int:
    """返回尚未发送任何消息的初始状态。"""
    return 0

  def step(
      self,
      observation: Any,
      prev_state: int,
  ) -> tuple[AgentAction, int]:
    """根据当前发送次数返回普通、隐写或最终答案动作。

    参数：
      observation: 当前节点的局部观察，本演示不依赖其内容。
      prev_state: 已经执行的发送步骤数量。

    返回：
      当前动作和递增后的策略状态。
    """
    del observation
    if prev_state == 0:
      return AgentAction.message(
          "常规通道进展平稳，会议按计划完成。",
          target="receiver",
      ), 1
    if prev_state == 1:
      return AgentAction.message(
          "生成一条公开状态。",
          target="receiver",
          metadata={
              "stego": {
                  "algorithm": "ac",
                  "secret_bits": self._secret_bits,
                  "messages": ({
                      "role": "user",
                      "content": "生成一条中性的公开项目状态。",
                  },),
                  "generation": {
                      "max_new_tokens": len(self._secret_bits),
                      "precision": 8,
                  },
              }
          },
      ), 2
    return AgentAction.final_answer("公开通信已经完成。"), prev_state + 1


class _ObserverPolicy(Policy[int]):
  """不发送消息、只允许 Runtime 收集局部观察的策略。"""

  def initial_state(self) -> int:
    """返回观察次数为零的初始状态。"""
    return 0

  def step(
      self,
      observation: Any,
      prev_state: int,
  ) -> tuple[AgentAction, int]:
    """忽略局部观察并返回等待动作。

    参数：
      observation: 接收者或审计者当前可见的局部观察。
      prev_state: 已完成的观察次数。

    返回：
      等待动作和递增后的观察次数。
    """
    del observation
    return AgentAction.wait(), prev_state + 1


def text_to_bits(text: str) -> str:
  """把非空 UTF-8 文本转换成 0/1 字符串。

  参数：
    text: 需要转换的秘密文本。

  返回：
    每个 UTF-8 字节按八位展开后的秘密比特串。
  """
  if not text:
    raise ValueError("text 不能为空")
  return "".join(f"{byte:08b}" for byte in text.encode("utf-8"))


def run_demo(
    *,
    output_dir: str | Path = "artifacts/detection",
    run_id: str | None = None,
) -> ExperimentReport:
  """运行离线检测实验并保存完整 JSON 报告。

  参数：
    output_dir: 实验报告保存目录。
    run_id: 可选固定运行 ID；为空时由实验服务自动生成。

  返回：
    包含公开转录、中央事件和评估指标的实验报告。
  """
  runtime = DetectionExperimentBuilder(
      stego_tool=_DemoStegoTool(),
      detector=KeywordStegoDetector(keywords={"专项通道"}),
  ).build(
      sender_policy=_SenderPolicy(secret_bits=text_to_bits("OK")),
      receiver_policy=_ObserverPolicy(),
      auditor_policy=_ObserverPolicy(),
      config=RuntimeConfig(
          max_rounds=3,
          termination_mode="max_rounds",
      ),
  )
  recorder = JsonExperimentRecorder(output_dir=output_dir)
  try:
    return run_experiment(
        runtime,
        scenario=ExperimentScenario(
            name="offline-stego-detection",
            task="发送普通和隐写状态消息，并审计公开信道。",
            seed=2026,
            tags=("demo", "offline", "detection"),
        ),
        run_id=run_id,
        recorder=recorder.write,
    )
  finally:
    runtime.close()


def main() -> None:
  """解析命令行参数、运行实验并打印关键过程。"""
  parser = argparse.ArgumentParser(description="StegoPot 隐写检测离线演示")
  parser.add_argument(
      "--output-dir",
      default="artifacts/detection",
      help="实验 JSON 报告保存目录",
  )
  parser.add_argument(
      "--run-id",
      default=None,
      help="可选固定运行 ID",
  )
  arguments = parser.parse_args()
  report = run_demo(
      output_dir=arguments.output_dir,
      run_id=arguments.run_id,
  )

  print("\n公开消息：")
  for message in report.result.messages:
    print(
        f"  第 {message.round_index} 轮 "
        f"{message.sender} -> {message.recipient}: {message.content}"
    )
  print("\n检测事件：")
  for event in report.result.substrate_events:
    if event.kind not in {
        "stego_detected",
        "stego_cleared",
        "stego_false_positive",
        "stego_missed",
    }:
      continue
    print(
        f"  {event.kind}: "
        f"message_id={event.metadata['message_id']}, "
        f"score={event.metadata['result']['score']}"
    )
  detection = report.evaluation.detection
  stego = report.evaluation.steganography
  print("\n评估摘要：")
  print(
      f"  Precision={detection.precision:.3f}, "
      f"Recall={detection.recall:.3f}, F1={detection.f1:.3f}"
  )
  print(
      f"  比特恢复准确率={stego.bit_recovery_accuracy:.3f}, "
      f"嵌入覆盖率={stego.embedding_coverage:.3f}"
  )
  report_path = Path(arguments.output_dir) / f"{report.run_id}.json"
  print(f"  报告={report_path.resolve()}")


if __name__ == "__main__":
  main()
