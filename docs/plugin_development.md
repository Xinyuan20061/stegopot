# 开放接口与扩展开发

## 核心定位

StegoPot 核心提供多节点运行、隐写编解码、信息隔离、信道干预、基础检测与审计。
扩展实现具体研究假设，不应复制框架的运行循环、预算、日志和报告逻辑。

### 可注册接口

| kind | 最小方法 | 职责与可见信息 |
| --- | --- | --- |
| scenario | plan(seed) | 纯计划生成，返回 ExperimentPlan，不运行模型 |
| policy | initial_state / step / close | 节点局部观察与内部状态，返回动作和新状态 |
| llm | generate / close | 模型消息与调用参数；只有供应商可获授权凭证 |
| codec | encode / decode / close | 私有输入、实际公开载体、显式预共享材料 |
| tool | execute / close | 节点允许列表中的通用操作；结果只回到调用节点 |
| substrate | reset / observe / step / state / close | 世界状态和局部投影，不应自行发起模型请求 |
| channel | transform(message) | 只改正文或返回 None 阻断，不改通信身份 |
| detector | reset / detect / close | 只读取最终公开消息，不获得秘密与真值 |
| reward | score(request) | 受限公开证据和检测信号到节点奖励；不直接修改策略 |
| outcome_reward | score(request) | 中央 Episode 结果和 truth 到下一 Episode 节点标量 |
| evaluator | evaluate(trial,result) / summarize(records) | 中央真值评分，必须保留失败和跳过样本 |
| audit | emit(event) | 明确启用的研究审计接收器，不替代宿主强制日志 |

接口集中在 `stegopot/domain/interface`。无需继承所有抽象类；
实现约定的方法即可，宿主会检查方法与调用结果的关键边界。

## 装饰器注册

插件应作为自己的安装包开发，不写入核心源码。下文代码展示接口用法，
不是仓库预置实验。注册器本身没有全局副作用：

```python
from dataclasses import dataclass, field
from stegopot.domain.interface.registration import Plugin

plugin = Plugin("example", "0.1.0")

@dataclass(frozen=True)
class RewardConfig:
  points: float = field(default=1.0, metadata={"description": "每条已投递消息给予发送者的奖励"})

@plugin.component("reward", "delivery", config=RewardConfig)
def build_reward(config, context):
  """config 是已验证的数据类；context 只提供声明的能力。"""
  return DeliveryReward(points=config.points)
```

其中 `DeliveryReward` 放在扩展的应用服务层，实现 `score(request)`。
不要把业务计算放在注册函数中；注册只做参数接入和对象组装。

例如在独立目录 my-plugin 中创建以下结构：

```text
my-plugin/
  pyproject.toml
  src/stegopot_example/
    __init__.py
    application/reward.py
    bootstrap/plugin.py
```

各 Python 子目录补充 `__init__.py`。在 bootstrap/plugin.py 中放上面的注册代码，
并从自己的 application.reward 导入 DeliveryReward。后者可以实现为：

```python
from collections.abc import Mapping

from stegopot.domain.model import RewardRequest

class DeliveryReward:
  """按实际公开投递计算奖励，不访问中央真值。"""

  def __init__(self, *, points: float) -> None:
    """points 是每条投递给予发送者的奖励。"""
    self._points = points

  def score(self, request: RewardRequest) -> Mapping[str, float]:
    """request 为不可变公开证据；返回节点 ID 到本轮奖励的映射。"""
    rewards: dict[str, float] = {}
    for message in request.messages:
      node = message.sender
      rewards[node] = rewards.get(node, 0.0) + self._points
    return rewards
```

pyproject.toml 的最小安装元数据：

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "my-stegopot-plugin"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["stegopot>=1.0,<2"]

[project.entry-points."stegopot.plugins"]
example = "stegopot_example.bootstrap.plugin:plugin"

[tool.setuptools.packages.find]
where = ["src"]
```

`plugin` 实例可直接调用，导出后冻结组件列表。
短名 `delivery` 自动成为完整 ID `example.delivery`。
插件版本必须与安装包版本一致。重复 ID、API 不兼容、错误类型和未知配置字段会失败。

### 参数模式

`config=数据类` 支持 str/int/float/bool、None、Literal、可选联合、list[T]、
dict[str, Any]；每个字段必须有 `metadata.description`。
数据类默认值由构造器处理，不复制可变默认对象。
复杂约束使用 `schema=严格 JSON Schema`，与 config 互斥。
显式 schema 的对象必须拒绝未知字段，只允许文档内部引用，不访问远程模式。

### 依赖注入

```python
@plugin.component(
    "policy", "sender", config=SenderConfig,
    references={"client": "llm", "codec": "codec"},
)
def build_sender(config, context):
  """client/codec 是配置中的资源名称，context 只能解析这两个声明槽位。"""
  return SenderPolicy(
      client=context.resource("client"),
      codec=context.resource("codec"),
      node_id=context.node_id,
      audit=context.audit,
  )
