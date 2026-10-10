# 插件开发

## 组件类型

插件 API 1.5 同时服务两种配置：

| 类别 | kind |
| --- | --- |
| 通用研究 | `model_adapter`、`dataset`、`transform`、`validator`、`scenario`、`analyzer`、`probe`、`intervention`、`metric`、`reporter` |
| 多 Agent | `scenario`、`policy`、`llm`、`substrate`、`channel`、`codec`、`detector`、`reward`、`outcome_reward`、`evaluator`、`tool`、`audit` |

v1 的 `scenario` 实现 `plan(seed)`；v2 的 `scenario` 实现 `setup/run/teardown`。
配置版本决定宿主使用哪种契约。

## 注册

```python
from dataclasses import dataclass, field

from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model.capability import Capability

plugin = Plugin("my_study", "0.1.0")


@dataclass(frozen=True)
class AnalyzerConfig:
  top_k: int = field(
      default=20,
      metadata={"description": "分析结果保留的候选数量。"},
  )


@plugin.component(
    "analyzer",
    "attribution",
    config=AnalyzerConfig,
    requires=(Capability.ACTIVATION_READ, Capability.GRADIENT_READ),
)
def build_analyzer(config, context):
  """工厂只组装对象，不执行数据生成或模型前向。"""
  del context
  return AttributionAnalyzer(top_k=config.top_k)
```

数据类字段必须提供中文 `metadata.description`。复杂配置可使用
`schema=严格 JSON Schema`；对象 schema 必须拒绝未知字段。

## 资源与凭证

```python
@plugin.component(
    "scenario",
    "online_defense",
    references={"probe": "probe"},
    requires=(Capability.TOKEN_STEP_CONTROL, Capability.ACTIVATION_WRITE),
)
def build_scenario(config, context):
  return OnlineDefenseScenario(probe=context.resource("probe"))
```

配置字段 `probe` 的值是 `resources` 中的资源名。工厂只能读取自己声明的 slot。
循环引用、类型不匹配和缺失资源在执行前失败。

只有 `llm`、`model_adapter` 和 `tool` 能声明 `credentials`。配置填写环境变量名，
工厂使用 `context.credential(field_name)` 取得单个值，不能读取完整环境。

## ModelAdapter

新的白盒后端至少实现：

- `adapter_id`、`model_id` 和 `capabilities`；
- `resolve(TensorRef)`；
- `forward(...)`；
- `open_generation_session(...)`；
- `close()`。

适配器只处理后端结构、张量和生成控制。归因公式、Probe 训练和实验标签不应写进适配器。
不支持的 capability 不得声明；未知架构地址必须显式失败。

## 数据和场景

- DatasetSource 产生通用 `Sample`。
- Transform 可以把一个样本展开为多个样本。
- Validator 返回错误文本序列。
- ResearchScenario 通过 `context.runtime` 使用模型，通过 `context.artifact_store` 保存额外工件。
- Analyzer 消费样本与场景输出。
- Metric 返回有限标量。
- Reporter 汇总记录，不修改已有结果。

中央标签放在 `Sample.target` 或插件私有 input 结构中，只在研究边界使用。

## 包声明

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "my-stegopot-plugin"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["stegopot>=2,<3"]

[project.entry-points."stegopot.plugins"]
my_study = "my_study.bootstrap:plugin"
```

entry point 名、`plugin_id` 和安装包声明必须一致。StegoPot 2.0 保持插件 API 1.x
向后兼容；插件不应假设所有模型后端都有白盒能力。

## 生命周期约定

- 插件导入时只声明组件，不加载模型、读取数据或联网。
- preflight 是纯函数，不构造资源。
- 工厂拥有自己创建对象的失败清理责任；交给宿主后由 ComponentSession 逆序关闭。
- 组件不能关闭注入资源。
- RuntimeEvent 不携带 activation 原值。
- 同进程插件属于可信代码，不是安全沙箱。

本地验证：

```powershell
python -m pip install -e D:\Research\my-plugin
stegopot plugins inspect my_study
stegopot validate experiment --workspace D:\Research\workspace
stegopot run experiment --workspace D:\Research\workspace
```
