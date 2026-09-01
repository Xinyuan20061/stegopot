"""隐写检测环境、实验评估和报告记录测试。"""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
from typing import Any
import unittest

from stegopot.application.engine import RuntimeConfig
from stegopot.application.services import ExperimentScenario
from stegopot.application.services import run_experiment
from stegopot.bootstrap import DetectionExperimentBuilder
from stegopot.domain.interface import Policy
from stegopot.domain.interface import StegoDetector
from stegopot.domain.interface import StegoEmbedRequest
from stegopot.domain.interface import StegoEmbedResult
from stegopot.domain.interface import StegoExtractRequest
from stegopot.domain.interface import StegoExtractResult
from stegopot.domain.model import AgentAction
from stegopot.domain.model import DetectionMetrics
from stegopot.domain.model import DetectionRequest
from stegopot.domain.model import DetectionResult
from stegopot.infrastructure.detectors import LLMStegoDetector
from stegopot.infrastructure.detectors import MockStegoDetector
from stegopot.infrastructure.detectors import PerplexityStegoDetector
from stegopot.infrastructure.llm.clients import MockLLMClient
from stegopot.infrastructure.recorders import JsonExperimentRecorder


SECRET_BITS = "01001111"


class _DeterministicStegoTool:
  """把秘密比特映射成固定公开文本的离线隐写工具。"""

  def __init__(self) -> None:
    """初始化资源关闭标记。"""
    self.closed = False

  def embed(self, request: StegoEmbedRequest) -> StegoEmbedResult:
    """返回不直接包含秘密比特的固定载体文本。"""
    return StegoEmbedResult(
        text="专项通道状态稳定，资料已经归档。",
        generated_token_ids=tuple(int(bit) for bit in request.secret_bits),
        consumed_bits=len(request.secret_bits),
        encode_time_seconds=0.01,
        embedding_capacity=1.0,
    )

  def extract(self, request: StegoExtractRequest) -> StegoExtractResult:
    """从测试 token ID 中恢复秘密比特。"""
    bits = "".join(str(token_id) for token_id in request.generated_token_ids)
    if request.max_bits is not None:
      bits = bits[:request.max_bits]
    return StegoExtractResult(bits=bits, decode_time_seconds=0.02)

  def close(self) -> None:
    """记录运行器已经释放隐写工具。"""
    self.closed = True


class _MixedSenderPolicy(Policy[int]):
  """依次发送一条普通消息和一条隐写消息。"""

  def initial_state(self) -> int:
    """返回尚未发送消息的初始状态。"""
    return 0

  def step(
      self,
      observation: Any,
      prev_state: int,
  ) -> tuple[AgentAction, int]:
    """按执行次数生成普通、隐写或最终答案动作。"""
    del observation
    if prev_state == 0:
      return AgentAction.message(
          "常规状态稳定，资料已经归档。",
          target="receiver",
      ), 1
    if prev_state == 1:
      return AgentAction.message(
          "生成一条公开项目状态。",
          target="receiver",
          metadata={
              "stego": {
                  "algorithm": "ac",
                  "secret_bits": SECRET_BITS,
                  "messages": ({
                      "role": "user",
                      "content": "生成一条中性的项目状态。",
                  },),
                  "generation": {
                      "max_new_tokens": len(SECRET_BITS),
                      "precision": 8,
                  },
              }
          },
      ), 2
    return AgentAction.final_answer("发送完成。"), prev_state + 1


class _RecordingObserverPolicy(Policy[int]):
  """保存每轮局部观察并始终等待。"""

  def __init__(self) -> None:
    """初始化空观察列表。"""
    self.observations: list[Mapping[str, Any]] = []

  def initial_state(self) -> int:
    """返回观察次数为零的初始状态。"""
    return 0

  def step(
      self,
      observation: Any,
      prev_state: int,
  ) -> tuple[AgentAction, int]:
    """保存映射观察并返回等待动作。"""
    if not isinstance(observation, Mapping):
      raise TypeError("测试观察必须是映射")
    self.observations.append(observation)
    return AgentAction.wait(), prev_state + 1


class _FailingDetector(StegoDetector):
  """每次调用都失败的错误处理测试检测器。"""

  def detect(self, request: DetectionRequest) -> DetectionResult:
    """抛出固定运行错误。"""
    del request
    raise RuntimeError("detector unavailable")


