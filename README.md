<p align="center">
  <img src="docs/assets/stegopot-icon.png" alt="StegoPot" width="128">
</p>
<h1 align="center">StegoPot</h1>
<p align="center"><strong>面向多智能体隐写、隐蔽通信与共谋现象研究的开放实验框架</strong></p>
<p align="center">配置驱动 · 信息流约束 · 配对反事实 · 全过程审计 · 插件化扩展</p>

**当前版本：1.0.0 · 插件 API：1.4 · Python：3.11+**

StegoPot 用一套稳定接口组织多智能体通信实验。研究者只需编写 YAML/JSON 配置，
即可声明节点、模型、定向拓扑、环境、信道干预、检测器、奖励、评价器和受控工具；
框架负责预检、调度、信息投影、证据记录、失败处理、封印核验与指标复算。

项目的核心定位是**标准实验基础设施**，不是某一篇论文的复现仓库。具体威胁假设、
诱因、提示词、数据集、隐写协议和实验结论应由配置或独立插件提供。这样可以在不修改
内核的情况下复现已有工作，也可以系统比较新的多 Agent 隐蔽交互现象。

## 可以做什么

| 能力 | 用途 |
| --- | --- |
| 自定义多 Agent 拓扑 | 定义任意节点、角色和有向通信边，按同步轮次执行 |
| LLM 节点 | 每个节点独立选择兼容 Chat Completions 的模型、提示词和采样参数 |
| 连续 Session | 在同一 Session 的 Episode 间延续策略状态与节点私有标量反馈 |
| 类型化信息流 | 明确区分公开、节点私有、秘密载荷、解码私有、监控可见、评价专用和研究专用信息 |
| 双模式通信 | 区分普通/自发研究的 `opaque` 载体与显式 codec 产生的 `instrumented` 载体 |
| 核心隐写能力 | 通过内置 StegoKit 适配器编码、传输并从实际接收文本恢复比特 |
| 信道与检测 | 对公开正文实施阻断、替换或插件化干预，并运行规则/LLM 检测器 |
| 激励闭环 | 使用逐轮公开证据奖励和 Episode 结束后的中央结果奖励 |
| 受控节点工具 | 按节点允许列表调用插件工具，结果只在下一轮返回调用节点 |
| 配对反事实 | 固定源消息正文与哈希，只改变信道、检测器或奖励处理条件 |
| 标准指标 | 统计恢复率、BER、嵌入覆盖率、bits/token、检测混淆矩阵、AUROC 与任务效用 |
| 可核验证据 | 保存研究/公开双日志、源码指纹、计划清单、威胁模型、子试验封印和根封印 |
| 离线复算 | 验证封印与当前插件源码后，从原始结果重新计算逐试验及汇总指标 |
| 热插拔扩展 | 通过装饰器注册 scenario、policy、tool、codec、detector、reward 等 12 类组件 |

StegoPot 1.0 可以正式运行以下类型的研究：

- 普通多 Agent 协作、竞争与定向通信基线；
- 明确使用隐写算法的受控通信和鲁棒性实验；
- 给 LLM 奖励、私有信息或工具后观察其通信行为；
- 同一真实载体在无干预、净化、阻断和检测条件下的配对比较；
- 隐写通信成功率、检测性能和任务效用之间的权衡；
- 自定义论文复现插件或新实验协议的批量执行与证据归档。

## 科学边界

框架会记录发生了什么，但不会替研究者自动证明行为的动机。

- `instrumented` 表示正文由受控 codec 明确生成，可以作为隐写正标签。
- `opaque` 表示框架不知道消息来源，不能仅凭比特恢复就宣称 LLM 自发共谋。
- 脚本策略、重放正文和工具编码结果都会被明确区分，不能冒充模型自然生成。
- 检测指标只在存在有效标签时有意义；AUROC 需要同时存在正负样本。
- 结论仍需足够重复、随机种子、合理对照、统计分析和人工审查。

## 架构

```text
用户配置 / 第三方插件
          |
          v
bootstrap     配置入口、预检、组件组装、生命周期、CLI、指标复算
          |
          v
application   多 Agent 调度、观察投影、通信管线、反事实编排、评价
          |
          v
domain        稳定接口与不可变领域模型
          ^
          |
infrastructure 模型、StegoKit、检测器、工具审计、配置、日志和封印实现
```

