# 公开 SAE 集成

## 边界

StegoPot 2.1 把“加载并运行公开 SAE”作为通用机制分析能力，把“某个隐写实验如何选择、
解释和统计特征”留给实验插件。分工如下：

| StegoPot 核心 | 外部实验插件 |
| --- | --- |
| `SAEModel` 稳定协议 | 选择模型层与 token |
| SAE Lens release/本地权重加载 | 定义 clean/corrupt 或秘密条件 |
| 模型、hook 与维度兼容性检查 | 选择候选特征与多重检验方法 |
| 编码、解码、重构和单特征读取 | 解释特征与定义研究指标 |
| 重构 MSE、余弦、解释方差与 L0 | 生成论文图表和结论 |
| 保留重构误差的通用特征干预 | 定义消融、patching 和控制组协议 |

核心不训练 SAE，也不会根据 `hook_name` 猜测 Hugging Face 的 `TensorRef`。不同模型库对
hook 的命名方式可能不同，实验插件必须显式给出二者映射。当前内置实现只接受输入与
重构空间相同的稀疏自编码器；输入、输出位置不同的 transcoder 应由独立插件适配。

## 安装

```powershell
python -m pip install -e ".[whitebox,sae]"
```

SAE Lens 会使用 Hugging Face 缓存。可通过 `HF_HOME` 把模型与 SAE 权重放到项目外的
持久缓存目录；这些大文件不应提交到 Git。

## 配置资源

在 v2 实验的 `resources` 中声明 `core.saelens`：

```yaml
resources:
  target_sae:
    type: core.saelens
    config:
      source: gemma-scope-2b-pt-res-canonical
      sae_id: layer_10/width_16k/average_l0_77
      source_kind: pretrained
      device: cuda
      dtype: bfloat16
      force_download: false
      expected_model_id: gemma-2-2b
      expected_hook_name: blocks.10.hook_resid_post
      expected_input_width: 2304
```

`source` 和 `sae_id` 必须使用 SAE Lens 当前 release 表中的值。Hugging Face 仓库名不一定
等于 release 名；运行前应以公开权重页面和 SAE Lens release 清单为准。本地已导出的权重
使用 `source_kind: local`，此时 `source` 为目录，`sae_id` 可省略。

正式实验建议填写所有 `expected_*` 字段。加载器会把权重配置规范为 `SAEManifest`；任何
明确的不一致都会在模型前向前失败，而不是静默使用错误特征空间。

## 实验插件接入

实验插件把 SAE 声明为资源引用，不直接导入 `SAELensLoader`：

```python
from dataclasses import dataclass, field

from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model.capability import Capability

plugin = Plugin("exp_feature_stability", "0.1.0")


@dataclass(frozen=True)
class FeatureConfig:
  sae: str = field(metadata={"description": "resources 中的 SAE 资源名。"})
  layer: int = field(metadata={"description": "基础模型的零基层索引。"})
  top_k: int = field(
      default=64, metadata={"description": "候选特征数量。"})


@plugin.component(
    "analyzer",
    "sae_feature_stability",
    config=FeatureConfig,
    references={"sae": "sae"},
    requires=(Capability.ACTIVATION_READ,),
)
def build_analyzer(config, context):
  return FeatureStabilityAnalyzer(
      sae=context.resource("sae"),
      layer=config.layer,
      top_k=config.top_k,
  )
```

对应 Analyzer 配置通过资源名引用：

```yaml
analyzers:
  - type: exp_feature_stability.sae_feature_stability
    config:
      sae: target_sae
      layer: 10
      top_k: 64
```

组件声明中的 `references={"sae": "sae"}` 使宿主在构造 Analyzer 前完成类型检查、依赖
排序和生命周期托管。Analyzer 不能关闭注入的 SAE；`ComponentSession` 会在运行结束时
逆序释放资源。

## 直接 API

```python
from stegopot.infrastructure.integrations.sae import (
    SAELensLoader,
    build_sae_feature_intervention,
    evaluate_reconstruction,
)
from stegopot import TensorRef

sae = SAELensLoader(
    source="your-release",
    sae_id="your-sae-id",
    device="cuda",
    dtype="bfloat16",
    expected_model_id="your/model-id",
    expected_hook_name="your/hook-name",
    expected_input_width=3584,
).load()

features = sae.encode(activation)
report = evaluate_reconstruction(sae, activation)
target_ref = TensorRef(layer=19, component="resid_post", token=-1)
intervention = build_sae_feature_intervention(
    intervention_id="ablate-feature-123",
    target=target_ref,
    sae=sae,
    feature_indices=(123,),
    mode="zero",
    preserve_error=True,
)
```

`preserve_error=True` 使用 `x + decode(z_modified) - decode(z_original)`。它保留 SAE 未能
重构的残差，适合隔离所选特征的干预效应；同时仍需设置纯重构控制组，测量插入 SAE 本身
造成的行为变化。

## 最低验证要求

公开 SAE 进入正式实验前至少检查：

1. `SAEManifest` 的模型、hook、输入宽度和版本记录完整。
2. 在目标数据分布上报告 MSE、relative MSE、cosine、explained variance、mean L0。
3. 比较原模型、纯 SAE 重构和保留重构误差的特征干预三组行为。
4. 特征发现集与验证集隔离，避免在同一批样本上选择并检验特征。
5. 对随机特征、随机层和等规模特征集合设置负对照。
6. 在不同提示模板、秘密值和随机种子上报告稳定性，不只展示单个成功样本。

公开 SAE 的加载接口与 release 约定以
[SAE Lens 官方仓库](https://github.com/decoderesearch/SAELens)为准。