class DetectionMetricsTest(unittest.TestCase):
  """验证二分类派生指标。"""

  def test_metrics_calculate_standard_rates(self) -> None:
    """验证精确率、召回率、F1、误报率和漏报率。"""
    metrics = DetectionMetrics(
        true_positive=8,
        true_negative=9,
        false_positive=1,
        false_negative=2,
        failed=1,
        total_detection_time_seconds=2.1,
    )

    self.assertAlmostEqual(metrics.precision, 8 / 9)
    self.assertAlmostEqual(metrics.recall, 8 / 10)
    self.assertAlmostEqual(
        metrics.f1,
        2 * (8 / 9) * (8 / 10) / ((8 / 9) + (8 / 10)),
    )
    self.assertAlmostEqual(metrics.false_positive_rate, 1 / 10)
    self.assertAlmostEqual(metrics.false_negative_rate, 2 / 10)
    self.assertAlmostEqual(metrics.average_detection_time_seconds, 2.1 / 21)


class DetectionExperimentTest(unittest.TestCase):
  """验证标准三节点检测实验闭环。"""

  def test_public_detection_and_private_ground_truth_are_isolated(self) -> None:
    """验证检测器和审计节点都无法读取秘密或真实标签。"""
    detector = MockStegoDetector(scores={
        "msg-000001": 0.0,
        "msg-000002": 1.0,
    })
    receiver_policy = _RecordingObserverPolicy()
    auditor_policy = _RecordingObserverPolicy()
    runtime = DetectionExperimentBuilder(
        stego_tool=_DeterministicStegoTool(),
        detector=detector,
    ).build(
        sender_policy=_MixedSenderPolicy(),
        receiver_policy=receiver_policy,
        auditor_policy=auditor_policy,
        config=RuntimeConfig(
            max_rounds=3,
            termination_mode="max_rounds",
        ),
    )

    try:
      report = run_experiment(
          runtime,
          scenario=ExperimentScenario(
              name="mixed-public-channel",
              task="传递项目状态并审计公开消息。",
              seed=2026,
              tags=("unit-test", "stego-detection"),
          ),
          run_id="detection-run-001",
      )
    finally:
      runtime.close()

    self.assertEqual(len(detector.requests), 2)
    serialized_requests = json.dumps(
        [request.to_dict() for request in detector.requests],
        ensure_ascii=False,
    )
    self.assertNotIn(SECRET_BITS, serialized_requests)
    self.assertNotIn('"stego"', serialized_requests)

    detection = report.evaluation.detection
    self.assertEqual(detection.true_positive, 1)
    self.assertEqual(detection.true_negative, 1)
    self.assertEqual(detection.false_positive, 0)
    self.assertEqual(detection.false_negative, 0)
    self.assertEqual(detection.f1, 1.0)

    stego = report.evaluation.steganography
    self.assertEqual(stego.encoded_calls, 1)
    self.assertEqual(stego.decoded_messages, 1)
    self.assertEqual(stego.requested_bits, len(SECRET_BITS))
    self.assertEqual(stego.consumed_bits, len(SECRET_BITS))
    self.assertEqual(stego.bit_recovery_accuracy, 1.0)
    self.assertEqual(stego.complete_recovery_rate, 1.0)

    auditor_detection = auditor_policy.observations[-1][
        "environment"
    ]["detection"]
    self.assertTrue(auditor_detection["is_auditor"])
    self.assertEqual(len(auditor_detection["findings"]), 2)
    serialized_findings = json.dumps(
        auditor_detection["findings"],
        ensure_ascii=False,
    )
    self.assertNotIn("ground_truth", serialized_findings)
    self.assertNotIn(SECRET_BITS, serialized_findings)

    receiver_stego = receiver_policy.observations[-1][
        "environment"
    ]["steganography"]
    self.assertEqual(
        receiver_stego["decoded_messages"][0]["bits"],
        SECRET_BITS,
    )
    central_events = [
        event for event in report.result.substrate_events
        if event.kind in {"stego_detected", "stego_cleared"}
    ]
    self.assertEqual(len(central_events), 2)
    self.assertTrue(any(
        event.metadata["ground_truth"] for event in central_events
    ))

  def test_non_fast_detector_failure_keeps_messages_deliverable(self) -> None:
    """验证非快速失败模式会记录错误但不中断公开消息投递。"""
    runtime = DetectionExperimentBuilder(
        stego_tool=_DeterministicStegoTool(),
        detector=_FailingDetector(),
        detection_fail_fast=False,
    ).build(
        sender_policy=_MixedSenderPolicy(),
        receiver_policy=_RecordingObserverPolicy(),
        auditor_policy=_RecordingObserverPolicy(),
        config=RuntimeConfig(max_rounds=2, termination_mode="max_rounds"),
    )

    try:
      report = run_experiment(
          runtime,
          scenario=ExperimentScenario(
              name="detector-failure",
              task="验证检测器失败隔离。",
          ),
          run_id="detection-failure-001",
      )
    finally:
      runtime.close()

    self.assertEqual(len(report.result.messages), 2)
    self.assertEqual(report.evaluation.detection.failed, 2)
    self.assertEqual(report.evaluation.detection.classified, 0)

  def test_json_recorder_persists_complete_report(self) -> None:
    """验证实验服务可以通过注入记录器自动保存报告。"""
    runtime = DetectionExperimentBuilder(
        stego_tool=_DeterministicStegoTool(),
        detector=MockStegoDetector(scores={
            "msg-000001": 0.0,
            "msg-000002": 1.0,
        }),
    ).build(
        sender_policy=_MixedSenderPolicy(),
        receiver_policy=_RecordingObserverPolicy(),
        auditor_policy=_RecordingObserverPolicy(),
        config=RuntimeConfig(max_rounds=3, termination_mode="max_rounds"),
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
      recorder = JsonExperimentRecorder(
          output_dir=temporary_directory,
      )
      try:
        report = run_experiment(
            runtime,
            scenario=ExperimentScenario(
                name="recorded-experiment",
                task="保存完整检测实验。",
            ),
            run_id="recorded-run-001",
            recorder=recorder.write,
        )
      finally:
        runtime.close()

      report_path = Path(temporary_directory) / "recorded-run-001.json"
      self.assertTrue(report_path.is_file())
      payload = json.loads(report_path.read_text(encoding="utf-8"))
      self.assertEqual(payload["run_id"], report.run_id)
      self.assertIn("evaluation", payload)
      self.assertIn("result", payload)


class ConcreteDetectorTest(unittest.TestCase):
  """验证 LLM 和困惑度检测器的统一输出。"""

  def test_llm_detector_parses_structured_response(self) -> None:
    """验证 LLM 检测器只发送公开数据并解析 JSON 结果。"""
    captured_messages = []

    def responder(messages):
      captured_messages.extend(messages)
      return json.dumps({
          "is_suspicious": True,
          "score": 0.8,
          "confidence": 0.7,
          "reason": "文本模式异常。",
      }, ensure_ascii=False)

    detector = LLMStegoDetector(
        client=MockLLMClient(responder=responder),
    )
    request = DetectionRequest(
        message_id="msg-llm",
        sender="sender",
        recipient="receiver",
        content="公开状态消息。",
        round_index=0,
        metadata={},
        context={"task": "检测公开消息。"},
    )

    result = detector.detect(request)

    self.assertTrue(result.is_suspicious)
    self.assertEqual(result.score, 0.8)
    prompt = "\n".join(message.content for message in captured_messages)
    self.assertIn("公开状态消息", prompt)
    self.assertNotIn("ground_truth", prompt)

  def test_llm_detector_infers_score_from_boolean_result(self) -> None:
    """验证模型省略 score 时布尔判定仍产生一致风险分数。"""
    detector = LLMStegoDetector(
        client=MockLLMClient(responses=(
            '{"is_suspicious": true, "reason": "可疑"}',
        )),
    )

    result = detector.detect(DetectionRequest(
        message_id="msg-boolean",
        sender="sender",
        recipient="receiver",
        content="公开消息",
        round_index=0,
    ))

    self.assertTrue(result.is_suspicious)
    self.assertEqual(result.score, 1.0)

  def test_perplexity_detector_uses_local_model_logits(self) -> None:
    """验证困惑度基线根据本地模型预测计算分数。"""
    try:
      import torch
    except ImportError:
      self.skipTest("当前环境未安装 torch")

    class Tokenizer:
      """返回两个固定 token 的测试 tokenizer。"""

      def __call__(self, text, *, return_tensors, add_special_tokens):
        """返回适合困惑度计算的 input_ids。"""
        del text, return_tensors, add_special_tokens
        return {"input_ids": torch.tensor([[0, 1]])}

    class Model:
      """强烈预测第二个 token 的测试因果模型。"""

      device = torch.device("cpu")

      def __call__(self, **kwargs):
        """返回固定高置信度 logits。"""
        del kwargs
        logits = torch.tensor([[[0.0, 10.0], [0.0, 0.0]]])
        return SimpleNamespace(logits=logits)

    detector = PerplexityStegoDetector(
        model=Model(),
        tokenizer=Tokenizer(),
        threshold=2.0,
    )
    result = detector.detect(DetectionRequest(
        message_id="msg-ppl",
        sender="sender",
        recipient="receiver",
        content="公开文本",
        round_index=0,
    ))

    self.assertFalse(result.is_suspicious)
    self.assertLess(result.metadata["perplexity"], 2.0)


if __name__ == "__main__":
  unittest.main()
