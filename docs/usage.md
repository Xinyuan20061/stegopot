# 使用指南

## 安装

```powershell
git clone https://github.com/Xinyuan20061/stegopot.git
cd stegopot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

需要本地模型内部访问时安装：

```powershell
python -m pip install -e ".[whitebox]"
```

StegoKit 生成式隐写使用：

```powershell
python -m pip install -e ".[stego]"
```

## 工作区

```powershell
stegopot init D:\Research\my-study
```

用户 YAML/JSON 放在 `configs/`，凭证放在 `.env`，结果写入 `outputs/`。这些内容默认
不提交仓库。

常用命令：

```powershell
stegopot list --workspace D:\Research\my-study
stegopot validate experiment --workspace D:\Research\my-study
stegopot doctor experiment --workspace D:\Research\my-study
stegopot run experiment --workspace D:\Research\my-study
stegopot plugins inspect core
stegopot schema
```

## v2 通用研究配置

v2 配置组合外部 Dataset、Scenario、Analyzer、Metric 和 Reporter 插件：

```yaml
schema_version: "2"
plugins:
  - my_stego_study
seed: 7

runtime:
  adapter:
    type: core.huggingface
    config:
      model_path: D:/Models/your-causal-lm
      revision: fixed-revision
      device: cpu
      dtype: float32
      local_files_only: true
      trust_remote_code: false

dataset:
  source:
    type: my_stego_study.dataset
    config:
      source_file: D:/Research/data.jsonl
  count: 200
  transforms: []
  validators:
    - type: my_stego_study.valid_pair
  split:
    train: 0.7
    validation: 0.15
    test: 0.15
    seed: 7
    group_key: pair_id

scenario:
  type: my_stego_study.trace_scenario
  config:
    layers: [6, 8, 10, 12]

analyzers:
  - type: my_stego_study.attribution
metrics:
  - type: my_stego_study.recovery
reporters: []
partitions: [train, validation, test]
```

`my_stego_study.*` 只是外部插件示例名称，不是内置实验。capability 在预检阶段匹配，
模型只有真正运行时才加载。运行结果目录包含 `config.json`、`metadata.json`、
`outputs.jsonl`、`metrics.json` 和 `manifest.json`。

## Python 运行时

```python
from stegopot import ModelInput, ModelRuntime, TensorRef, TracePolicy
from stegopot.infrastructure.model_adapters import HuggingFaceAdapter

adapter = HuggingFaceAdapter(
    model_path="D:/Models/your-causal-lm",
    local_files_only=True,
    parameter_gradients=False,
)
runtime = ModelRuntime(adapter)
ref = TensorRef(layer=12, component="resid_post", token=-1)
result = runtime.forward(
    ModelInput("test prompt"),
    policy=TracePolicy(refs=(ref,)),
)
print(result.trace.get(ref).shape)
runtime.close()
```

纯激活审计建议设置 `parameter_gradients=False`。该模式不为模型参数分配梯度，但仍支持
选定 activation 的 backward 和梯度读取，可显著降低 EAP 等实验的显存占用。

## v1 多 Agent 配置

v1 配置继续负责 Agent、拓扑、消息、信道、检测、奖励、StegoKit 和审计：

```yaml
schema_version: "1"
scenario:
  type: core.explicit
  config:
    task: Solve the task
    nodes:
      - id: sender
        role: sender
        policy:
          type: core.llm
          config:
            client: deepseek
            temperature: 0
      - id: receiver
        role: receiver
        policy:
          type: core.echo
    edges:
      - [sender, receiver]

resources:
  deepseek:
    type: core.chat_completions
    config:
      base_url: https://api.deepseek.com
      model: your-model-name
      api_key_env: DEEPSEEK_API_KEY
```

`.env`：

```dotenv
DEEPSEEK_API_KEY=your-key
```

Chat Completions 是黑盒调用，不提供 activation 或 gradient。需要这些能力时使用
`model_adapter`，不要让 API 客户端虚假实现白盒接口。

## StegoKit

`core.stegokit` 是基础隐写能力，作为 v1 `codec` 资源使用。`core.codec_sender` 和
`core.codec_receiver` 把编解码器接入 Agent 消息流程。模型路径必须是可信本地模型；
默认不下载权重、不执行远程代码。具体隐写协议实验、对照和指标仍应放在外部插件。

## 文件级 API

```python
from stegopot.bootstrap.experiments.api import diagnose_file, run_file

diagnostics = diagnose_file(
    "experiment",
    workspace="D:/Research/my-study",
)
report, directory = run_file(
    "experiment",
    workspace="D:/Research/my-study",
)
print(report["status"], directory)
```

`run_file` 自动按 `schema_version` 选择 v1 或 v2 执行链。配置解析拒绝重复键和未知字段，
不会把真实密钥写入结果。