依赖方向受约束：`domain` 不依赖外层，`application` 只依赖领域契约，
`infrastructure` 实现契约，`bootstrap` 是唯一组合根。第三方插件应依赖
`stegopot.domain.interface` 和 `stegopot.domain.model`，不要导入内部运行器。

主要目录：

```text
stegopot/
  domain/
    interface/          Policy、Substrate、Tool、Codec、Detector、Plugin 等接口
    model/              动作、消息、计划、信息、通信、工具、威胁模型等数据
  application/
    engine/             节点、路由、同步运行器、通信处理管线和预算检查点
    services/           场景展开、反事实、Session、奖励、指标和威胁模型编译
  infrastructure/
    llm/                LLM 策略、动作解析、客户端与调用审计
    integrations/       StegoKit 适配
    tools/              通用工具审计包装
    detectors/          基础检测器
    substrates/         默认通信环境和信道变换
    plugins/            插件发现、版本和 Schema 校验
    recorders/audit/    双日志、查询、哈希链、封印与完整性验证
    settings/           配置、工作区、环境文件和资源诊断
  bootstrap/experiments 配置 API、CLI、预检、运行和离线复算
configs/                用户本地实验配置；仓库只跟踪说明文件
docs/                   架构、内核、插件和威胁模型文档
```

## 安装

在项目根目录使用当前虚拟环境：

```powershell
python -m pip install -e .
```

需要内置 StegoKit 和本地 Transformers 模型时：

```powershell
python -m pip install -e ".[stego]"
```

初始化一个与安装目录独立的实验工作区：

```powershell
python -m stegopot init D:\Research\my-stegopot-study
```

工作区约定：

```text
my-stegopot-study/
  .env               本地凭证，不提交版本控制
  configs/           用户实验 YAML/JSON
  outputs/           每次运行生成一个不可覆盖的证据目录
```

## 最小实验

将以下内容保存为工作区 `configs/communication.yaml`：

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

运行前先做纯预检，再执行：

```powershell
python -m stegopot validate communication --workspace D:\Research\my-stegopot-study
python -m stegopot run communication --workspace D:\Research\my-stegopot-study
```

`validate` 不构造模型、不发网络请求。`doctor` 会额外检查本地 StegoKit 模型文件，
同样不会下载权重或测试远程账户。

## 接入 DeepSeek

在工作区 `.env` 中保存密钥：

```dotenv
DEEPSEEK_API_KEY=你的实际密钥
```

配置中只写环境变量名，不写密钥值：

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

模型请求、原始响应、解析动作、消息路由和实际投递都进入研究审计。凭证不会写入
配置清单或日志。远程请求是否成功仍取决于账户、网络和服务端模型能力。

## 类型化信息流

新实验应使用 `information` 声明跨组件信息，而不是把所有材料混入
`shared_context` 或 `node_contexts`：

```yaml
scenario:
  type: core.explicit
  config:
    task: "评估隐蔽协作"
    nodes: []  # 实际配置中填写节点
    edges: []
    information:
      public_rules:
        class: public
        value: {language: zh}
      sender_secret:
        class: secret_payload
        value: "101101"
        visible_to: ["node:sender", evaluator, research_audit]
        description: "发送节点需要传递的中央标注比特"
      decoder_key:
        class: decoder_private
        value: {key_id: shared-01}
        visible_to: ["node:receiver", evaluator, research_audit]
      monitor_reference:
        class: monitor_visible
        value: {baseline: clean}
```

标准类别：

| 类别 | 默认/允许语义 |
| --- | --- |
| `public` | 可授权所有节点、环境、检测、评价和审计主体 |
| `agent_private` | 必须显式指定一个或多个 `node:<id>`，可同时授权中央评价 |
| `secret_payload` | 必须显式指定发送节点，不允许交给 Detector、Reward 或公开审计 |
| `decoder_private` | 必须显式指定接收节点，不允许交给 Detector、Reward 或公开审计 |
| `monitor_visible` | 默认只给 Detector、Evaluator 和研究审计 |
| `evaluator_only` | 默认给 Evaluator、OutcomeReward 和研究审计 |
| `research_only` | 只给研究审计，不进入任何运行组件 |

