<p align="center">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

<p align="center">
  <img src="docs/assets/stegopot-icon.png" alt="StegoPot" width="112">
</p>

<h1 align="center">StegoPot</h1>

<p align="center"><strong>多智能体隐写、隐蔽通信与共谋研究实验框架</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/version-1.1.0-2F81F7?style=flat-square" alt="Version 1.1.0">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/PyTorch-2.1%2B%20optional-EE4C2C?style=flat-square&logo=pytorch&logoColor=white" alt="PyTorch 2.1+ optional">
  <img src="https://img.shields.io/badge/plugin%20API-1.4-4B5563?style=flat-square" alt="Plugin API 1.4">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-D22128?style=flat-square" alt="Apache-2.0 License"></a>
</p>

<p align="center">
  <a href="#核心功能">核心功能</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#llm-节点">LLM 节点</a> ·
  <a href="#隐写实验">隐写实验</a> ·
  <a href="#隐写路径分析">路径分析</a> ·
  <a href="#插件扩展">插件扩展</a>
</p>

StegoPot 使用 YAML/JSON 描述实验。用户可以配置 Agent 节点、有向拓扑、模型、
隐写编解码器、信道、检测器、奖励和评价器，然后通过统一命令完成预检、运行、
审计、完整性验证与指标复算。

## 核心功能

| 功能 | 说明 |
| --- | --- |
| 多 Agent 拓扑 | 自定义节点、角色和有向边，按同步轮次执行消息交互 |
| LLM 节点 | 每个节点独立配置模型、系统角色、采样参数和输出约束 |
| 隐写编解码 | 通过内置 StegoKit 适配器生成载体并从实际接收文本恢复比特 |
| 通信来源标记 | 区分普通模型消息 `opaque` 与受控编解码消息 `instrumented` |
| 信息流控制 | 分离公开信息、节点私有信息、秘密载荷、监控信息和评价信息 |
| 信道与检测 | 在消息投递前执行阻断、替换、自定义信道和规则/LLM 检测 |
| 奖励闭环 | 支持逐轮奖励、检测惩罚和 Episode 结束后的结果奖励 |
| 节点工具 | Agent 通过允许列表调用工具，工具结果仅返回调用节点 |
| 连续 Session | 在同一 Session 的 Episode 之间保留允许延续的策略状态 |
| 配对反事实 | 固定同一条真实载体，仅改变信道、检测器或奖励条件 |
| 标准指标 | 输出 BER、恢复率、bits/token、检测性能、AUROC 和任务效用 |
| 秘密定位 | 对 Token/Text、Activation、KV、Logits 计算统一可恢复分数和随机标签对照 |
| 因果路径归因 | 对显著候选执行反事实干预，同时保存定位分数 L 与因果贡献 M |
| 路径迁移 | 在协议一致时比较优化前后的表面贡献分布和 Jensen-Shannon 距离 |
| 插件系统 | 通过装饰器注册 12 类组件，在两次实验之间热插拔 |
| 全过程审计 | 保存公开/研究双日志、运行计划、源码指纹和实验报告 |
| 证据验证 | 校验日志哈希链和结果封印，并从原始结果离线复算指标 |

适用场景包括：

- 多智能体定向通信、协作和竞争基线；
- LLM 隐蔽通信与共谋行为观察；
- 显式隐写算法的容量、恢复率和鲁棒性测试；
- 载体净化、消息阻断和检测器消融实验；
- 隐写成功率、检测性能与任务效用的联合评估；
- 论文复现协议和新实验组件的插件化实现。
- 多智能体秘密信息流的离线定位、因果归因与路径迁移研究。

## 安装

### 从源码安装当前版本

```powershell
git clone https://github.com/Xinyuan20061/stegopot.git
cd stegopot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

### 安装 v1.0.0 发行版

```powershell
python -m pip install https://github.com/Xinyuan20061/stegopot/releases/download/v1.0.0/stegopot-1.0.0-py3-none-any.whl
```

需要 StegoKit、本地 Transformers 模型和 PyTorch 时安装可选依赖：

```powershell
python -m pip install -e ".[stego]"
```

## 快速开始

### 1. 创建实验工作区

```powershell
python -m stegopot init D:\Research\my-stegopot-study
```

工作区包含：

```text
my-stegopot-study/
  .env               本地密钥和环境变量
  configs/           YAML/JSON 实验配置
  outputs/           每次运行产生的独立结果目录
