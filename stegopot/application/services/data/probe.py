"""从通用 ActivationTrace 构造逐层 Probe 数据视图。"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from stegopot.domain.model.probe import ProbeDataset, ProbeExample, ProbeInputSpec
from stegopot.domain.model.reference import TensorRef
from stegopot.domain.model.trace import ActivationTrace, StoredTensorRef


def build_probe_dataset(
    traces: Mapping[str, ActivationTrace],
    labels: Mapping[str, Any],
    input_spec: ProbeInputSpec,
    *,
    split: str = "unspecified",
    tensor_loader: Callable[[StoredTensorRef], Any] | None = None,
) -> ProbeDataset:
  """把同一位置的激活和中央标签对齐成 ProbeDataset。"""
  if set(traces) != set(labels):
    raise ValueError("traces 与 labels 必须覆盖完全相同的 sample_id")
  examples = []
  for sample_id in sorted(traces):
    record = traces[sample_id].get(input_spec.ref)
    value = record.value
    if isinstance(value, StoredTensorRef):
      if tensor_loader is None:
        raise ValueError("磁盘轨迹必须显式提供 tensor_loader")
      value = tensor_loader(value)
    features = _pool(value, input_spec.pooling)
    examples.append(ProbeExample(
        sample_id, features, labels[sample_id],
        {"trace_run_id": traces[sample_id].run_id,
         "tensor_ref": input_spec.ref.key}))
  return ProbeDataset(input_spec, examples, split)


def build_layer_probe_datasets(
    traces: Mapping[str, ActivationTrace],
    labels: Mapping[str, Any],
    *,
    layers: Sequence[int],
    component: str,
    token: int | tuple[int | None, int | None] | None = -1,
    pooling: str = "none",
    split: str = "unspecified",
    tensor_loader: Callable[[StoredTensorRef], Any] | None = None,
) -> Mapping[int, ProbeDataset]:
  """为每个 layer 构造独立数据集，Probe 算法由外部插件决定。"""
  if not layers or len(set(layers)) != len(layers):
    raise ValueError("layers 必须非空且不能重复")
  result = {}
  for layer in layers:
    spec = ProbeInputSpec(
        TensorRef(layer=int(layer), component=component, token=token), pooling)
    result[int(layer)] = build_probe_dataset(
        traces, labels, spec, split=split, tensor_loader=tensor_loader)
  return result


def _pool(value: Any, pooling: str) -> Any:
  """使用张量对象自身的索引、mean 和 reshape 能力执行轻量池化。"""
  if pooling == "none":
    return value
  if pooling == "last_token":
    return value[..., -1, :] if getattr(value, "ndim", 0) >= 3 else value[-1]
  if pooling == "mean_tokens":
    axis = -2 if getattr(value, "ndim", 0) >= 2 else 0
    try:
      return value.mean(dim=axis)
    except TypeError:
      return value.mean(axis=axis)
  if pooling == "flatten":
    try:
      return value.reshape(-1)
    except AttributeError as exc:
      raise TypeError("flatten pooling 需要 reshape 能力") from exc
  raise ValueError(f"不支持的 pooling：{pooling}")