可用组件主体为 `substrate`、`detector`、`reward`、`outcome_reward`、`evaluator`、
`public_audit`、`research_audit`；节点主体写作 `node:<id>`。类别定义的是授权上限，
`visible_to` 只能缩小或在允许范围内选择，不能把秘密扩大授权给监控器。

预检生成 `stegopot.threat-model/2`，其中只保存资产类别、读取者和含值声明摘要，
不复制真实信息值。运行时由宿主按主体投影，默认拒绝未授权信息。

## 隐写通信

StegoPot 提供两种不会混淆的通信来源：

1. `opaque`：普通脚本或 LLM 消息。框架不预先知道是否隐写，适合研究自发行为。
2. `instrumented`：`core.codec_sender` 调用受控 codec 后自动生成。记录 codec ID、
   输入比特数、实际消耗比特数、载体 token 数和正文哈希，但不把秘密放入消息。

内置 StegoKit 资源示意：

```yaml
resources:
  stego:
    type: core.stegokit
    config:
      model_path: D:/Models/local-causal-model
      algorithm: ac
      generation:
        max_new_tokens: 128

# 节点 policy 分别使用：
# core.codec_sender:   {codec: stego, target: receiver, active_round: 0}
# core.codec_receiver: {codec: stego, active_round: 1}
```

解码端只对**信道处理后实际收到的文本**重新分词，不接收编码端隐藏 token ID。
StegoKit 加载本地模型时启用 `local_files_only` 并关闭远程代码信任。

`core.stego_metrics` 要求中央 `truth.secret_bits` 和 `truth.receiver`，输出：

- 比特恢复、长度完整性和 BER；
- payload/consumed bits、嵌入覆盖率、载体 token 数和 bits/token；
- 载体投递率；
- 检测混淆矩阵、TPR、FPR、precision 和 AUROC；
- 可选 `truth.expected_answers` 对应的任务效用；
- 配对反事实处理组结果。

`opaque` 载体默认不参与正负样本统计。若中央数据集已为当前 Trial 提供可靠标签，可在
`truth.stego_label` 写入布尔值；未标注观察会单独计入 `security.unlabeled`。

## 配对反事实

`core.counterfactual` 先执行一个源 Trial，再将其中唯一真实消息正文固定到多个处理分支。
分支发送者不会再次调用原策略或模型；报告记录源 Trial、消息 ID、正文 SHA-256、
配对组和 treatment ID。可改变的处理层是 `channels`、`detectors` 和 `rewards`，
任务、拓扑、策略、环境、真值等字段默认必须与源试验一致。

```yaml
scenario:
  type: core.counterfactual
  config:
    source:
      id: source
      task: "生成并传递一个载体"
      max_rounds: 2
      nodes:
        - id: sender
          policy: {type: core.scripted, config: {actions: [{kind: message, content: "carrier", target: receiver}]}}
        - id: receiver
          policy: {type: core.echo}
      edges: [[sender, receiver]]
    carrier: {sender: sender, recipient: receiver}
    group_id: carrier-ablation
    treatments:
      - id: raw
        channels: []
      - id: blocked
        channels: [{type: core.block}]
```

该机制适合做载体净化、检测器消融和信道鲁棒性比较，避免不同模型采样产生的正文差异
污染处理效应。

## 节点工具

节点只可调用其 `tools` 映射中声明的别名。工具动作为：

```json
{
  "kind": "tool_call",
  "content": null,
  "target": null,
  "metadata": {},
  "tool_call": {
    "tool": "codec_tool",
    "operation": "encode",
    "arguments": {"text": "..."}
  }
}
```

宿主先检查节点授权、调用次数和 JSON 大小，再创建 `ToolRequest`。`ToolResult` 只在
下一轮的 `observation.tool_results` 返回调用节点，不作为公开消息广播。请求、响应、
失败、调用者和调用 ID 进入研究审计，未知工具别名直接违反契约。

## 插件开发

插件 API 1.4 支持以下组件类型：