```

### 2. 编写实验配置

创建 `D:\Research\my-stegopot-study\configs\communication.yaml`：

```yaml
schema_version: "1"

scenario:
  type: core.explicit
  config:
    task: "发送者向接收者报告状态"
    max_rounds: 2
    nodes:
      - id: sender
        role: sender
        policy:
          type: core.scripted
          config:
            actions:
              - kind: message
                content: "ready"
                target: receiver
      - id: receiver
        role: receiver
        policy:
          type: core.echo
    edges:
      - [sender, receiver]
```

`edges` 是有向边。只有 `sender -> receiver` 被声明时，发送节点才能向接收节点投递消息。

### 3. 预检并运行

```powershell
python -m stegopot validate communication --workspace D:\Research\my-stegopot-study
python -m stegopot run communication --workspace D:\Research\my-stegopot-study
```

`validate` 只校验配置、组件引用、拓扑、预算和信息流，不构造模型或发起网络请求。
使用本地 StegoKit 模型时，可通过 `doctor` 额外检查模型目录和运行资源：

```powershell
python -m stegopot doctor communication --workspace D:\Research\my-stegopot-study
```

## LLM 节点

StegoPot 内置兼容 Chat Completions 协议的模型客户端，可用于 DeepSeek 等服务。

在工作区 `.env` 中保存密钥：

```dotenv
DEEPSEEK_API_KEY=你的实际密钥
```

在配置中声明模型资源和节点策略：

```yaml
schema_version: "1"

resources:
  deepseek:
    type: core.chat_completions
    config:
      base_url: https://api.deepseek.com
      model: deepseek-chat
      api_key_env: DEEPSEEK_API_KEY
      timeout: 60
      response_format: json_object

scenario:
  type: core.explicit
  config:
    task: "向 receiver 发送一条简短状态消息"
    max_rounds: 2
    nodes:
      - id: sender
        role: sender
        policy:
          type: core.llm
          config:
            client: deepseek
            role: "你是发送节点，只输出规定 JSON 动作。"
            action_kind: message
            target: receiver
            active_round: 0
            max_tokens: 128
      - id: receiver
        role: receiver
        policy:
          type: core.echo
    edges:
      - [sender, receiver]
```

配置只引用环境变量名称，不会把密钥写入报告或审计日志。每个 LLM 节点可以使用不同的
模型资源、角色提示、目标节点和 token 上限。

## 隐写实验

### 通信模式

| 模式 | 来源 | 用途 |
| --- | --- | --- |
| `opaque` | 普通脚本策略或 LLM | 观察未知来源消息，不预设其是否含有隐写信息 |
| `instrumented` | `core.codec_sender` | 记录 codec、载荷长度、实际消耗比特、载体 token 数和正文哈希 |

`opaque` 消息默认不作为检测正负标签。实验数据已有可靠标签时，可以通过
`truth.stego_label` 提供标签。

### StegoKit

内置 `core.stegokit` 从本地路径加载 Hugging Face 模型：

```yaml
resources:
  stego:
    type: core.stegokit
    config:
      model_path: D:/Models/local-causal-model
      algorithm: ac
      generation:
        max_new_tokens: 128
```

发送端和接收端策略分别使用：

```yaml
# 发送节点
policy:
  type: core.codec_sender
  config:
    codec: stego
    target: receiver
    active_round: 0

# 接收节点
policy:
  type: core.codec_receiver
  config:
    codec: stego
    active_round: 1
```

发送节点私有上下文提供 `secret_bits`、可选 `cover` 和 `shared_material`。接收端只解码
经过 Substrate 和 Channel 处理后实际收到的文本，不读取编码端的隐藏 token 序列。

### 信息流

实验可以通过 `information` 声明数据类别和可见主体：

```yaml
information:
  public_rules:
    class: public
    value: {language: zh}
  sender_secret:
    class: secret_payload
    value: "101101"
    visible_to: ["node:sender", evaluator, research_audit]
  decoder_key:
    class: decoder_private
    value: {key_id: shared-01}
    visible_to: ["node:receiver", evaluator, research_audit]
