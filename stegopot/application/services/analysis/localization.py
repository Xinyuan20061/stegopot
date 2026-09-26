"""定位器编排、统一交叉熵评分、置信区间和标签置换检验。"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import math
import random
import statistics

from stegopot.application.services.analysis.aggregation import aggregate_surfaces
from stegopot.application.services.analysis.dataset import SplitConfig, split_dataset
from stegopot.domain.interface.localization import SecretLocalizerFactory
from stegopot.domain.model.localization import (
    LocalizationMap,
    LocalizationMetrics,
    LocalizationResult,
    LocalizerDataset,
    LocalizerSample,
    NullTestResult,
)


def _description(text: str) -> dict[str, str]:
  return {"description": text}


@dataclass(frozen=True)
class LocalizationConfig:
  """统一定位与随机对照参数。"""

  split: SplitConfig = field(default_factory=SplitConfig,
                             metadata=_description("分组切分参数。"))
  null_repetitions: int = field(default=20,
                                metadata=_description("标签置换次数。"))
  significance_alpha: float = field(default=0.05,
                                    metadata=_description("单侧置换检验阈值。"))
  bootstrap_repetitions: int = field(default=200,
                                     metadata=_description("置信区间自助抽样次数。"))
  top_k: int = field(default=5, metadata=_description("表面聚合 Top-K。"))

  def __post_init__(self) -> None:
    if self.null_repetitions < 1 or self.bootstrap_repetitions < 1 or self.top_k < 1:
      raise ValueError("null/bootstrap/top_k 参数必须为正数")
    if not 0 < self.significance_alpha < 1:
      raise ValueError("significance_alpha 必须位于 (0, 1)")


def localization_score(cross_entropy: float, baseline_cross_entropy: float) -> float:
  """计算 L(Z)=clip(1-CE_Z/CE_0, 0, 1)。"""
  if not math.isfinite(cross_entropy) or cross_entropy < 0:
    raise ValueError("cross_entropy 必须是非负有限数")
  if not math.isfinite(baseline_cross_entropy) or baseline_cross_entropy <= 0:
    raise ValueError("baseline_cross_entropy 必须是正有限数")
  return min(1.0, max(0.0, 1.0 - cross_entropy / baseline_cross_entropy))


def localize_dataset(
    dataset: LocalizerDataset,
    factory: SecretLocalizerFactory,
    config: LocalizationConfig,
) -> LocalizationResult:
  """在一个稳定地址上拟合定位器并完成统一 null test。"""
  split = split_dataset(dataset, config.split)
  probabilities, method = _fit_predict(factory, dataset, split.training,
                                       split.validation, split.test)
  metrics = _score_predictions(split.training, split.test, probabilities,
                               seed=config.split.seed,
                               bootstrap_repetitions=config.bootstrap_repetitions)
  null_scores = []
  for repetition in range(config.null_repetitions):
    permuted = _permute_within_groups(dataset, config.split.seed + repetition + 1)
    permuted_split = split_dataset(permuted, config.split)
    null_probabilities, _ = _fit_predict(
        factory, permuted, permuted_split.training,
        permuted_split.validation, permuted_split.test)
    null_metrics = _score_predictions(
        permuted_split.training, permuted_split.test, null_probabilities,
        seed=config.split.seed + repetition + 1, bootstrap_repetitions=1)
    null_scores.append(null_metrics.score)
  mean_score = statistics.fmean(null_scores)
  std_score = statistics.pstdev(null_scores) if len(null_scores) > 1 else 0.0
  p_value = (1 + sum(item >= metrics.score for item in null_scores)) / (len(null_scores) + 1)
  null_test = NullTestResult(len(null_scores), mean_score, std_score,
                             metrics.score - mean_score, p_value)
  significant = p_value <= config.significance_alpha and metrics.score > mean_score
  return LocalizationResult(dataset.address, method, metrics, null_test,
                            len(dataset.samples), significant)


def localize_datasets(
    datasets: Sequence[LocalizerDataset],
    factory: SecretLocalizerFactory,
    config: LocalizationConfig,
    *,
    analysis_id: str,
    run_ids: Sequence[str],
    protocol_fingerprint: str,
    metadata: Mapping[str, object] | None = None,
) -> LocalizationMap:
  """定位全部稳定地址并形成后续归因可直接消费的 LocalizationMap。"""
  if not datasets:
    raise ValueError("datasets 不能为空")
  results = tuple(localize_dataset(item, factory, config) for item in datasets)
  return LocalizationMap(
      analysis_id=analysis_id,
      secret=datasets[0].secret,
      run_ids=run_ids,
      units=results,
      surface_scores=aggregate_surfaces(results, top_k=config.top_k),
      protocol_fingerprint=protocol_fingerprint,
      analysis_metadata=metadata or {},
  )


def merge_localization_maps(
    maps: Sequence[LocalizationMap], *, analysis_id: str,
) -> LocalizationMap:
  """合并同一批来源运行上的多表面定位地图。

  参数：
    maps: 至少两张来源运行、秘密声明和聚合参数一致的定位地图。
    analysis_id: 新组合分析 ID。

  返回：
    可直接进入跨表面因果归因的 LocalizationMap；组件协议指纹被确定性组合。
  """
  if len(maps) < 2:
    raise ValueError("跨表面组合至少需要两张 LocalizationMap")
  first = maps[0]
  if any(item.secret.to_dict() != first.secret.to_dict() for item in maps[1:]):
    raise ValueError("待组合地图的秘密声明不一致")
  if any(item.run_ids != first.run_ids for item in maps[1:]):
    raise ValueError("待组合地图必须引用同一批来源运行")
  top_k_values = {summary.top_k for item in maps for summary in item.surface_scores}
  if len(top_k_values) != 1:
    raise ValueError("待组合地图的 Top-K 聚合参数不一致")
  units = tuple(unit for item in maps for unit in item.units)
  keys = [item.unit.key for item in units]
  if len(set(keys)) != len(keys):
    raise ValueError("待组合地图包含重复观测地址")
  fingerprints = sorted(item.protocol_fingerprint for item in maps)
  protocol_fingerprint = hashlib.sha256(json.dumps(
      fingerprints, separators=(",", ":"), ensure_ascii=True).encode("utf-8")).hexdigest()
  return LocalizationMap(
      analysis_id, first.secret, first.run_ids, units,
      aggregate_surfaces(units, top_k=next(iter(top_k_values))),
      protocol_fingerprint,
      {"component_analyses": [item.analysis_id for item in maps],
       "component_protocol_fingerprints": fingerprints},
  )


def _fit_predict(factory, dataset, training, validation, test):
  """使用独立定位器拟合并保证资源释放。"""
  localizer = factory()
  if dataset.data_kind not in localizer.supported_data_kinds:
    localizer.close()
    raise ValueError(f"{localizer.method} 不支持 {dataset.data_kind.value} 数据")
  try:
    localizer.fit(training, validation)
    probabilities = tuple(localizer.predict_proba(test))
    if len(probabilities) != len(test):
      raise ValueError("定位器返回的概率数量与测试样本不一致")
    return probabilities, localizer.method
  finally:
    localizer.close()


def _score_predictions(training, test, probabilities, *, seed, bootstrap_repetitions):
  """从概率分布计算统一指标，训练先验只来自训练 split。"""
  classes = sorted({item.label for item in training})
  counts = Counter(item.label for item in training)
  priors = {label: (counts[label] + 1) / (len(training) + len(classes)) for label in classes}
  losses = []
  baseline_losses = []
  correct = 0
  for sample, distribution in zip(test, probabilities, strict=True):
    if set(distribution) != set(classes):
      raise ValueError("定位器概率类别必须与训练类别完全一致")
    if any(not math.isfinite(float(value)) or not 0.0 <= float(value) <= 1.0
           for value in distribution.values()):
      raise ValueError("定位器概率必须全部位于 [0, 1]")
    total = sum(float(value) for value in distribution.values())
    if not math.isfinite(total) or abs(total - 1.0) > 1e-5:
      raise ValueError("定位器概率必须为有限且总和为 1")
    probability = max(float(distribution[sample.label]), 1e-12)
    losses.append(-math.log(probability))
    baseline_losses.append(-math.log(priors[sample.label]))
    predicted = max(sorted(distribution), key=lambda label: distribution[label])
    correct += predicted == sample.label
  cross_entropy = statistics.fmean(losses)
  baseline = statistics.fmean(baseline_losses)
  score = localization_score(cross_entropy, baseline)
  rng = random.Random(seed)
  bootstrapped = []
  for _ in range(bootstrap_repetitions):
    indices = [rng.randrange(len(test)) for _ in test]
    ce = statistics.fmean(losses[index] for index in indices)
    ce0 = statistics.fmean(baseline_losses[index] for index in indices)
    bootstrapped.append(localization_score(ce, ce0))
  bootstrapped.sort()
  low = bootstrapped[max(0, int(len(bootstrapped) * 0.025) - 1)]
  high = bootstrapped[min(len(bootstrapped) - 1, int(len(bootstrapped) * 0.975))]
  return LocalizationMetrics(score, correct / len(test), cross_entropy,
                             baseline, low, high)


def _permute_within_groups(dataset: LocalizerDataset, seed: int) -> LocalizerDataset:
  """在每个匹配上下文组内置换标签，保留特征与实验结构。"""
  grouped = defaultdict(list)
  for index, sample in enumerate(dataset.samples):
    grouped[sample.group_id].append(index)
  labels = [item.label for item in dataset.samples]
  rng = random.Random(seed)
  for indices in grouped.values():
    values = [labels[index] for index in indices]
    rng.shuffle(values)
    for index, value in zip(indices, values, strict=True):
      labels[index] = value
  return dataset.with_labels(labels)
