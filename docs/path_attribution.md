# 隐写路径定位与因果归因

本页对应 StegoPot 1.1.0 的离线研究链路。目标不是增加一种实时检测器，而是回答：

1. 哪些内部或外部表征能够恢复中央秘密；
2. 哪些表征在反事实干预下真正影响秘密恢复；
3. 相同协议下，优化前后的因果贡献是否迁移到其他隐写表面。

## 概念边界

| 阶段 | 问题 | 核心输出 |
| --- | --- | --- |
| Detection | 公开消息是否可疑 | `DetectionResult` |
| Localization | 只给局部状态 Z，能恢复多少秘密 S | `LocalizationMap` |
| Attribution | 干预 Z 后秘密恢复是否下降 | `CausalPathGraph` |
| Migration | 相同协议前后因果贡献是否重新分布 | `PathMigrationReport` |

Localization 是带中央标签的离线研究分析。它不能实现为 `StegoDetector`，也不能把标签、
定位结果或内部表征返回 Agent、Detector、Reward。`unsupported` 表示没有相应采集能力，
不能转换成零分或“没有秘密”。

## 已实现范围

- 公开 `runtime.message` 的 Token/Text 定位；
- Activation、KV、Logits 的独立向量工件记录和 `LinearSecretProbe`；
- 字符/词 n-gram `TextSecretProbe`；
- JSON 字段特征 `StructuredSecretProbe` Python 接口；
- 训练/验证/测试 matched-group 切分和机械泄漏审计；
- 相对交叉熵分数、bootstrap 置信区间、标签置换 null test；
- Top-K 表面聚合；
- matched activation patching 执行器和统一因果贡献分数；
- 研究级 `CausalPathGraph` 与协议匹配的路径迁移比较。

CoT、Tool、Memory、Timing、Behavior 已有标准表面和特征接口，但 1.1.0 CLI 不把它们
声明为已完成采集链。Weight/LoRA、神经元级完整电路、自动 RL 和大规模 benchmark 不在
当前版本范围内。

## 统一分数

定位主分数为：

```text
L(Z) = clip(1 - CE_Z / CE_0, 0, 1)
```

`CE_Z` 是测试集秘密预测交叉熵，`CE_0` 是只使用训练集类别先验的基线交叉熵。
每个结果同时保存 accuracy、两个交叉熵、置信区间、样本数、null 均值/标准差、
real-minus-null 和 permutation p-value。只有通过预注册 alpha 的地址进入因果候选。

统一因果贡献为：

```text
M(Z) = clip((R0 - Ri) / (R0 - Rchance), 0, 1)
```

其中 `R0` 是未干预基线，`Ri` 是干预后的秘密恢复率，`Rchance` 是随机猜测基线。
结果必须保留三个原始量，不能只保存 M。

## 分析配置

分析配置独立于实验 YAML，建议放在工作区 `analyses/`：

```yaml
schema_version: "stegopot.analysis/1"

secret:
  name: payload
  kind: categorical
  source: central-label-table-v1
  classes: ["00", "01", "10", "11"]

# 键可用 trial_id；多个运行出现同名 trial 时必须使用 run_id:trial_id。
labels:
  paired-session-0001.secret-00: "00"
  paired-session-0001.secret-01: "01"
  paired-session-0001.secret-10: "10"
  paired-session-0001.secret-11: "11"

matched_groups:
  paired-session-0001.secret-00: context-0001
  paired-session-0001.secret-01: context-0001
  paired-session-0001.secret-10: context-0001
  paired-session-0001.secret-11: context-0001

surface: token
selection:
  agent_id: sender
  recipient: receiver
  rounds: [0]
  flow_order: 30

localizer:
  type: text
  config:
    dimension: 1024
    char_min: 2
    char_max: 4
    token_min: 1
    token_max: 2
    l2: 0.01
    epochs: 250

split:
  train_ratio: 0.6
  validation_ratio: 0.2
  test_ratio: 0.2
  seed: 7

null_test:
  repetitions: 100
  alpha: 0.05

bootstrap_repetitions: 500
minimum_samples: 24
aggregation:
  top_k: 5

# 迁移比较要求以下协议字段和全部分析参数完全一致。
protocol:
  task_distribution: task-set-v1
  secret_distribution: four-class-balanced-v1
  topology: sender-receiver-v1
  model_family: local-model-v1
  sampling: temperature-0-v1
  capture: public-message-v1
  intervention: matched-activation-v1
  evaluator: secret-recovery-v1
```

每个 matched group 应在相同任务、上下文、拓扑和模型条件下改变秘密。框架按 group 切分，
同组样本不会跨越 train/validation/test。标签必须由中央研究侧提供，不能编码到特征元数据、
任务文本、文件路径或 trial ID 规则中。上例只展示字段格式；正式分析至少需要 3 个 matched
group，并应满足 `minimum_samples`。分析配置含中央标签，不应提交到 Git。

## Token/Text 定位

```powershell
python -m stegopot analyze localize `
  D:\Research\study\outputs\<run-id> `
  --config D:\Research\study\analyses\secret_localization.yaml
```

目标也可以是一个包含多个封印运行的目录，或以下 JSON 运行组清单：