```

支持 `public`、`agent_private`、`secret_payload`、`decoder_private`、`monitor_visible`、
`evaluator_only` 和 `research_only` 七类信息。宿主在运行前检查授权范围，并为节点、
环境、检测器、奖励器和评价器分别生成数据视图。

### 配对反事实

`core.counterfactual` 先运行源 Trial，再把源消息正文和 SHA-256 固定到多个处理分支。
分支不会重新调用发送模型，因此可以直接比较信道、检测器或奖励变化的影响。

```yaml
scenario:
  type: core.counterfactual
  config:
    source:
      id: source
      task: "生成一个通信载体"
      max_rounds: 2
      nodes:
        - id: sender
          policy:
            type: core.scripted
            config:
              actions:
                - {kind: message, content: "carrier", target: receiver}
        - id: receiver
          policy: {type: core.echo}
      edges: [[sender, receiver]]
    carrier: {sender: sender, recipient: receiver}
    group_id: carrier-ablation
    treatments:
      - id: raw
        channels: []
      - id: blocked
        channels:
          - {type: core.block}
```

### 标准指标

使用 `core.stego_metrics` 可以计算：

- 比特恢复率、解码完整性和 BER；
- payload bits、consumed bits、嵌入覆盖率和 bits/token；
- 消息投递率；
- 检测混淆矩阵、TPR、FPR、precision 和 AUROC；
- `truth.expected_answers` 对应的任务效用；
- 配对反事实各处理组的聚合结果。

## 隐写路径分析

StegoPot 1.1 将“是否可疑”的实时检测与“秘密在哪里、是否因果参与传播”的离线分析分开：

```text
封印实验 + 中央秘密标签 + 可选表征工件
  -> matched-group 数据集
  -> Secret Probe + permutation null test
  -> LocalizationMap
  -> 反事实干预
  -> CausalPathGraph
  -> Path Migration
```

内置 `TextSecretProbe` 使用字符/词 n-gram，`LinearSecretProbe` 用于 Activation、KV 和
Logits 向量，`StructuredSecretProbe` 供 Python 侧处理 Tool、Timing、Behavior 等 JSON
特征。统一定位分数为 `L(Z)=clip(1-CE_Z/CE_0,0,1)`；报告同时保留 accuracy、CE、
先验 CE、置信区间、null 均值/标准差和 permutation p-value。

分析配置独立放在工作区 `analyses/`，不修改实验 YAML：

```yaml
schema_version: "stegopot.analysis/1"
secret:
  name: payload
  kind: categorical
  source: central-label-table-v1
  classes: ["0", "1"]
labels:
  paired-session-0001.secret-0: "0"
  paired-session-0001.secret-1: "1"
matched_groups:
  paired-session-0001.secret-0: context-0001
  paired-session-0001.secret-1: context-0001
surface: token
selection:
  agent_id: sender
  recipient: receiver
  rounds: [0]
  flow_order: 30
localizer:
  type: text
  config: {dimension: 1024, l2: 0.01, epochs: 250}
split: {train_ratio: 0.6, validation_ratio: 0.2, test_ratio: 0.2, seed: 7}
null_test: {repetitions: 100, alpha: 0.05}
bootstrap_repetitions: 500
minimum_samples: 24
aggregation: {top_k: 5}
protocol:
  task_distribution: task-set-v1
  secret_distribution: binary-balanced-v1
  topology: sender-receiver-v1
  model_family: local-model-v1
  sampling: temperature-0-v1
  capture: public-message-v1
  intervention: matched-activation-v1
  evaluator: secret-recovery-v1
```

上例只展示字段格式。正式分析至少需要 3 个 matched group 并满足 `minimum_samples`；
分析配置含中央标签，应保留在本地工作区且不要提交到 Git。

运行公开文本定位：

```powershell
python -m stegopot analyze localize D:\Research\study\outputs\<run-id> `
  --config D:\Research\study\analyses\secret_localization.yaml
```

内部表征不进入 `research.jsonl`。本地模型适配器通过
`RepresentationRecorder` 写独立二进制工件、索引和哈希封印，再在配置中声明
`representation_bundles`，使用 `surface: activation|kv|logits` 和 `localizer.type: vector`。
未采集或不支持的表面会显式失败，不会被记为 0 分。

因果归因只接受真实重跑结果。`MatchedActivationPatcher` 用上下文匹配、秘密不同的供体
激活替换源激活；调用方负责把替换值送回模型。统一因果分数为
`M(Z)=clip((R0-Ri)/(R0-Rchance),0,1)`，并保留三个原始恢复率。

