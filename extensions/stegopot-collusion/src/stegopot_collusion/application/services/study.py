"""共谋样本规划；运行循环属于框架，插件只生成条件。"""

import random

from stegopot_collusion.domain.model.collusion import CHOICES, MARKERS, CollusionStudyConfig, CollusionTrial


def plan_cases(config: CollusionStudyConfig) -> tuple[CollusionTrial, ...]:
  """根据 config 创建均衡秘密标签和随机协议，不改变全局随机状态。"""
  rng = random.Random(config.seed)
  targets = list(CHOICES) * (config.cases // len(CHOICES))
  rng.shuffle(targets)
  trials = []
  for index, target in enumerate(targets):
    markers = list(MARKERS)
    rng.shuffle(markers)
    trials.append(CollusionTrial(
        case_id=f"case-{index + 1:03d}", condition="shared_codebook",
        private_target=target,
        public_target=rng.choice([choice for choice in CHOICES if choice != target]),
        codebook=dict(zip(CHOICES, markers))))
  return tuple(trials)
