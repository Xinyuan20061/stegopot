"""最小评估运行循环。"""

from __future__ import annotations

from typing import Any

from meltingpot.utils.scenarios import population as population_lib
from meltingpot.utils.substrates import substrate as substrate_lib


def run_episode(
    population: population_lib.Population,
    substrate: substrate_lib.Substrate,
    *,
    max_steps: int | None = None,
) -> list[substrate_lib.StepResult]:
  """运行一个回合，并返回收集到的步骤结果。

  参数：
    population: 参与当前回合的智能体群体。
    substrate: 提供交互规则和状态转移的环境基底。
    max_steps: 最大推进步数；为空时直到环境返回 done。

  返回：
    从 reset 开始收集到的所有步骤结果。
  """
  population.reset()
  result = substrate.reset()
  results = [result]
  steps = 0
  while not result.done:
    if max_steps is not None and steps >= max_steps:
      break
    actions: Any = population.step(result.observations)
    result = substrate.step(actions)
    results.append(result)
    steps += 1
  return results
