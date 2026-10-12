<p align="center">
  <strong>简体中文</strong> | <a href="README_EN.md">English</a>
</p>

<p align="center">
  <img src="docs/assets/stegopot-icon.png" alt="StegoPot" width="112">
</p>

<h1 align="center">StegoPot</h1>

<p align="center"><strong>面向 LLM 隐写与多智能体研究的可控实验底座</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/version-2.1.0-2F81F7?style=flat-square" alt="Version 2.1.0">
  <img src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/PyTorch-optional-EE4C2C?style=flat-square&logo=pytorch&logoColor=white" alt="PyTorch optional">
  <img src="https://img.shields.io/badge/plugin%20API-1.6-4B5563?style=flat-square" alt="Plugin API 1.6">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-Apache--2.0-D22128?style=flat-square" alt="Apache-2.0 License"></a>
</p>

StegoPot 统一了可控模型执行、内部状态访问、数据组织、多 Agent 交互、隐写基础能力和
实验生命周期。核心不实现某篇论文的完整实验协议；用户通过配置和独立插件定义数据、
协议、Probe、高级归因方法、指标与场景。

## 可以做什么

| 能力 | 内容 |
| --- | --- |
| 可控前向 | 普通、选择性追踪、保留计算图和运行时干预四种 forward |
| 内部状态 | 用 `TensorRef` 访问 layer/component/token 级 activation 和 gradient |
| 逐 token 生成 | 在 token 输出前检查激活、应用干预、采样并显式提交 |
| 基础干预 | Replace、Zero、Scale、Add、Interpolate 和条件触发 |
| 数据流水线 | Source -> Transform -> Validate -> 分组切分 -> 指纹与存储 |
| Probe 接口 | 从任意层 ActivationTrace 构造训练/评估数据；算法由插件提供 |
| 因果归因 | 内置基础 EAP 评分、显式边定义与 residual edge patch 构造器 |
| 稀疏特征 | 加载公开 SAE、兼容性清单、重构评估和特征空间因果干预 |
| 通用实验 | Dataset -> Scenario -> Analyze -> Evaluate -> Save |
| 多 Agent | 自定义节点、角色、有向拓扑、信道、检测、奖励和连续 Episode |
| 模型接入 | Hugging Face 白盒适配器与 Chat Completions 黑盒客户端并存 |
| 隐写基础 | 内置 StegoKit 适配、载体编解码与多 Agent 消息接入 |
| 插件系统 | 严格 schema、装饰器注册、依赖注入、capability 预检 |
| 可复现工件 | 配置、环境、插件、输出、指标、张量引用和 SHA-256 封印 |

以下内容刻意不在核心中：SAE 训练、任务特定的特征筛选与解释、EAP-IG、AtP、特定
Probe 训练器、clean/corrupt Pair、单比特协议、论文场景和预置实验。它们应作为插件组合
底层能力。核心 SAE 与 EAP 只提供可复用机制，不猜测模型计算图、秘密语义或论文结论。

## 架构

```text
bootstrap
  ├── application
  │     ├── runtime / data / research
  │     └── multi-agent engine
  └── infrastructure
        ├── Hugging Face / Chat Completions
        ├── StegoKit
        ├── plugins / storage / audit
              ↓
            domain
       models + interfaces
```

仓库只保留 `domain`、`application`、`infrastructure` 和 `bootstrap` 四个物理层。
详细依赖见 [架构文档](docs/architecture.md)。

## 安装

```powershell
git clone https://github.com/Xinyuan20061/stegopot.git
cd stegopot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

本地白盒模型：

```powershell
python -m pip install -e ".[whitebox]"
```

StegoKit：

```powershell
python -m pip install -e ".[stego]"
```

公开 SAE：

```powershell
python -m pip install -e ".[sae]"
```

## 可控模型 API

```python
from stegopot import ModelInput, ModelRuntime, TensorRef, TracePolicy
from stegopot.infrastructure.model_adapters import HuggingFaceAdapter

adapter = HuggingFaceAdapter(
    model_path="D:/Models/your-causal-lm",
    revision="fixed-revision",
    local_files_only=True,
    parameter_gradients=False,
    # 8GB 显存运行 7B 白盒实验时可显式选择 bitsandbytes NF4。
    quantization="bnb_4bit",
    bnb_4bit_compute_dtype="bfloat16",
)
runtime = ModelRuntime(adapter)