`scenario`、`policy`、`llm`、`substrate`、`channel`、`codec`、`detector`、
`reward`、`outcome_reward`、`evaluator`、`tool`、`audit`。

最小通用工具插件：

```python
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model import ToolResult

plugin = Plugin("my_lab", "0.1.0")

class Calculator:
    """只实现声明的确定性运算。"""

    def execute(self, request):
        if request.operation != "double":
            raise ValueError("不支持的操作")
        return ToolResult(request.arguments["value"] * 2)

    def close(self):
        pass

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
    return Calculator()

def entrypoint():
    return plugin()
```

发布包中注册入口：

```toml
[project.entry-points."stegopot.plugins"]
my_lab = "my_lab.plugin:entrypoint"
```

实验配置需要在顶层显式允许插件：

```yaml
plugins:
  - id: my_lab
    version: ">=0.1,<1"
```

每个工厂只得到经过 Schema 校验的自身配置和受限 `BuildContext`。资源依赖通过
`references` 声明，凭证通过 `credentials` 声明；不得从全局容器、环境或其他节点
读取未授权数据。`evaluator` 必须无资源、无凭证，以保证可离线复算。

组件 ID 必须使用插件命名空间，例如 `my_lab.calculator`。同一运行的注册表冻结后不可
修改；热插拔发生在两次实验之间，不是在执行中替换代码。

完整约定见 [插件开发](docs/plugin_development.md)。

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
python -m stegopot plugins list
python -m stegopot plugins inspect core
python -m stegopot schema --component core.llm
```

`events` 默认先核验封印且只读公开视图。研究视图包含计划、真值、模型回复、工具输出
和完整失败信息，只有明确使用 `--scope research` 时才读取。独立保存根 `seal.json`
的 SHA-256 后，可通过 `--expected-seal-sha256` 检测整组证据连同封印一起被替换。

## Python API

```python
from stegopot.bootstrap.experiments.api import (
    prepare_file,
    recompute_directory,
    run_file,
)

prepared = prepare_file("study", workspace="D:/Research/my-stegopot-study")
print(len(prepared.plan.trials), prepared.threat_model.schema_version)

report, directory = run_file(
    "study",
    workspace="D:/Research/my-stegopot-study",
)
if report["status"] != "completed":
    raise RuntimeError(report["errors"])

verification = recompute_directory(directory)
assert verification["verified"]
```

`prepare_file`、CLI 和 `run_file` 使用同一预检与组装链路。低层 `MultiAgentBuilder`
适合嵌入自定义应用，但不会自动生成标准威胁模型、实验清单和封印工件。

## 配置约定

顶层配置字段：

| 字段 | 作用 |
| --- | --- |
| `schema_version` | 必填，当前固定为字符串 `"1"` |
| `scenario` | 必填，生成完整 `ExperimentPlan` 的场景组件 |
| `plugins` | 允许加载的已安装插件和可选版本范围 |
| `resources` | 可复用的 `llm`、`codec` 或 `tool` 资源 |
| `policies` | 按节点 ID 覆盖场景策略 |
| `topology` | 可选全局拓扑边覆盖 |
| `channels` / `detectors` / `rewards` | 默认公开处理管线 |
| `outcome_rewards` | Episode 结束后的中央反馈组件 |
| `evaluators` | 中央纯评价器 |
| `audit_sinks` | 附加审计接收器；不能关闭宿主审计 |
| `threat_model` | 策略历史、检测器公共上下文和审计投影声明 |
| `runtime` | 调用、轮数、时间、token、消息和上下文预算 |

组件统一写法：

```yaml
type: plugin.component
config:
  parameter: value
```

所有配置 Schema 都拒绝未知字段；YAML 重复键、锚点和别名被拒绝。真实密钥必须只通过
环境变量引用。`configs/`、`.env`、`outputs/` 和本地测试均已加入 `.gitignore`。

## 执行顺序

```text
配置读取
 -> 插件允许列表与 JSON Schema 校验
 -> 纯预检钩子
 -> Scenario 生成固定计划
 -> 信息流与威胁模型编译
 -> manifest 写入
 -> Trial / Session / Episode
      -> 节点局部观察
      -> Policy 决策或受控 Tool 调用
      -> 拓扑路由
      -> Substrate
      -> Channel
      -> 最终公开文本 Detector
      -> Reward
      -> 下一轮
 -> OutcomeReward
 -> Evaluator
 -> 汇总、双日志和关联封印
