"""公开 SAE 的重构质量与稀疏度测量。"""

from typing import Any

from stegopot.domain.interface.sae import SAEModel
from stegopot.domain.model.sae import SAEReconstructionReport


def evaluate_reconstruction(
    sae: SAEModel, activation: Any, *, epsilon: float = 1e-12,
) -> SAEReconstructionReport:
  """计算一批激活的基础 SAE 质量指标。

  参数：
    sae: 已加载且与激活位置兼容的 SAE。
    activation: 最后一维等于 SAE 输入宽度的 PyTorch 张量。
    epsilon: 相对误差和余弦相似度分母的最小稳定值。
  """
  if epsilon <= 0:
    raise ValueError("epsilon 必须大于零")
  torch = _torch()
  if not torch.is_tensor(activation):
    raise TypeError("activation 必须是 PyTorch 张量")
  with torch.no_grad():
    features = sae.encode(activation)
    reconstructed = sae.decode(features).to(
        device=activation.device, dtype=torch.float32)
    original = activation.detach().to(dtype=torch.float32)
    error = original - reconstructed
    mse = error.square().mean()
    reference_power = original.square().mean().clamp_min(epsilon)
    relative_mse = mse / reference_power
    original_flat = original.reshape(-1)
    reconstructed_flat = reconstructed.reshape(-1)
    cosine = torch.nn.functional.cosine_similarity(
        original_flat.unsqueeze(0), reconstructed_flat.unsqueeze(0),
        dim=-1, eps=epsilon).item()
    variance = original.var(unbiased=False)
    explained = None
    if variance.item() > epsilon:
      explained = (1.0 - error.var(unbiased=False) / variance).item()
    l0 = (features.detach() != 0).sum(dim=-1).to(torch.float32).mean().item()
  return SAEReconstructionReport(
      mse=mse.item(), relative_mse=relative_mse.item(),
      cosine_similarity=cosine, explained_variance=explained,
      mean_l0=l0, feature_density=l0 / sae.manifest.feature_width)


def _torch() -> Any:
  """延迟导入 PyTorch，保持基础安装轻量。"""
  try:
    import torch
  except ImportError as exc:
    raise RuntimeError("测量 SAE 需要安装 stegopot[sae]") from exc
  return torch