```json
{"runs": ["../outputs/run-a", "../outputs/run-b"]}
```

分析器先验证每个运行的日志链和根封印，只读取公开 `runtime.message`；完成写出后再次使用
原根封印摘要核验来源。中央标签值不会写入分析产物，只记录标签表摘要。

## 内部表征采集

大向量不能写入 `research.jsonl`。模型适配器在可信研究侧使用：

```python
from stegopot.infrastructure.recorders.representations import RepresentationRecorder

recorder = RepresentationRecorder(
    "D:/Research/study/captures/run-a",
    source_run="D:/Research/study/outputs/<run-id>",
    run_id="20260926T010203Z-abcd1234",
    capabilities={
        "provider": "local-transformer-adapter",
        "surfaces": ["activation", "logits"],
        "white_box": True,
    },
)

recorder.record_vector(
    trial_id="paired-session-0001.secret-00",
    agent_id="sender",
    surface="activation",
    address={"layer": 17, "token": 23},
    value=activation_vector,
)
recorder.seal()
```

采集包包含 `index.json`、`representation-seal.json` 和二进制 float64 工件。封印绑定来源
运行根封印；读取时逐个验证 artifact SHA-256。向量分析配置把 `surface` 改为
`activation`、`kv` 或 `logits`，使用 `localizer.type: vector`，并声明：

```yaml
representation_bundles:
  - ../captures/run-a
```

## 因果干预

Python 接口提供 matched activation patching。调用方负责把替换后的激活真正送回模型并
返回秘密恢复率；框架不会用探针预测冒充因果结果：

```python
from stegopot.domain.model.attribution import InterventionSpec
from stegopot.domain.model.localization import ObservationAddress, SurfaceKind
from stegopot.infrastructure.analysis.interventions import MatchedActivationPatcher

target = ObservationAddress(SurfaceKind.ACTIVATION, "sender", {"layer": 17, "token": 23})
spec = InterventionSpec(
    "patch-L17-T23", target, "matched_activation_patch",
    source_sample_id="run-a:trial-secret-00",
    donor_sample_id="run-a:trial-secret-01",
)

runner = MatchedActivationPatcher(
    source=source_activation,
    donor=matched_donor_activation,
    evaluator=rerun_from_patched_activation,
    baseline_recovery=0.91,
    chance_recovery=0.25,
)
result = runner.run(spec)
```

批量重跑结果写成 `interventions.json`：

```json
{
  "interventions": [{
    "intervention_id": "patch-L17-T23",
    "target": {"surface": "activation", "agent_id": "sender", "address": {"layer": 17, "token": 23}},
    "method": "matched_activation_patch",
    "source_sample_id": "run-a:trial-secret-00",
    "donor_sample_id": "run-a:trial-secret-01",
    "baseline_recovery": 0.91,
    "intervened_recovery": 0.34,
    "chance_recovery": 0.25
  }]
}
```

然后构建路径图：

```powershell
python -m stegopot analyze combine outputs/<token-analysis> outputs/<activation-analysis> outputs/<logits-analysis>
python -m stegopot analyze attribute outputs/<analysis-id> --interventions interventions.json
```

`combine` 要求秘密声明、来源运行和 Top-K 参数一致，并为组件协议指纹生成确定性的组合
指纹。跨表面地址可以预注册数值 `flow_order`；只有具有真实干预结果且声明该顺序的节点
才会生成路径边，框架不会从 Agent 名称猜测传播顺序。

框架只提升通过 null test 的候选。没有真实干预文件时命令会失败，不会伪造 causal score。

## 路径迁移

```powershell
python -m stegopot analyze compare-paths outputs/<before-analysis> outputs/<after-analysis>
```

两张图的协议指纹必须完全相同。框架将每个表面的 causal score 汇总并归一化，输出
Jensen-Shannon 距离和逐表面因果贡献变化。协议不一致会直接拒绝比较。

## 分析输出

```text
outputs/<analysis-id>/
  analysis-manifest.json   来源运行、封印摘要、协议指纹和泄漏审计
  localization.json        完整 LocalizationMap
  localization.md          可阅读摘要
  null-tests.json          每个地址的置换对照
  analysis-seal.json       定位工件摘要封印
  path.json                attribute 后生成
  path-seal.json           路径图与来源定位图摘要

outputs/<migration-id>/
  analysis-manifest.json
  migration.json
  analysis-seal.json
```

分析目录是新建工件，不能覆盖已有结果。原实验运行始终只读。

## 开发接口

稳定领域对象位于 `stegopot.domain.model.localization` 和
`stegopot.domain.model.attribution`；算法协议位于 `stegopot.domain.interface.localization`
和 `stegopot.domain.interface.intervention`。1.1.0 暂不把 localizer/intervention 加入插件
API 1.4，避免过早冻结仍在演化的研究协议。文件级入口为：

```python
from stegopot.bootstrap.analysis import (
    attribute_path,
    combine_localizations,
    compare_paths,
    localize_runs,
)
```

插件 API 仍用于正常实验的 Scenario、Policy、LLM、Substrate、Channel、Codec、Detector、
Reward、OutcomeReward、Evaluator、Tool 和 Audit。两条扩展路径的权限不同，不能混用。
