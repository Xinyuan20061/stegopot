# 运行时内核

## Capability

模型适配器显式声明实际能力：

| capability | 含义 |
| --- | --- |
| `forward` | 执行模型前向 |
| `generation` | 生成文本或 token |
| `token_step_control` | 在 token 提交前暂停、检查和重算 |
| `activation_read` | 读取指定内部张量 |
| `activation_write` | 在真实前向中修改内部张量 |
| `gradient_read` | backward 后读取选定激活的梯度 |
| `agent_message_hook` | 控制 Agent 消息生命周期 |

插件通过 `requires_capabilities` 声明要求，`model_adapter` 通过
`provides_capabilities` 声明提供项。配置预检会在模型加载前拒绝不匹配组合。

## TensorRef

`TensorRef` 支持两种地址：

```python
TensorRef(module="model.layers.8.mlp", token=-1)
TensorRef(layer=8, component="resid_post", token=-1)
```

通用 Hugging Face 适配器识别常见层容器，以及 `resid_pre`、`resid_post`、
`attention_output` 和 `mlp_output`。未知架构使用精确 `module` 路径。
`head` 只有后端能够证明布局时才支持；通用适配器不会猜测。

## TracePolicy

```python
from stegopot import TensorRef, TracePolicy

policy = TracePolicy(
    refs=(TensorRef(layer=8, component="resid_post", token=-1),),
    store="cpu",
    detach=True,
    precision="float32",
    max_records=32,
    max_bytes=64 * 1024 * 1024,
)
```

- `profile="none"` 不安装采集 Hook。
- `selected` 只采集 `refs`。
- `full` 采集叶子模块，仍受记录数和字节上限约束。
- `store` 可选 `memory`、`cpu` 或 `disk`。
- 保留计算图或梯度时必须使用 `store="memory", detach=False`。
- 磁盘模式要求构造适配器时注入 `TraceStore`。

`ActivationTrace` 按 TensorRef 与生成步骤索引记录。JSON manifest 只保存 shape、dtype、
设备、摘要引用和梯度是否就绪，不保存张量原值。

## 可控 Forward

```python
from stegopot import ModelInput, ModelRuntime
from stegopot.infrastructure.model_adapters import HuggingFaceAdapter

adapter = HuggingFaceAdapter(
    model_path="D:/Models/Qwen",
    revision="固定修订",
    local_files_only=True,
)
runtime = ModelRuntime(adapter)
result = runtime.forward(ModelInput("prompt"), policy=policy)
activation = result.trace.get(policy.refs[0]).value
```

梯度由调用方定义目标函数：

```python
gradient_policy = TracePolicy(
    refs=policy.refs,
    store="memory",
    detach=False,
    retain_graph=True,
    retain_gradients=True,
)
result = runtime.forward(ModelInput("prompt"), policy=gradient_policy)
metric = result.output.logits[0, -1, target_token]
metric.backward()
gradient = result.trace.get(policy.refs[0]).gradient
```

StegoPot 不定义具体任务的 metric 或模型图。核心只提供基础 EAP 的统一符号约定：
`(evaluated_source-reference_source) dot evaluated_target_gradient`，以及把显式边转换为
真实 residual edge patch 的构造器。EAP-IG、AtP 和实验协议由插件实现；公开 SAE 的
加载、重构测量与特征干预由基础集成提供，特征选择和解释仍属于实验插件。

## 干预

核心提供 Replace、Zero、Scale、Add 和 Interpolate 五个无实验语义的算子：

```python
from stegopot import Intervention
from stegopot.application.services.runtime import ScaleOperator

intervention = Intervention(
    intervention_id="scale-layer-8",
    target=TensorRef(layer=8, component="resid_post", token=-1),
    operator=ScaleOperator(0.5),
)
changed = runtime.forward(
    ModelInput("prompt"),
    interventions=(intervention,),
)
```

`observe + condition` 可组成在线条件干预。条件只获得观察张量和最小
`InterventionContext`；具体 Probe 或检测策略由插件实现。算子返回值必须与目标选择的
shape、dtype 和 device 完全一致。

## SAE 特征干预

`core.saelens` 提供统一的 `SAEModel`。`SAEFeatureInterventionOperator` 在特征空间执行
`zero`、`set`、`scale` 或 `add`，并默认使用以下形式保留 SAE 重构误差：

```text
x_intervened = x + decode(z_intervened) - decode(encode(x))
```

实验插件负责把 SAE 的 `hook_name` 显式映射到模型 `TensorRef`，并使用
`build_sae_feature_intervention()` 构造运行时干预。核心不会根据字符串名称猜测层位置。
完整示例见 [SAE 集成](sae.md)。

## 逐 Token Generation

```python
from stegopot import GenerationConfig

session = runtime.generate_session(
    ModelInput("prompt"),
    config=GenerationConfig(max_new_tokens=32, temperature=0),
    policy=policy,
)
while not session.finished:
  step = session.forward_next()
  record = step.inspect(policy.refs[0])
  token_id = step.sample()
  session.commit(token_id)
result = session.result()
```

`step.apply(interventions)` 会在 token 提交前重算当前步骤。初版 Hugging Face 会话使用
完整前缀重算，强调正确、透明和可干预；高性能 KV cache 会话可由后端插件实现。

## 数据与 Probe

`DatasetPipeline` 固定执行：

```text
DatasetSource -> Transform -> Validate -> Grouped Split -> DatasetBundle
```

`Sample` 只有 `sample_id`、`input`、可选 `target` 和 `metadata`。实验插件可以在
input/target 中放自己的结构，但核心不增加 secret 或 carrier 字段。

`build_probe_dataset` 和 `build_layer_probe_datasets` 将中央标签与 ActivationTrace
对齐，并支持 none、last_token、mean_tokens 和 flatten 池化。Probe 的训练、校准和
评价由实现 `Probe` 的外部组件负责。

## 事件与存储

`InMemoryEventBus` 同步发布 forward、activation、generation、intervention 和实验
生命周期事件。事件不得携带原始张量或凭证。

`FileArtifactStore` 为每次运行创建独占目录，写入 config、metadata、outputs、metrics
和 SHA-256 manifest。已存在文件、路径越界和封印后写入都会失败。