ref = TensorRef(layer=12, component="resid_post", token=-1)
result = runtime.forward(
    ModelInput("Inspect this prompt"),
    policy=TracePolicy(refs=(ref,), store="cpu"),
)
print(result.trace.get(ref).shape)
runtime.close()
```

`parameter_gradients=False` 会冻结模型参数，但仍从输入嵌入建立激活计算图，适合 EAP、
activation patching 和 Probe 数据采集。需要训练模型参数时保持默认值 `True`。
量化模型的机制可能与全精度权重不同；实验清单必须记录量化方式，并对关键结论做跨精度复核。

## 基础 EAP

`core.eap` 接收插件或配置显式声明的 writer-reader 边，并计算：

```text
(evaluated_source - reference_source) · evaluated_target_gradient
```

返回值估计 `evaluated_metric - patched_metric`。`build_edge_patch()` 可把候选边转换为真实
干预，用精确前向验证排名。模型专用图、配对数据、可微 metric、行为门槛、随机基线和
稳定性统计仍由实验插件定义，避免核心绑定 Qwen、秘密位或某篇论文。

梯度、干预和逐 token 会话见 [运行时内核](docs/kernel.md)。

## 公开 SAE

`core.saelens` 将 SAE Lens 的公开 release 或本地权重加载为统一 `SAEModel` 资源。它会
保存 `SAEManifest`，并可严格核对基础模型 ID、hook 名、输入宽度和特征宽度。核心同时
提供重构质量测量及 `zero/set/scale/add` 特征干预；特征搜索、标签解释、统计检验和论文
实验协议仍由外部实验插件实现。

```yaml
resources:
  layer_sae:
    type: core.saelens
    config:
      source: your-saelens-release
      sae_id: your-sae-id
      device: cuda
      dtype: bfloat16
      expected_model_id: your/model-id
      expected_hook_name: your/hook-name
      expected_input_width: 3584
```

外部 Analyzer 或 Scenario 通过 `references={"sae": "sae"}` 获得该资源。完整边界、
验证步骤和插件示例见 [SAE 集成](docs/sae.md)。

## 配置运行

初始化独立工作区：

```powershell
stegopot init D:\Research\my-study
stegopot validate experiment --workspace D:\Research\my-study
stegopot doctor experiment --workspace D:\Research\my-study
stegopot run experiment --workspace D:\Research\my-study
```

`schema_version: "2"` 用于通用受控模型实验：

```yaml
schema_version: "2"
plugins: [my_study]
seed: 7
runtime:
  adapter:
    type: core.huggingface
    config:
      model_path: D:/Models/your-causal-lm
      revision: fixed-revision
      local_files_only: true
dataset:
  source:
    type: my_study.dataset
  count: 100
scenario:
  type: my_study.scenario
analyzers:
  - type: my_study.analyzer
metrics:
  - type: my_study.metric
```

`my_study.*` 由用户自己的安装包提供。StegoPot 在加载模型前校验组件 schema、资源引用、
凭证和 capability。`schema_version: "1"` 继续支持多 Agent 消息实验。

## 插件

```python
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model.capability import Capability

plugin = Plugin("my_study", "0.1.0")

@plugin.component(
    "analyzer",
    "gradient_method",
    requires=(Capability.ACTIVATION_READ, Capability.GRADIENT_READ),
)
def build_analyzer(config, context):
  return GradientAnalyzer(**config)
```

插件依赖 capability，不依赖 `HuggingFaceAdapter` 具体类。注册器没有全局状态，插件只有在
配置 `plugins` 中显式启用后才会加载。完整约定见 [插件开发](docs/plugin_development.md)。

## API 模型与多 Agent

`core.chat_completions` 支持 DeepSeek 等兼容服务，密钥配置填写环境变量名：

```yaml
resources:
  deepseek:
    type: core.chat_completions
    config:
      base_url: https://api.deepseek.com
      model: your-model-name
      api_key_env: DEEPSEEK_API_KEY
```

API 模型用于 `llm` 节点，但不声明 activation/gradient 能力。v1 配置可以组合
`core.explicit` 或 `core.sessions` 场景、自定义拓扑、信道、检测、奖励、工具和评价器。
StegoKit 以 `core.stegokit` codec 资源接入。详见 [使用指南](docs/usage.md)。

## 输出与边界

v2 运行写入独占目录：

```text
outputs/<run-id>/
  config.json
  metadata.json
  outputs.jsonl
  metrics.json
  traces/
  manifest.json
```

默认不全量保存激活。`RuntimeEvent` 不携带原始张量，磁盘 Tensor 使用摘要引用。
用户配置、`.env`、测试和结果默认被 Git 忽略。

插件以 `trusted_in_process` 方式运行。框架提供接口级信息隔离和资源约束，但不是操作系统
安全沙箱；不可信插件应放在外部容器或受限进程中执行。

## 文档

- [架构](docs/architecture.md)
- [运行时内核](docs/kernel.md)
- [SAE 集成](docs/sae.md)
- [使用指南](docs/usage.md)
- [插件开发](docs/plugin_development.md)
- [威胁模型](docs/threat_model.md)