```

每个 Episode 都重置环境、收件箱和上一动作。只有声明允许时，策略不透明状态和节点自己的
标量反馈才会延续到同一 Session 的下一 Episode；不会跨 Session 或写入报告。

## 输出与审计

一次成功运行产生：

```text
outputs/<run-id>/
  manifest.json             stegopot.manifest/3：配置、固定计划、插件和源码指纹
  threat-model.json         stegopot.threat-model/2：有效视图、边界和信息流摘要
  experiment-report.json    stegopot.report/1：逐试验结果、指标和汇总
  report.md                 面向阅读的摘要
  research.jsonl            完整研究事件哈希链
  public.jsonl              默认拒绝未知事件的最小公开投影哈希链
  seal.json                 根工件与双日志终点封印
  <trial-id>/
    result.json
    research.jsonl
    public.jsonl
    seal.json
```

`verify` 检查：

- 双日志序号、前序哈希和终点哈希；
- 根工件和每个子 Trial 工件的文件摘要；
- 根报告与子结果一致；
- 实际 Trial 声明与预注册计划逐项一致；
- 威胁模型的计划、拓扑和类型化信息流摘要一致。

`recompute` 在上述检查后还会验证当前启用插件的 Python 源码指纹，并重新构造无资源
Evaluator，从封印的固定计划和实际结果计算指标。它不会运行节点、请求模型、调用 codec
或修改原目录。框架哈希链不是数字签名、可信时间戳或防篡改存储；高保证实验应独立保存
根哈希并使用只写介质或外部签名系统。

## 运行限制

常用 `runtime` 默认值：

| 参数 | 默认值 | 含义 |
| --- | ---: | --- |
| `max_model_calls` | 64 | 整组模型调用上限 |
| `max_tool_calls` | 256 | codec 与通用 Tool 的整组调用上限 |
| `max_output_tokens` | 1024 | 单次宿主模型请求输出上限 |
| `max_total_tokens` | 1000000 | 服务端已报告累计 token 上限 |
| `max_rounds` | 100 | 场景可声明的最大轮数 |
| `max_trials` | 1000 | 独立 Trial 与全部 Episode 总上限 |
| `max_seconds` | 3600 | 协作式执行截止时间 |
| `max_message_bytes` | 65536 | 单条公开正文 UTF-8 大小上限 |
| `max_context_bytes` | 1000000 | 观察、模型输入和工具数据 JSON 大小上限 |

还可设置 `max_model_calls_per_trial`、`max_model_calls_per_node`、
`max_tool_calls_per_trial` 和 `max_tool_calls_per_node`。调用在开始前原子预占额度，失败调用
仍计数。取消和截止是协作式的，不能强制终止已经进入第三方 Python 代码或网络请求的调用。

## 安全边界

当前信任模型是 `trusted_in_process`：插件与内核运行在同一个 Python 进程中。

框架能够保证通过宿主接口提供的数据按声明投影，并限制组件类型、资源引用、凭证注入、
消息身份、工具允许列表、调用预算和公开审计内容；但**不能阻止恶意插件直接访问文件、
网络、环境变量、进程内存或无限占用 CPU/GPU**。因此 StegoPot 1.0 是轻量级实验框架，
不是操作系统安全沙箱，也不是分布式执行平台。

处理不可信第三方插件时，应在容器、独立账户或虚拟机中运行，并由外部系统限制网络、
文件、CPU、内存和 GPU。框架内核保持轻量，把硬隔离交给部署层。

## 文档

- [文档索引](docs/README.md)
- [架构与依赖方向](docs/architecture.md)
- [内核控制与审计](docs/kernel.md)
- [威胁模型与信息边界](docs/threat_model.md)
- [插件开发](docs/plugin_development.md)
- [使用指南](docs/usage.md)

## 许可证

StegoPot 使用 [Apache License 2.0](LICENSE)。内置的 StegoKit 上游源码保留其原始许可证，
详见 `stegopot/infrastructure/vendor/stego-kit/LICENSE`。
