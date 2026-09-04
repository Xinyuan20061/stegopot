<p align="center">
  <img src="docs/assets/stegopot-icon.png" alt="StegoPot" width="144">
</p>
<h1 align="center">StegoPot</h1>
<p align="center">可配置拓扑、内置隐写能力、开放组件接口与全过程审计的多智能体实验框架</p>

StegoPot 为多 Agent 隐写研究提供可复用的实验基础设施。使用者定义任务、节点、
通信关系和评价方法，框架负责执行、信息投影、资源注入、预算约束与审计留存。

项目交付的是**框架，不是预置实验集合**：不附带论文专用场景、共谋协议、历史结果或 Console。
已有能力可以通过配置组合；新的策略、算法和实验设计通过独立插件接入。

**框架版本：0.7.0 · 插件接口版本：1.0 · Python：3.11+**

## 目录

- [框架能力](#框架能力)
- [项目结构](#项目结构)
- [安装](#安装)
- [首次运行](#首次运行)
- [接入模型](#接入模型)
- [使用核心隐写](#使用核心隐写)
- [配置与命令约定](#配置与命令约定)
- [Python 调用](#python-调用)
- [组件接口约定](#组件接口约定)
- [开发扩展](#开发扩展)
- [结果与审计](#结果与审计)
- [边界与常见问题](#边界与常见问题)
- [开发规范与许可](#开发规范与许可)

## 框架能力

| 能力 | 可以完成的工作 | 前提与边界 |
| --- | --- | --- |
| 多 Agent 交互 | 自定义节点、角色、定向通信边、轮次和局部状态 | 当前是同步轮次调度，不是分布式执行系统 |
| 模型驱动决策 | 为不同节点设置模型、提示、采样参数和历史保留 | 使用兼容 Chat Completions 的服务，或实现 LLMClient |
| 隐写通信 | 编码私有比特、传递公开文本、从实际接收载体恢复比特 | 内置 StegoKit；通常需要本地语言模型及隐写依赖 |
| 信息隔离 | 分离公开任务、节点私有材料、预共享材料与中央真值 | 可信组件的接口约束，不是恶意代码沙箱 |
| 信道干预 | 阻断或替换正文，扩展新的文本变换 | 不允许修改消息身份或另加传输元数据 |
| 检测、奖励与评价 | 组合公开消息检测、节点反馈和中央评分 | 奖励计算不自动训练模型；专用算法由插件提供 |
| 重复与配对运行 | 重复执行显式场景，按计划重放前序实际消息 | 复杂配对设计由场景插件生成，不能凭空补造载体 |
| 审计与复核 | 保存配置、计划、真实调用、消息、失败和关联封印 | CLI 与文件级 API 强制审计；完整研究记录不可直接公开 |
| 开放扩展 | 十类组件统一注册、校验和按需构造 | 插件需要安装并显式启用，不能覆盖核心组件 |

**StegoKit、基础检测、信息隔离和审计属于核心能力。**
具体研究假设、论文协议、任务奖励和专用评价属于使用者的实验或扩展，不写死在内核中。

## 项目结构

```text
stegopot/                       Python 框架包
  domain/
    interface/                  抽象契约、插件声明、装饰器
    model/                      消息、动作、拓扑、计划与试验数据
  application/
    engine/                     节点、轮次、路由、观察与处理管线
    services/                   通用实验用例与汇总
  infrastructure/
    settings/                   配置、工作区、环境快照
    plugins/                    安装发现与组件校验
    llm/                        模型适配、策略、提示、调用审计
    integrations/stegokit/      核心 StegoKit 适配与载体编解码
    vendor/stego-kit/            固定版本上游子模块
    substrates/                 环境和信道实现
    detectors/                  基础检测器
    recorders/audit/             日志、报告、脱敏与完整性核验
  bootstrap/                    依赖组装、Python 入口与命令行
configs/                        用户实验配置；初始只有目录说明
docs/                           架构、使用和扩展开发文档
pyproject.toml                  安装与打包声明
.env.example                   不含真实凭证的环境文件说明
```

源码遵守 `bootstrap -> application / infrastructure -> domain` 的依赖方向。
插件实现可以有自己的分层，但不应反向依赖框架的具体引擎或基础设施。

工作区还可以有本地 `.env`、`.venv/` 和运行时生成的 `outputs/`。
它们不属于框架业务层，也不提交研究仓库。
安装工具可能再次生成 `*.egg-info/`；这是可再生的打包元数据，不应手动编辑或提交。

## 安装

### 从仓库安装

```powershell
git clone --recurse-submodules https://github.com/Xinyuan20061/stegopot.git
cd stegopot
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m stegopot --version
```

已有虚拟环境时跳过创建步骤。本文后续的 `python` 都指安装了 StegoPot 的解释器；
在 Windows 中也可始终用 `.\.venv\Scripts\python.exe` 替代，避免调用其他环境。

Linux/macOS 使用 `.venv/bin/python`。已有源码但缺少子模块时，在仓库根目录运行：

```shell
git submodule update --init --recursive
```

普通规则通信、HTTP 模型请求、配置与审计仅依赖轻量核心包。
本地隐写能力另外安装可选依赖：

```shell
python -m pip install -e ".[stego]"
```

这会安装声明的 NumPy、PyTorch、Transformers 等依赖，但**不会下载模型权重**。
模型目录、tokenizer、硬件资源和算法参数由使用者准备。
通过仓库 ZIP 获取源码时，不能假定其中包含子模块；构建分发包前必须补齐 StegoKit 源码。

### PyCharm

- 解释器选择当前项目的 `.venv/Scripts/python.exe`。
- 工作目录选择实验工作区根目录；在本仓库内使用时就是仓库根目录。
- 使用模块名称 `stegopot`，参数如 `validate communication` 或 `run communication`。
- 不把包内的 `__main__.py` 当普通脚本运行。

## 首次运行

### 编写自己的配置

将用户定义的 YAML 或 JSON 放入工作区 `configs/`。
以下是说明格式的最小通信配置，可作为 `configs/communication.yaml` 的起点；
仓库本身不会自动生成该文件，也不会预置此实验。

```yaml
schema_version: "1"
scenario:
  type: core.explicit
  config:
    task: 将状态消息发送给接收者。
    nodes:
      - id: sender
        role: 发送者
        policy:
          type: core.scripted
          config:
            actions:
              - kind: message
                target: receiver
                content: status-ready
      - id: receiver
        role: 接收者
        policy:
          type: core.echo
    edges:
      - [sender, receiver]
    max_rounds: 2
```

该配置只使用规则节点，不调用模型，也不证明隐写或共谋现象。
`core.explicit` 根据声明生成计划；`core.scripted` 返回预设动作；`core.echo` 根据收件箱返回答案。
边 `[sender, receiver]` 只允许该方向通信，不自动生成反向边。

### 校验、运行和查看结果

在工作区根目录执行：

```shell
python -m stegopot list
python -m stegopot validate communication
python -m stegopot run communication
```

`validate` 检查配置、组件和计划，不构造模型客户端，不发送模型请求。
`run` 执行同样的预检后开始实验，输出本次结果目录和状态。

默认结果位置为 `outputs/<run-id>/`。阅读其中的 `report.md`、
`experiment-report.json`，需要复核时运行：

```shell
python -m stegopot verify outputs/<run-id>
```

`<run-id>` 应替换为本次命令实际输出的目录名，而不是文字占位符。

### 使用独立工作区

安装包与实验工作区可以完全分开，不必把配置写入 `site-packages` 或框架源码目录：

```shell
python -m stegopot init D:/Research/my-workspace
python -m stegopot list --workspace D:/Research/my-workspace
```

`init` 只创建空 `configs/`，重复执行不会覆盖现有 `.env` 或生成默认实验。
在该工作区加入自己的配置后：

```shell
python -m stegopot run communication --workspace D:/Research/my-workspace
```

默认凭证来自该工作区的 `.env`，默认输出属于该工作区的 `outputs/`。
框架不切换进程工作目录，也不修改安装包内容。

## 接入模型

### DeepSeek 与兼容服务

内置 `core.chat_completions` 负责 HTTP 传输，`core.llm` 负责节点决策。
不需要安装旧 DeepSeek 实验扩展。工作区 `.env` 中设置：

```dotenv
DEEPSEEK_API_KEY=填写你的真实密钥
```

模型名称由资源配置明确指定。下面是一份双 LLM 节点配置；使用前必须将
`REPLACE_WITH_YOUR_MODEL` 换成账户实际可用的模型名称。运行会产生服务端费用。

```yaml
schema_version: "1"
resources:
  model:
    type: core.chat_completions
    config:
      base_url: https://api.deepseek.com
      model: REPLACE_WITH_YOUR_MODEL
      api_key_env: DEEPSEEK_API_KEY
      timeout: 60
      response_format: json_object
scenario:
  type: core.explicit
  config:
    task: 发送一个简短问题，再由接收者回答。
    nodes:
      - id: sender
        policy:
          type: core.llm
          config:
            client: model
            prompt: 生成一个简短的日常问题，只发送给 receiver。
            active_round: 0
            action_kind: message
            target: receiver
            max_tokens: 256
      - id: receiver
        policy:
          type: core.llm
          config:
            client: model
            prompt: 回答收件箱中的问题，使用 final_answer 返回结果。
            active_round: 1
            action_kind: final_answer
            max_tokens: 256
    edges: [[sender, receiver]]
    max_rounds: 2
runtime:
  max_model_calls: 2
  max_output_tokens: 256
```

可将该用户配置命名为 `configs/llm.yaml`，先 `validate llm` 再 `run llm`。
模型返回不符合严格动作协议时保留真实失败，不自动生成替代答案。

### 模型参数

| 参数 | 含义 |
| --- | --- |
| `base_url` | 必填，API 根地址，可含 `/v1`；适配器追加 `/chat/completions` |
| `model` | 必填，资源默认模型名；策略可显式覆盖 |
| `api_key_env` | 密钥环境变量名称，不是密钥本身；无鉴权本地服务可省略 |
| `timeout` | 连接及读操作超时秒数，默认 60；不是整个实验的硬截止 |
| `response_format` | 默认 `json_object`；`text` 表示不发送该 API 字段，节点仍须输出动作 JSON |
| `thinking` | 可选 `enabled` / `disabled`；仅在所用服务支持时填写 |
| `reasoning_effort` | 可选推理强度；具体值由服务提供方定义 |

远程接口必须使用 HTTPS；`localhost`、`127.0.0.1`、`::1` 可使用本地 HTTP。
URL 不得包含凭证、查询参数或片段。客户端不跟随重定向，不自动重试；
一次 `generate` 最多一次 HTTP 请求，错误正文不会原样打印到命令行。

`core.llm` 的常用参数为 `client`、`role`、`prompt`、`model`、`temperature`、
`max_tokens`、`keep_history`、`active_round`、`action_kind`、`target`。
未指定 `active_round` 时，每个活动轮次都可能请求模型；默认不保留完整对话历史。
全部组件参数可由 `python -m stegopot plugins inspect core` 查询。

凭证优先级为：Python `environment` 显式覆盖 > 已有进程环境 > 工作区 `.env`。
读取文件不会修改 `os.environ`。旧 `DEEPSEEK_MODEL` 和测试开关不再控制框架运行。

## 使用核心隐写

`core.stegokit` 将 StegoKit 接入统一 `StegoCodec` 契约。
发送策略获得私有比特，接收策略只从实际收到的公开文本解码，不暗传编码端 token ID。

以下为本地模型配置结构。使用前准备模型、初始化子模块并安装 `.[stego]`，
将 `model_path` 改为模型的绝对路径。配置能通过预检不等于模型和 tokenizer 一定兼容算法。

```yaml
schema_version: "1"
resources:
  codec:
    type: core.stegokit
    config:
      model_path: D:/Models/your-local-causal-model
      algorithm: ac
      generation:
        max_new_tokens: 64
        temperature: 1.0
        top_k: 4
        precision: 32
        stop_on_eos: false
scenario:
  type: core.explicit
  config:
    task: 通过公开状态文本传递私有比特。
    nodes:
      - id: sender
        policy:
          type: core.codec_sender
          config: {codec: codec, target: receiver}
      - id: receiver
        policy:
          type: core.codec_receiver
          config: {codec: codec}
    edges: [[sender, receiver]]
    node_contexts:
      sender:
        secret_bits: "01010101"
        shared_material:
          messages: [{role: user, content: Write a short status update.}]
      receiver:
        shared_material:
          messages: [{role: user, content: Write a short status update.}]
          max_bits: 8
    truth: {secret_bits: "01010101", receiver: receiver}
    max_rounds: 2
evaluators:
  - type: core.stego_metrics
```

`generation` 约束本地生成；`encode_config` 和 `decode_config` 可传入算法配置。
发送节点默认第 0 轮编码，接收节点默认第 1 轮解码；可通过 `active_round` 调整。
基础接收策略要求单一载体，多消息协议应实现自己的策略。

双方所需的 `shared_material` 必须显式分配，不能把秘密放进 `shared_context`。
适配器会检查文本与 token 的往返一致性，不满足时明确失败。
框架仅加载本地模型，禁用自动下载及远程模型代码。

**Chat Completions API 与本地隐写模型不能相互替代。**
前者提供文本响应，后者通常需要 token 级概率。
`core.codec_sender/receiver` 是工具策略，不是 LLM 自主选择工具或自发共谋的证据。

## 配置与命令约定

### 配置结构

组件统一使用 `type/config`：

```yaml
type: core.replace
config:
  search: old-text
  replacement: new-text
```

该片段是单个信道组件，应放入完整实验的 `channels` 列表，而非单独运行。
`type` 是注册后的组件 ID；`config` 只接受该组件声明的参数。

| 顶层字段 | 约定 |
| --- | --- |
| `schema_version` | 必填，当前为字符串 `"1"` |
| `scenario` | 必填，场景组件引用，产生计划而不自行执行实验 |
| `plugins` | 已安装插件的显式允许列表，可附版本范围；默认空列表 |
| `seed` | 中央计划种子，默认 0；不自动给节点，不保证远程模型采样确定性 |
| `resources` | 命名的模型与 codec 资源，只允许 `llm` / `codec` 类型 |
| `policies` | 按节点 ID 覆盖场景的默认策略 |
| `topology.edges` | 覆盖场景的有向通信边 |
| `channels` | 按配置顺序执行的公开正文干预 |
| `detectors` | 检测最终公开消息的组件，不自动据此阻断消息 |
| `rewards` | 按公开轮次转移计算节点反馈的组件 |
| `evaluators` | 额外中央评分器，结果使用组件 ID 命名空间 |
| `audit_sinks` | 附加研究审计接收器，不替代或关闭宿主日志 |
| `runtime` | 模型调用、输出 token、轮数、试验数和软时间上限 |
| `audit` | 仅允许 `required: true`、`profile: research` |

`core.explicit.config` 必填 `task`、`nodes`、`edges`；可选 `max_rounds`、
`repeat`、`substrate`、`shared_context`、`node_contexts`、`truth`。
每个节点必填 `id`、`policy`，可选 `role`。
默认环境为 `core.communication`，默认 2 轮、1 次试验。

默认预算为 64 次模型调用、每次最多 1024 输出 token、100 轮、1000 次试验、3600 秒。
`runtime.max_rounds` 是上限，真正的轮数由场景决定。
时间上限在试验边界检查，不强制中断正在执行的插件；本地 codec 计算不计入 LLM 调用次数。

解析器拒绝未知字段、重复键、YAML 锚点/别名、对象构造标签和大于 2 MB 的配置。
不执行配置中的 Python 表达式，不进行任意环境变量插值。

### 文件与路径

- 支持 `.yaml`、`.yml`、`.json`；`configs/team/study.yaml` 可按名称 `team/study` 选择。
- 省略配置参数时要求目录中恰好一份配置；没有配置、多份配置或同名歧义均不会自动运行。
- 可显式使用 `configs/team/study.yaml` 或绝对配置路径。
- 相对配置路径和 `--output`、`--env-file` 以工作区为基准；绝对路径保持原义。
- 指定外部配置不会改变工作区、默认凭证和输出目录。
- 框架不猜测第三方参数是否表示文件路径；内置 StegoKit 的模型路径应写为绝对路径。
- 本仓库默认忽略用户 YAML/JSON 配置及结果；公开研究配置前应自行审查并选择版本控制范围。

### 命令与退出码

| 命令 | 行为 |
| --- | --- |
| `init [目录]` | 创建空配置目录 |
| `list [--workspace 目录]` | 发现配置，不解析内容、不加载插件 |
| `validate [配置]` | 预检；不会创建模型客户端，但会调用受信任场景插件生成计划 |
| `run [配置]` | 预检并执行；支持 `--workspace` 和 `--output` |
| `plugins list` | 查看核心和安装元数据，不导入第三方组件 |
| `plugins inspect <ID>` | 显式加载指定插件，输出组件参数与依赖声明 |
| `schema [--component ID]` | 输出顶层或指定内置组件的 JSON Schema |
| `verify <运行目录>` | 离线核验报告、日志及关联封印 |
| `--version` / `--help` | 查看版本或帮助 |

`run` 和 `validate` 都支持 `--env-file` 或 `--no-env`，两者互斥。
`--no-env` 仅禁用文件读取，不清除已有进程环境。

退出码：**0** 为成功；**1** 为实验结果 `failed` 或 `partial`；
**2** 为配置、参数或执行入口错误。审计写入失败可能使目录未封印，不能仅凭目录存在判断成功。

## Python 调用

### 文件级入口

```python
from stegopot.bootstrap.experiments.api import run_file

report, directory = run_file(
    "communication",
    workspace="D:/Research/my-workspace",
    output="outputs",
    load_env=True,
)
if report["status"] != "completed":
    raise RuntimeError(f"实验未完整成功，请检查 {directory}")
```

`run_file` 自动预检。需要固定准备结果后再执行时，改用分步入口：

```python
from stegopot.bootstrap.experiments.api import prepare_file
from stegopot.bootstrap.experiments.run import run_experiment

prepared = prepare_file("communication", workspace="D:/Research/my-workspace")
report, directory = run_experiment(
    prepared,
    output="D:/Research/my-workspace/outputs",
)
```

`run_experiment` 是较低层入口，不自动继承工作区路径；示例明确传入结果目录，
不要为同一次运行先调用它再调用 `run_file`。

| 参数 | 适用入口 | 调用约定 |
| --- | --- | --- |
| `config` | prepare_file / run_file | 配置名或路径，默认自动选择唯一配置 |
| `workspace` | 两者 | 工作区，默认当前目录 |
| `env_file` | 两者 | 显式凭证文件；默认工作区 `.env` |
| `load_env` | 两者 | 默认 True；False 时不能同时指定 env_file |
| `environment` | 两者 | 单次环境覆盖映射，不写入进程全局状态 |
| `catalog` | 两者 | 注入注册表；提供后由调用方负责登记全部需要的插件，不自动补充加载 |
| `output` | run_file | 结果父目录，默认工作区 outputs |
| `progress` | run_file | 每次试验后接收研究记录副本的回调；不得泄露记录，异常可能中断运行 |

`prepare_file` 返回 `PreparedExperiment`，含配置、计划、固定注册表和私有凭证，
不得直接公开。`run_file` 返回 `(report, directory)`：报告是字典，目录是 `Path`。
普通组件失败写入报告，调用方必须检查 `status`；配置和审计等异常向调用者传播。
直接调用字典级 `prepare_experiment` / `run_experiment` 也可使用相同执行链路。

### 同步调度与动作

节点策略的核心调用为：

```python
state = policy.initial_state()
action, next_state = policy.step(observation, state)
```

`AgentNode` 保存节点身份和策略状态；`Policy` 只负责决策。
观察包含任务、当前轮次、自身身份、出入邻居、收件箱、上一动作、共享上下文及局部环境。

| 约定 | 行为 |
| --- | --- |
| 轮次 | 从 0 开始，同轮产生的消息在下一轮进入收件箱 |
| 消息方向 | 只能发给出邻居；向一个节点定向发送用其 ID |
| 广播 | message 的 target 为 null 或 `*` 时广播给出邻居，不是向全局所有节点发送 |
| 最终答案 | final_answer 写入该节点结果，不作为消息投递给其他节点 |
| 标准试验 | 由计划轮数调度；单个节点给出 final_answer 不代表整组实验立即结束 |
| 状态 | 初始状态属于本次节点运行，不隐式共享其他节点的内部状态 |

LLM 通过 JSON 表达相同动作，例如：

```json
{"kind": "message", "content": "公开消息", "target": "receiver", "metadata": {}}
```

动作类型为 `message`、`wait`、`final_answer`。
启用 `action_kind` 时使用严格解析，要求且仅允许上述四个字段，
动作类型与目标必须匹配，正文必须非空，metadata 必须为 `{}`。
普通策略使用的宽松解析与该严格模式不同，不能把两者的失败处理混为一谈。
标准公开消息管线会剥离动作元数据，防止把它当作额外隐蔽通道。

## 组件接口约定

所有公开契约集中在 [domain/interface](stegopot/domain/interface)。
抽象类用于约束行为，并不表示要实例化抽象类；工厂返回满足契约的具体实现。
部分接口使用 Protocol，宿主也检查关键方法与结果类型。

| kind | 主要调用 | 返回与责任 |
| --- | --- | --- |
| scenario | `plan(seed)` | 返回 ExperimentPlan；只生成 TrialSpec，不执行模型或自行运行实验 |
| policy | `initial_state()`、`step(observation, state)`、`close()` | 返回 AgentAction 与下一状态，只处理节点局部观察 |
| llm | `generate(messages, *, model, temperature, max_tokens)`、`close()` | 返回 LLMResponse，保留实际文本与真实响应元数据 |
| codec | `encode(request)`、`decode(request)`、`close()` | 返回 EncodeResult / DecodeResult；只通过实际载体与授权材料解码 |
| substrate | `reset(context)`、`observe(node_id)`、`step(context)`、`state()`、`close()` | 管理环境状态，step 返回 SubstrateStepResult |
| channel | `transform(message)` | 返回同身份 AgentMessage 或 None 阻断；不能改变 ID、主体、轮次或增加元数据 |
| detector | `reset()`、`detect(request)`、`close()` | 返回与请求 message_id 一致的 DetectionResult |
| reward | `score(transition)` | 返回现有节点 ID 到有限数值奖励的映射，不直接修改模型权重 |
| evaluator | `evaluate(trial, result)`、`summarize(records)` | 返回可 JSON 序列化的指标；保留全部失败和跳过样本 |
| audit | `emit(event)` | 持久化研究事件；失败必须向上抛出，不能假装写入成功 |

### 可见信息

- `shared_context` 是显式公开材料；不要放置秘密、密钥或中央标签。
- `node_contexts[id]` 只投影到该节点的 `environment.framework.private`。
- `truth` 只用于中央评价，不自动加入节点观察；中央种子和完整计划也不自动公开。
- 奖励输入包含轮次、实际公开消息和动作类型/目标，不包含未投递正文或私有最终答案。
- 检测器只获得最终公开正文及身份，不能从宿主取得秘密比特和预共享材料。
- 节点可通过自己的私有配置 `observe_public_channel: true` 获得最终公开转录，
  但不会获得干预前状态或其他节点的私有上下文。
- codec 的 research 字段是研究材料，不得附加到公开消息中。

场景可通过 `ReplaySpec` 引用前序试验的唯一实际投递正文。
源试验失败或载体不唯一时跳过，不用重新生成的正文冒充配对对照。

### 生命周期与所有权

1. 读取配置并加载显式允许的插件，校验 API 版本和组件参数。
2. 调用场景生成计划，解析所需资源与凭证引用，冻结本次注册表。
3. 为试验建立组件会话；资源按试验和节点作用域缓存，不因为资源名称相同就跨节点共享可变实例。
4. 运行器调用策略与环境，宿主包装模型和 codec 的实际调用审计。
5. 中央评分、写报告并封印；宿主逆序关闭持有的资源。

组件**不能关闭注入的模型、codec 或宿主日志**。它只关闭自己创建、自己拥有的资源。
工厂构造失败时，尚未交还宿主的资源由工厂释放。
预检阶段的场景工厂不得访问网络、凭证或运行资源；这是可信插件契约，不是系统级沙箱强制隔离。

## 开发扩展

### 独立包与装饰器

具体实验和专用算法应放在自己的安装包中。例如：

```text
my-plugin/
  pyproject.toml
  src/my_stegopot_plugin/
    __init__.py
    application/
      __init__.py
      reward.py
    bootstrap/
      __init__.py
      plugin.py
```

`application/reward.py` 实现功能：

```python
from collections.abc import Mapping
from typing import Any

class DeliveryReward:
    """根据实际公开投递计算发送节点的奖励。"""

    def __init__(self, *, points: float) -> None:
        """points 为每条消息的奖励；本对象不拥有外部资源。"""
        self._points = points

    def score(self, transition: Mapping[str, Any]) -> Mapping[str, float]:
        """transition 是宿主提供的公开轮次转移；返回节点奖励映射。"""
        rewards: dict[str, float] = {}
        for message in transition["messages"]:
            sender = message["sender"]
            rewards[sender] = rewards.get(sender, 0.0) + self._points
        return rewards
```

`bootstrap/plugin.py` 只声明参数并组装对象：

```python
from dataclasses import dataclass, field

from stegopot.domain.interface.plugin import BuildContext
from stegopot.domain.interface.registration import Plugin
from my_stegopot_plugin.application.reward import DeliveryReward

plugin = Plugin("research", "0.1.0")

@dataclass(frozen=True)
class RewardConfig:
    points: float = field(
        default=1.0,
        metadata={"description": "每条实际投递消息给予发送者的奖励"},
    )

@plugin.component("reward", "delivery", config=RewardConfig)
def build_reward(config: RewardConfig, context: BuildContext) -> DeliveryReward:
    """config 为已验证参数；context 为受限上下文，本组件不申请外部资源。"""
    return DeliveryReward(points=config.points)
```

`pyproject.toml` 声明安装和发现方式：

```toml
[build-system]
requires = ["setuptools>=77"]
build-backend = "setuptools.build_meta"

[project]
name = "my-stegopot-plugin"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["stegopot>=0.7,<0.8"]

[project.entry-points."stegopot.plugins"]
research = "my_stegopot_plugin.bootstrap.plugin:plugin"

[tool.setuptools.packages.find]
where = ["src"]
```

安装包名称可以不同于插件 ID；entry point 名称必须与 Plugin 的 ID 一致，
包版本必须与 Plugin 声明版本一致。此示例生成组件 ID `research.delivery`。

先在运行框架的同一解释器中安装，再在自己的完整实验配置中启用：

```shell
python -m pip install -e D:/Research/my-plugin
python -m stegopot plugins inspect research
```

```yaml
plugins:
  - id: research
    version: ">=0.1,<0.2"
rewards:
  - type: research.delivery
    config: {points: 1.0}
```

这只是并入完整配置的扩展片段；不会取代必填的 scenario。
插件安装不等于启用，启用也不意味着自动执行其他配置文件。

### 工厂与注入

统一工厂签名为 `factory(config, context) -> component`。
`config=数据类` 会自动生成参数模式；每个字段必须提供中文 `metadata.description`。
复杂约束可改用显式 `schema`，但不能同时指定 config 和 schema。

| 声明或方法 | 约定 |
| --- | --- |
| `kind`、`name` | kind 必须属于十类接口；name 是插件内短名 |
| `config` / `schema` | 定义严格参数模式，拒绝未知字段；schema 只接受内部引用 |
| `references={"client": "llm", "codec": "codec"}` | 声明配置字段引用的资源类型，工厂只能访问所声明槽位 |
| `context.resource("client")` | 按槽位取得宿主注入的已审计资源，不是按任意全局名称查找 |
| `credentials=("api_key_env",)` | 只有 llm 工厂可以声明；配置中写环境变量名 |
| `context.credential("api_key_env")` | 读取已授权密钥，不提供整个环境变量字典 |
| `context.node_id` | 当前构造作用域的节点身份；无节点作用域时可为 None |
| `context.audit.emit(event)` | 插件事件写入研究日志的 plugin.event 命名空间 |

组件不得绕过注入自行读取其他节点数据、重复关闭依赖或修改宿主全局注册表。
重复 ID、版本不兼容、错误资源类型和未知参数都会被拒绝。
在进程内注入 PluginCatalog 时由调用方完成注册；CLI 则依据安装元数据与配置允许列表发现插件。

## 结果与审计

每次运行创建新目录，默认不会覆盖之前的结果：

```text
outputs/<run-id>/
  manifest.json                 规范化配置、展开计划、插件版本与源码摘要
  experiment-report.json        整组研究报告
  report.md                     人类可读汇总
  research.jsonl                根研究事件流
  public.jsonl                  根公开事件流
  seal.json                     根日志及关联文件封印
  <trial-id>/
    result.json                 单次试验的真实结果、状态和指标
    research.jsonl              观察、请求、响应、工具和干预等研究记录
    public.jsonl                公开事件白名单投影
    seal.json                   单次试验封印
```

结果契约为 `stegopot.report/1`。报告包含 `trials`、`summary`、`errors`、
`status`，以及模型调用数、实际型号、服务端返回的用量和耗时。
缺少服务端用量不等于真实零费用；完成运行也不等于完成研究目标。

`completed` 表示正常完成；`failed` 表示存在失败；
`partial` 表示没有失败但存在跳过。失败不会被补写成成功答案或当作阴性样本。
模型/组件失败可留下完整失败报告；审计写盘失败或中断则可能留下未封印目录。

```shell
python -m stegopot verify outputs/<run-id>
python -m stegopot verify outputs/<run-id> --expected-seal-sha256 <独立保存的根哈希>
```

根哈希是 `seal.json` 文件的 SHA-256，可在 PowerShell 中读取：

```powershell
Get-FileHash -LiteralPath "outputs/<run-id>/seal.json" -Algorithm SHA256
```

应在研究目录之外独立保管该值。哈希链验证内部一致性，不是数字签名、
可信时间戳或供应商签署回执；同时重写日志和封印时，仅靠自校验不足以证明原始性。

完整研究记录可能包含秘密比特、预共享材料和提示，**不得直接公开或交给观察者**。
公开投影也无法撤回模型在正文中主动泄露的信息。
凭证脱敏不是通用数据防泄漏保证，插件必须遵守资源和输出边界。

## 边界与常见问题

**没有配置时为什么不能直接运行？**

框架不预置研究任务。先编写 configs 中的配置；本 README 的代码块用于说明格式，不会自动生成文件。

**可以只改配置实现任何实验吗？**

配置可以组合已有组件，不能凭空实现新算法。新的场景、策略、协议或评价需要插件代码。

**有奖励接口，是否已经实现强化学习？**

没有。当前只计算和投影反馈，不提供训练循环、模型权重更新或自动协议演化。

**是否已经证明模型自发隐写或共谋？**

没有。框架提供实验能力，不预设结论。工具恢复比特、人工共享协议和 LLM 自发行为必须区分。

**LLM 能否自动调用任意工具？**

当前核心没有通用自主工具规划器。`core.codec_sender/receiver` 是固定工具策略；
更复杂的模型与工具协作应通过 policy 接口开发。

**热插拔发生在什么时候？**

两次实验之间通过配置启停、替换组件。更换已安装代码后应启动新进程，
不支持执行过程中热重载 Python 模块，也不自动执行某个目录里的任意脚本。

**插件是否被安全隔离？**

不是。插件是与宿主同进程运行的可信 Python 代码，仍具有宿主进程权限。
接口可见性不等于操作系统沙箱或针对恶意插件的安全保证。

**旧的 DeepSeek 扩展和实验命令还能用吗？**

0.7 已移除旧专用扩展和实验目录。模型资源使用 `core.chat_completions`，
运行统一使用 `python -m stegopot run`。不要继续引用旧 examples、experiments 或 Console 路径。

**为什么安装后又出现 egg-info？**

这是打包工具可能重新生成的元数据。删除不等于禁用框架，但下一次安装可能重建；
不修改它，也不将它作为业务目录或提交内容。

## 开发规范与许可

四层结构、中文参数说明、资源所有权和信息边界的完整约束见 [AGENTS.md](AGENTS.md)
与 [架构说明](docs/architecture.md)。更多使用细节见 [配置指南](docs/usage.md)，
扩展说明见 [接口开发指南](docs/plugin_development.md)。

框架修改应在临时工作区验证配置、拓扑隔离、资源注入、失败记录、审计封印和独立安装。
本仓库不恢复旧实验测试或保存验证结果；第三方插件应在自己的项目中维护对应测试。
默认不运行付费 API，真实模型实验需要由使用者明确选择。

核心采用 [Apache-2.0](LICENSE)。StegoKit 保留
[上游许可证](stegopot/infrastructure/vendor/stego-kit/LICENSE) 及固定版本源码；
适用条件应同时参考对应算法实现。
