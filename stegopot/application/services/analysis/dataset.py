"""将无标签研究观测与中央标签连接，并执行配对分组和泄漏审计。"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import random
from typing import Any

from stegopot.domain.model.localization import (
    CapturedObservation,
    DataKind,
    LocalizerDataset,
    LocalizerSample,
    SecretSpec,
)


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass(frozen=True)
class SplitConfig:
  """以 matched group 为最小单位的固定数据切分参数。"""

  train_ratio: float = field(default=0.6, metadata=_description("训练组比例。"))
  validation_ratio: float = field(default=0.2, metadata=_description("验证组比例。"))
  test_ratio: float = field(default=0.2, metadata=_description("测试组比例。"))
  seed: int = field(default=0, metadata=_description("确定性分组随机种子。"))

  def __post_init__(self) -> None:
    ratios = (float(self.train_ratio), float(self.validation_ratio), float(self.test_ratio))
    if any(value <= 0 for value in ratios) or abs(sum(ratios) - 1.0) > 1e-9:
      raise ValueError("train/validation/test 比例必须为正且总和为 1")
    if type(self.seed) is not int:
      raise TypeError("SplitConfig.seed 必须是整数")


@dataclass(frozen=True)
class DatasetSplit:
  """不共享 matched group 的训练、验证和测试样本。"""

  training: Sequence[LocalizerSample] = field(metadata=_description("训练样本。"))
  validation: Sequence[LocalizerSample] = field(metadata=_description("验证样本。"))
  test: Sequence[LocalizerSample] = field(metadata=_description("测试样本。"))
  group_assignment: Mapping[str, str] = field(metadata=_description("组 ID 到 split 的映射。"))

  def __post_init__(self) -> None:
    object.__setattr__(self, "training", tuple(self.training))
    object.__setattr__(self, "validation", tuple(self.validation))
    object.__setattr__(self, "test", tuple(self.test))
    object.__setattr__(self, "group_assignment", dict(self.group_assignment))
    sets = [{item.group_id for item in values}
            for values in (self.training, self.validation, self.test)]
    if sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2]:
      raise ValueError("train/validation/test 不能共享 matched group")
    if any(not values for values in (self.training, self.validation, self.test)):
      raise ValueError("三个 split 都必须包含样本")


@dataclass(frozen=True)
class LeakageAudit:
  """记录数据集构造阶段可机械检查的数据泄漏风险。"""

  passed: bool = field(metadata=_description("是否通过强制泄漏检查。"))
  checks: Mapping[str, bool] = field(metadata=_description("各检查项结果。"))
  warnings: Sequence[str] = field(metadata=_description("不能自动证明的风险说明。"))

  def to_dict(self) -> dict[str, Any]:
    """返回可写入分析清单的泄漏审计。"""
    return {"passed": self.passed, "checks": dict(self.checks),
            "warnings": list(self.warnings)}


def build_matched_datasets(
    observations: Sequence[CapturedObservation],
    *,
    secret: SecretSpec,
    labels: Mapping[str, str],
    matched_groups: Mapping[str, str],
    data_kind: DataKind,
    minimum_samples: int = 6,
) -> tuple[tuple[LocalizerDataset, ...], LeakageAudit]:
  """按稳定地址构造定位数据集。

  参数：
    observations: 不带真值的公开消息或表征观测。
    secret: 中央秘密声明。
    labels: sample_id 或无歧义 trial_id 到秘密标签的映射。
    matched_groups: sample_id 或无歧义 trial_id 到配对组的映射。
    data_kind: 观测值的数据形态。
    minimum_samples: 每个稳定地址至少需要的样本数。

  返回：
    地址级数据集及泄漏审计。秘密标签只存在于返回的离线数据集中。
  """
  if minimum_samples < 3:
    raise ValueError("minimum_samples 不能小于 3")
  if not observations:
    raise ValueError("没有可用于定位的观测")
  pairs = {(item.run_id, item.trial_id) for item in observations}
  trial_counts = Counter(trial_id for _, trial_id in pairs)
  grouped: dict[str, list[tuple[CapturedObservation, str, str]]] = defaultdict(list)
  forbidden_metadata = False
  for item in observations:
    forbidden_metadata = forbidden_metadata or _contains_forbidden_key(item.metadata)
    label = _lookup_central(labels, item, trial_counts, "labels")
    group_id = _lookup_central(matched_groups, item, trial_counts, "matched_groups")
    grouped[item.address.key].append((item, label, group_id))

  datasets = []
  context_controlled = True
  paired_groups = True
  for rows in grouped.values():
    if len(rows) < minimum_samples:
      continue
    samples = tuple(LocalizerSample(item.sample_id, group_id, label, item.value)
                    for item, label, group_id in rows)
    labels_present = {item.label for item in samples}
    expected = set(secret.classes)
    if expected and labels_present != expected:
      continue
    group_labels: dict[str, set[str]] = defaultdict(set)
    for sample in samples:
      group_labels[sample.group_id].add(sample.label)
    paired_groups = paired_groups and all(len(values) >= 2 for values in group_labels.values())
    fingerprints = {row.metadata.get("context_fingerprint") for row, _, _ in rows
                    if row.metadata.get("context_fingerprint") is not None}
    context_controlled = context_controlled and len(fingerprints) <= 1
    datasets.append(LocalizerDataset(secret, rows[0][0].address, data_kind, samples,
                                     {"context_fingerprints": len(fingerprints)}))
  if not datasets:
    raise ValueError("没有稳定地址同时满足样本数和秘密类别要求")
  checks = {
      "feature_metadata_excludes_truth": not forbidden_metadata,
      "matched_groups_contain_multiple_secrets": paired_groups,
      "context_fingerprint_controlled": context_controlled,
      "central_labels_joined_outside_features": True,
  }
  if not all(checks.values()):
    failures = ", ".join(name for name, passed in checks.items() if not passed)
    raise ValueError(f"数据泄漏审计失败：{failures}")
  audit = LeakageAudit(True, checks, (
      "trial ID 与秘密的语义相关性、任务模板差异和潜在公共基线仍需研究者复核。",
  ))
  return tuple(sorted(datasets, key=lambda item: item.address.key)), audit


def split_dataset(dataset: LocalizerDataset, config: SplitConfig) -> DatasetSplit:
  """以 matched group 为单位做确定性切分，杜绝配对样本跨 split。"""
  groups = sorted({item.group_id for item in dataset.samples})
  if len(groups) < 3:
    raise ValueError("至少需要 3 个 matched group 才能形成 train/validation/test")
  random.Random(config.seed).shuffle(groups)
  train_count = max(1, int(len(groups) * config.train_ratio))
  validation_count = max(1, int(len(groups) * config.validation_ratio))
  if train_count + validation_count >= len(groups):
    train_count = len(groups) - validation_count - 1
  if train_count < 1:
    raise ValueError("matched group 数量不足以满足切分比例")
  assignment = {}
  for index, group_id in enumerate(groups):
    split = ("train" if index < train_count else
             "validation" if index < train_count + validation_count else "test")
    assignment[group_id] = split
  values = {name: [] for name in ("train", "validation", "test")}
  for item in dataset.samples:
    values[assignment[item.group_id]].append(item)
  result = DatasetSplit(values["train"], values["validation"], values["test"], assignment)
  train_labels = {item.label for item in result.training}
  all_labels = {item.label for item in dataset.samples}
  if train_labels != all_labels:
    raise ValueError("训练 split 未覆盖全部秘密类别；请增加配对组或调整组设计")
  return result


def _lookup_central(
    values: Mapping[str, str],
    item: CapturedObservation,
    trial_counts: Mapping[str, int],
    name: str,
) -> str:
  """优先按 run:trial 连接中央数据，仅在 trial ID 无歧义时允许短键。"""
  value = values.get(item.sample_id)
  if value is None and trial_counts[item.trial_id] == 1:
    value = values.get(item.trial_id)
  if not isinstance(value, str) or not value.strip():
    raise ValueError(f"{name} 缺少样本 {item.sample_id}")
  return value.strip()


def _contains_forbidden_key(value: Any) -> bool:
  """拒绝把中央真值伪装进 feature metadata。"""
  forbidden = {"secret", "secret_bits", "truth", "label", "target_label"}
  if isinstance(value, Mapping):
    return any(str(key).lower() in forbidden or _contains_forbidden_key(item)
               for key, item in value.items())
  if isinstance(value, (list, tuple)):
    return any(_contains_forbidden_key(item) for item in value)
  return False

