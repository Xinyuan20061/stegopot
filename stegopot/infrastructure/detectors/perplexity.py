"""基于本地因果语言模型困惑度的隐写检测基线。"""

from __future__ import annotations

import math
from typing import Any

from stegopot.domain.interface import StegoDetector
from stegopot.domain.model import DetectionRequest
from stegopot.domain.model import DetectionResult


class PerplexityStegoDetector(StegoDetector):
  """把高于阈值的公开文本困惑度视为可疑信号。

  困惑度只能反映文本在指定参考模型下的异常程度，不能证明文本包含隐写
  内容。本类只提供可复现基线，阈值应使用独立普通文本集进行校准。
  """

  def __init__(
      self,
      *,
      model: Any,
      tokenizer: Any,
      threshold: float,
      detector_id: str = "perplexity-baseline",
  ) -> None:
    """初始化困惑度检测器。

    参数：
      model: 返回 logits 的本地 Transformers 因果语言模型。
      tokenizer: 与 model 匹配、可把文本转换为 input_ids 的 tokenizer。
      threshold: 达到或超过该困惑度时判定消息可疑。
      detector_id: 写入 DetectionResult 的检测器 ID。
    """
    if model is None:
      raise ValueError("model 不能为空")
    if tokenizer is None:
      raise ValueError("tokenizer 不能为空")
    if not math.isfinite(float(threshold)) or float(threshold) <= 0:
      raise ValueError("threshold 必须是大于 0 的有限数值")
    if not isinstance(detector_id, str) or not detector_id.strip():
      raise ValueError("detector_id 必须是非空字符串")
    self._model = model
    self._tokenizer = tokenizer
    self._threshold = float(threshold)
    self._detector_id = detector_id.strip()

  def detect(self, request: DetectionRequest) -> DetectionResult:
    """计算公开文本困惑度并与阈值比较。

    参数：
      request: 当前公开消息检测请求。

    返回：
      包含原始困惑度、归一化风险分数和阈值判定的结果。
    """
    perplexity = self._calculate_perplexity(request.content)
    is_suspicious = perplexity >= self._threshold
    score = min(1.0, perplexity / (2.0 * self._threshold))
    confidence = min(
        1.0,
        abs(perplexity - self._threshold) / self._threshold,
    )
    return DetectionResult(
        message_id=request.message_id,
        detector_id=self._detector_id,
        is_suspicious=is_suspicious,
        score=score,
        confidence=confidence,
        reason=(
            f"文本困惑度 {perplexity:.4f}，"
            f"检测阈值 {self._threshold:.4f}。"
        ),
        metadata={
            "perplexity": perplexity,
            "threshold": self._threshold,
        },
    )

  def _calculate_perplexity(self, text: str) -> float:
    """使用本地模型计算去除最后位置后的自回归困惑度。"""
    try:
      import torch
      import torch.nn.functional as torch_functional
    except ImportError as exc:
      raise RuntimeError(
          "PerplexityStegoDetector 需要安装 torch"
      ) from exc

    encoded = self._tokenizer(
        text,
        return_tensors="pt",
        add_special_tokens=False,
    )
    if "input_ids" not in encoded:
      raise ValueError("tokenizer 返回结果缺少 input_ids")
    device = getattr(self._model, "device", None)
    input_ids = encoded["input_ids"]
    if device is not None:
      input_ids = input_ids.to(device)
    if input_ids.shape[-1] < 2:
      return 1.0

    model_arguments = {"input_ids": input_ids}
    attention_mask = encoded.get("attention_mask")
    if attention_mask is not None:
      if device is not None:
        attention_mask = attention_mask.to(device)
      model_arguments["attention_mask"] = attention_mask
    with torch.no_grad():
      output = self._model(**model_arguments)
      logits = output.logits[:, :-1, :]
      targets = input_ids[:, 1:]
      loss = torch_functional.cross_entropy(
          logits.reshape(-1, logits.shape[-1]),
          targets.reshape(-1),
      )
      perplexity = torch.exp(torch.clamp(loss, max=50.0)).item()
    return float(perplexity)
