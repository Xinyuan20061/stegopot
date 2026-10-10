"""Source -> Transform -> Validate -> Split -> Store 数据流水线。"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
import hashlib
import json
import random

from stegopot.domain.interface.data import (
    DatasetSource,
    DatasetStore,
    DatasetTransform,
    DatasetValidator,
)
from stegopot.domain.model.context import ExperimentContext
from stegopot.domain.model.data import DatasetBundle, Sample, SplitPolicy


class DatasetPipeline:
  """编排通用样本生成，不解释 input、target 或 metadata 语义。"""

  def __init__(
      self, *, source: DatasetSource,
      transforms: Sequence[DatasetTransform] = (),
      validators: Sequence[DatasetValidator] = (),
      split: SplitPolicy = SplitPolicy(),
      store: DatasetStore | None = None,
  ) -> None:
    """注入数据源、转换、验证、切分和可选存储实现。"""
    self.source = source
    self.transforms = tuple(transforms)
    self.validators = tuple(validators)
    self.split = split
    self.store = store

  def prepare(self, count: int, context: ExperimentContext) -> DatasetBundle:
    """生成 count 个源样本并返回确定性切分的数据集。"""
    if type(count) is not int or count < 1:
      raise ValueError("count 必须是正整数")
    source_values = tuple(self.source.generate(count, context))
    if len(source_values) > count:
      raise ValueError("DatasetSource 生成数量超过请求上限")
    values = []
    for source in source_values:
      if not isinstance(source, Sample):
        raise TypeError("DatasetSource 只能产生 Sample")
      current = (source,)
      for transform in self.transforms:
        transformed = []
        for sample in current:
          transformed.extend(transform.apply(sample, context))
        if any(not isinstance(item, Sample) for item in transformed):
          raise TypeError("DatasetTransform 只能返回 Sample")
        current = tuple(transformed)
      values.extend(current)
    if not values:
      raise ValueError("数据流水线没有生成有效样本")
    identifiers = [item.sample_id for item in values]
    if len(set(identifiers)) != len(identifiers):
      raise ValueError("数据流水线生成了重复 sample_id")
    failures = {}
    for sample in values:
      errors = [message for validator in self.validators
                for message in validator.validate(sample, context)]
      if errors:
        failures[sample.sample_id] = tuple(str(item) for item in errors)
    if failures:
      sample_id = sorted(failures)[0]
      raise ValueError(f"样本 {sample_id} 未通过验证：{'; '.join(failures[sample_id])}")
    train, validation, test = _split(values, self.split)
    fingerprint = _fingerprint(
        values, self.source.source_id,
        [item.transform_id for item in self.transforms],
        [item.validator_id for item in self.validators], self.split)
    bundle = DatasetBundle(
        dataset_id=f"dataset-{fingerprint[:16]}", train=train,
        validation=validation, test=test, fingerprint=fingerprint,
        metadata={"source": self.source.source_id,
                  "transforms": [item.transform_id for item in self.transforms],
                  "validators": [item.validator_id for item in self.validators]})
    if self.store is not None:
      self.store.write(bundle, context)
    return bundle


def _split(values: Sequence[Sample], policy: SplitPolicy):
  """按可选分组键执行确定性切分。"""
  groups = defaultdict(list)
  for sample in values:
    key = sample.metadata.get(policy.group_key) if policy.group_key else sample.sample_id
    if key is None:
      raise ValueError(f"样本 {sample.sample_id} 缺少分组字段 {policy.group_key}")
    groups[str(key)].append(sample)
  keys = sorted(groups)
  random.Random(policy.seed).shuffle(keys)
  total = len(keys)
  train_end = round(total * policy.train_ratio)
  validation_end = train_end + round(total * policy.validation_ratio)
  partitions = (keys[:train_end], keys[train_end:validation_end], keys[validation_end:])
  return tuple(tuple(sample for key in keys_for_split for sample in groups[key])
               for keys_for_split in partitions)


def _fingerprint(values, source_id, transforms, validators, policy):
  """根据稳定 ID、流水线版本和切分参数生成 SHA-256。"""
  payload = {
      "samples": sorted(item.sample_id for item in values),
      "source": source_id, "transforms": transforms, "validators": validators,
      "split": {"train": policy.train_ratio, "validation": policy.validation_ratio,
                "test": policy.test_ratio, "seed": policy.seed,
                "group_key": policy.group_key},
  }
  return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