```

资源必须声明在实验配置的 `resources` 中。不要直接导入 DeepSeek 客户端或
StegoKit 适配器；使用已注入接口。工厂统一接收 `(config, context)`。
插件自定义事件通过 `context.audit.emit` 写入命名空间研究记录。
工厂不能通过上下文读取未声明资源、全部环境变量或中央真实标签。

宿主拥有注入资源的关闭责任。组件只关闭自己创建的对象，不关闭注入依赖。
每个 Episode 创建新组件；不同节点不共享可变模型/codec 实例。Policy 的不透明状态
可由宿主在同一 Session 传给新 Policy 实例，因此状态不得拥有需要关闭的资源，也不得
依赖上一个 Episode 的 Substrate 或组件实例。
工厂创建过程中失败时，尚未交还宿主的部分资源由工厂自行释放。

### 供应商凭证

只有 `kind="llm"` 或 `kind="tool"` 可以声明 `credentials=("api_key_env",)`。
配置中该字段填写环境变量名称，工厂用
`context.credential("api_key_env")` 取值；不得把真实密钥写进配置。
供应商不得自动重试或自行绕过宿主发起额外请求。需要重试的研究策略必须显式声明，
并通过注入客户端逐次调用，让每次尝试都计入预算与审计。

## 实验配置

| 字段 | 含义 |
| --- | --- |
| schema_version | 当前为字符串 "1" |
| plugins | 已安装扩展允许列表，可附版本范围；未启用就不可引用 |
| scenario | 产生独立 Trial 或 Condition/Session/Episode 计划的组件引用，形式为 type/config |
| seed | 中央计划种子，不自动写入节点观察 |
| resources | 模型、codec 与通用 Tool 资源字典，按声明槽位使用 |
| policies | 按节点 ID 覆盖场景默认策略 |
| topology.edges | 覆盖场景有向边；不存在的节点会被拒绝 |
| channels / detectors / rewards | 按配置顺序执行的逐轮组件列表 |
| outcome_rewards | Episode 结束后执行的中央结果奖励组件列表 |
| evaluators | 添加中央评分器，结果按组件 ID 命名空间保存 |
| audit_sinks | 添加研究事件接收器，不能移除宿主日志 |
| threat_model | 声明策略/检测器公开视图、同进程信任前提和审计投影 |
| runtime | 调用、输出 token、轮次、试验数和软时间上限 |
| audit | 当前只支持 required=true、profile=research |

`TrialSpec`/`EpisodeSpec` 中 `task/shared_context` 共同可见，
`node_contexts[id]` 只给对应节点，`truth` 只给中央评分。
基础隐写策略使用节点私有字段 `secret_bits`、`cover`、`shared_material`；
后者包括双方预先共享的 `messages`、可选 `material/max_bits`。
不要通过共享上下文、节点 ID、拓扑选择或评分反馈意外泄露实验秘密。
插件不读取完整 ThreatModelManifest；宿主应在调用组件前完成投影。
Detector 是否读取公共实验上下文由 threat_model 显式控制，永远不通过宿主获得真值。

默认上限：64 次模型调用、每次 1024 输出 token、100 轮、1000 次试验、3600 秒。
场景轮数仍由 TrialSpec 指定，宿主上限不是自动增加轮次。
时间上限在试验、轮次、组件及模型/工具调用前后协作检查，不强制终止正在执行的插件。
工具本地计算不计入 LLM API 次数，但受独立 max_tool_calls 限制，仍须设置合理生成上限。

## 隐写与对照

新 `StegoCodec` 的 encode 返回 `Carrier` 与研究统计，
decode 只接收实际载体和预共享材料。真实 token ID 不作为隐含通道传给接收者。
核心 StegoKit 适配器从文本重新分词，无法一致往返就失败。
算法恢复属于工具结果，不能将其写成 LLM 自主推断或共谋动机的证据。

`ReplaySpec` 引用先前试验的一条唯一实际投递消息。
源试验失败或没有唯一载体时跳过对照，记录原因，不伪造源文本。
干预可通过信道组件阻断、替换正文；检测器只检查干预后的公开载体。

## 审计与失败

- threat-model.json：固定有效组件视图、信任假设、计划摘要和拓扑摘要。
- manifest.json：固定配置、展开计划、插件版本、Python 源码摘要并引用威胁模型。
- research.jsonl：完整研究事件；可含合成秘密和模型提示，不能公开。
- public.jsonl：白名单公开投影；不保证模型正文没有主动泄露信息。
- 子试验 result.json：真实结果、状态、插件评分与调用计数。
- experiment-report.json / report.md：整组研究报告，含全部分母。
- seal.json：日志终点与关联工件哈希；根报告关联各子目录封印。

资源构造、运行、评价、关闭失败都要保留；审计写入失败直接中止。
未封印日志不是完整实验结果。版本与源码摘要帮助核查，不保证 API 采样可复现。
外部模型权重和数据集应额外固定并记录；哈希链不是签名。

插件在同一 Python 进程运行，仅应安装可信代码。
热插拔指运行之间启用/停用或更换插件；升级安装包后使用新进程。
长驻进程不会自动清空 Python 模块缓存，不支持进行中的实验重载。

## 开发与验证

```powershell
python -m pip install -e D:/Research/my-plugin
python -m stegopot plugins inspect example
python -m stegopot validate my_experiment
python -m stegopot run my_experiment
```

在自己的配置中添加 `plugins: [example]` 和
`rewards: [{type: example.delivery, config: {points: 1.0}}]`。
既有 experiment 配置的节点、拓扑和任务由使用者定义；插件安装不会自动执行实验。
Python 调用者也可构建 PluginCatalog、add(plugin())，通过 prepare_file/run_file 的
catalog 参数注入；此时调用者负责登记全部依赖，框架仍校验组件契约。

新增插件至少测试：参数错误、资源声明、重复实例、节点隔离、失败状态、
资源释放、实际载体变换，以及审计校验。不要只测试成功样本。

## 1.1 预检扩展

API 1.1 引入此能力；当前 API 1.4 宿主仍可加载同一主版本内较早的插件。
组件可在装饰器增加 preflight=校验函数；数据类配置与工厂保持同一类型。
回调签名为 preflight(config, context) -> Sequence[Diagnostic]。

- context 是 PreflightContext，只提供位置、节点身份、轮数、出入邻居和当前节点私有材料副本。
- 不提供凭证、运行资源、其他节点材料或中央 truth；不得联网、构造模型或执行试验。
- error 诊断阻止运行；warning/info 随 PreparedExperiment 和 manifest 留存。
- Diagnostic 必须提供 code、path、message、hint；诊断文本不能回显秘密或原始参数。
- 宿主仅依据组件声明调度预检，不要求修改核心引擎来注册新的校验规则。

完整示例和执行停止约定见 [内核控制与审计](kernel.md)。

## 1.2 奖励证据

当前宿主默认声明插件 API 1.4，并继续接受同一主版本内较早的插件。Reward 的 `score`
接收 `RewardRequest`，新插件应优先使用以下只读属性：

| 属性 | 内容 | 明确不包含 |
| --- | --- | --- |
| `round_index` | 当前同步轮次 | Trial ID 和中央种子 |
| `actions` | 节点到 kind/target 的只读映射 | 动作正文和 metadata |
| `messages` | 实际投递的不可变 AgentMessage | 候选、阻断和干预前正文 |
| `detections` | 组件 ID、消息 ID、判定、分数和置信度 | reason、metadata、context 和 truth |
| `information` | 按 reward 主体显式授权的类型化资产 | 任何未授权资产 |

API 1.1 奖励插件仍可用 `request["messages"]`、`request["actions"]` 等键读取
JSON 副本。Reward 必须返回现有节点 ID 到有限数值的映射；宿主将多个组件结果
与 Substrate 奖励相加，并只把每个节点自己的合成标量投影到下一轮观察。

策略 step 的参数名称应为 observation、prev_state，宿主使用关键字调用；
返回 (AgentAction, next_state)。内部状态仍是不透明对象，不要求 JSON 化。
动作字段与元数据必须符合标准序列化契约，不能把不可序列化对象交给审计层。

## 1.3 Episode 结果奖励

`outcome_reward.score(request)` 接收 `EpisodeOutcomeRequest`。它只在受信任的中央阶段
运行，可读取 `condition_id`、`session_id`、`episode_id`、实际 `result` 和当前
Episode 的 `truth`。`result` 与 `truth` 属性每次访问都返回独立只读 JSON 副本。
API 1.4 还提供按 `outcome_reward` 主体投影的只读 `information` 属性。

返回值必须是当前 Episode 节点 ID 到有限数值的映射。宿主把多个 OutcomeReward
结果与逐轮累计奖励相加，只在同一 Session 的下一 Episode 首轮向对应节点投影标量。
插件不能从该接口访问 Policy 状态，也不能返回提示、答案、检测理由或任意对象。
结果奖励失败会使当前 Episode 失败并阻止该 Session 继续延续状态。