```powershell
python -m stegopot analyze combine outputs/<token-analysis> outputs/<activation-analysis>
python -m stegopot analyze attribute outputs/<analysis-id> --interventions interventions.json
python -m stegopot analyze compare-paths outputs/<before> outputs/<after>
```

路径迁移比较要求两侧协议指纹完全一致。详细配置、表征记录和干预文件格式见
[隐写路径定位与因果归因](docs/path_attribution.md)。

## 节点工具

节点只允许调用自身 `tools` 映射中声明的工具别名。工具动作格式如下：

```json
{
  "kind": "tool_call",
  "content": null,
  "target": null,
  "metadata": {},
  "tool_call": {
    "tool": "calculator",
    "operation": "double",
    "arguments": {"value": 21}
  }
}
```

宿主检查节点授权、调用预算和 JSON 大小后执行工具。结果只在下一轮的
`observation.tool_results` 中返回调用节点；请求、结果和错误进入研究审计。

## 内置组件

StegoPot 1.1.0 保留 20 个运行期内置组件，并新增独立离线分析内核：

| 类型 | 组件 |
| --- | --- |
| Scenario | `core.explicit`、`core.sessions`、`core.counterfactual` |
| Policy | `core.scripted`、`core.echo`、`core.llm`、`core.codec_sender`、`core.codec_receiver` |
| LLM | `core.chat_completions` |
| Substrate | `core.communication` |
| Channel | `core.block`、`core.replace` |
| Codec | `core.stegokit` |
| Detector | `core.keyword`、`core.llm_detector` |
| Reward | `core.delivery_reward`、`core.detection_penalty` |
| Outcome reward | `core.exact_match_outcome` |
| Evaluator | `core.metrics`、`core.stego_metrics` |

查看组件参数 Schema：

```powershell
python -m stegopot plugins inspect core
python -m stegopot schema --component core.llm
```

## 配置参考

| 顶层字段 | 作用 |
| --- | --- |
| `schema_version` | 配置版本，当前为字符串 `"1"` |
| `scenario` | 生成实验计划的场景组件 |
| `plugins` | 允许加载的第三方插件和版本范围 |
| `resources` | 可复用的 LLM、Codec 或 Tool 资源 |
| `policies` | 按节点 ID 覆盖场景策略 |
| `topology` | 覆盖场景中的有向拓扑边 |
| `channels` | 消息信道处理组件 |
| `detectors` | 公开文本检测组件 |
| `rewards` | 逐轮奖励组件 |
| `outcome_rewards` | Episode 结束后的结果奖励 |
| `evaluators` | 实验指标评价器 |
| `audit_sinks` | 附加审计输出组件 |
| `threat_model` | 历史、监控上下文和审计投影设置 |
| `runtime` | 调用次数、时间、token、消息和上下文预算 |

组件统一使用以下结构：

```yaml
type: plugin.component
config:
  parameter: value
```

配置 Schema 会拒绝未知字段；YAML 重复键、锚点和别名同样会被拒绝。密钥应放入
工作区 `.env`，并在组件配置中通过环境变量名称引用。

## 命令行

```powershell
python -m stegopot --version
python -m stegopot init <工作区>
python -m stegopot list --workspace <工作区>
python -m stegopot validate <配置名> --workspace <工作区>
python -m stegopot doctor <配置名> --workspace <工作区>
python -m stegopot run <配置名> --workspace <工作区>
python -m stegopot verify <运行目录>
python -m stegopot recompute <运行目录>
python -m stegopot events <运行目录> --scope public --limit 100
python -m stegopot analyze localize <运行目录或运行组> --config <分析配置>
python -m stegopot analyze combine <定位分析1> <定位分析2> [...]
python -m stegopot analyze attribute <分析目录> --interventions <干预结果>
python -m stegopot analyze compare-paths <迁移前分析> <迁移后分析>
python -m stegopot plugins list
python -m stegopot plugins inspect core
python -m stegopot schema --component core.llm
```

`events` 默认先验证封印并读取公开日志。完整研究事件需要显式指定
`--scope research`。

## Python API

```python
from stegopot.bootstrap.experiments.api import (
    prepare_file,
    recompute_directory,
    run_file,
)
from stegopot.bootstrap.analysis import (
    attribute_path,
    combine_localizations,
    compare_paths,
    localize_runs,
)

prepared = prepare_file(
    "study",
    workspace="D:/Research/my-stegopot-study",
)
print(len(prepared.plan.trials))

report, output_directory = run_file(
    "study",
    workspace="D:/Research/my-stegopot-study",
)
if report["status"] != "completed":
    raise RuntimeError(report["errors"])

verification = recompute_directory(output_directory)
assert verification["verified"]

localization, analysis_directory = localize_runs(
    output_directory,
    config="D:/Research/my-stegopot-study/analyses/secret_localization.yaml",
)
```

实验 CLI/Python API 共用运行链路；分析 CLI/Python API 共用独立分析配置和只读封印数据源。

## 插件扩展

插件 API 1.4 支持 `scenario`、`policy`、`llm`、`substrate`、`channel`、`codec`、
`detector`、`reward`、`outcome_reward`、`evaluator`、`tool` 和 `audit`。

```python
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model import ToolResult

plugin = Plugin("my_lab", "0.1.0")


class Calculator:
    """提供一个确定性的倍增操作。"""

    def execute(self, request):
        if request.operation != "double":
            raise ValueError("不支持的操作")
        return ToolResult(request.arguments["value"] * 2)

    def close(self):
        """当前工具没有需要释放的资源。"""


@plugin.component(
    "tool",
    "calculator",
    schema={
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    },
)
def build_calculator(config, context):
    """构造工具实例。"""
    return Calculator()


def entrypoint():
    """返回插件定义。"""
    return plugin()
```

在插件包中声明入口：

```toml
[project.entry-points."stegopot.plugins"]
my_lab = "my_lab.plugin:entrypoint"
```

实验配置必须显式允许第三方插件：

```yaml
plugins:
  - id: my_lab
    version: ">=0.1,<1"
```

完整接口约定见 [插件开发文档](docs/plugin_development.md)。

## 实验输出

每次运行产生一个不可覆盖的结果目录：

```text
outputs/<run-id>/
  manifest.json             配置、固定计划、插件和源码指纹
  threat-model.json         有效拓扑、组件边界和信息流摘要
  experiment-report.json    逐试验结果、指标和汇总
  report.md                 可阅读的实验摘要
  research.jsonl            完整研究事件哈希链
  public.jsonl              最小公开事件哈希链
  seal.json                 根工件和日志终点封印
  <trial-id>/
    result.json
    research.jsonl
    public.jsonl
    seal.json
```

离线定位另行创建不可覆盖的分析目录，不向原运行追加文件：

```text
outputs/<analysis-id>/
  analysis-manifest.json
  localization.json
  localization.md
  null-tests.json
  analysis-seal.json
  path.json               执行 attribute 后生成
  path-seal.json          执行 attribute 后生成

outputs/<migration-id>/
  analysis-manifest.json
  migration.json
  analysis-seal.json
```

验证结果目录：

```powershell
python -m stegopot verify D:\Research\my-stegopot-study\outputs\<run-id>
python -m stegopot recompute D:\Research\my-stegopot-study\outputs\<run-id>
```

`verify` 检查文件摘要、日志哈希链、子试验封印和预注册计划一致性；`recompute`
进一步验证当前插件源码，并从固定计划和原始结果重新计算指标。

## 运行约束

`runtime` 可限制模型调用、工具调用、单次输出 token、累计 token、试验数、轮数、
执行时间、消息大小和上下文大小。框架还支持按 Trial 和按节点设置调用上限。

StegoPot 的插件运行在同一 Python 进程中。节点可见信息、工具权限和调用预算由宿主限制，
但不可信第三方插件仍应在容器或虚拟机中运行，以隔离文件、网络、CPU、内存和 GPU。

## 文档

- [使用指南](docs/usage.md)
- [插件开发](docs/plugin_development.md)
- [架构与依赖方向](docs/architecture.md)
- [内核控制与审计](docs/kernel.md)
- [隐写路径定位与因果归因](docs/path_attribution.md)
- [威胁模型与信息边界](docs/threat_model.md)
- [文档索引](docs/README.md)

## 许可证

StegoPot 使用 [Apache License 2.0](LICENSE)。内置 StegoKit 上游源码保留其原始许可证，
详见 `stegopot/infrastructure/vendor/stego-kit/LICENSE`。
