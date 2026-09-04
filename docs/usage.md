# 配置与运行

## 工作区约定

安装包与用户工作区分离。工作区含用户的 configs/、可选 .env 和按需生成的 outputs/。
`python -m stegopot init <目录>` 只创建空 configs，不修改现有 .env 或生成默认实验。
在当前目录操作时无需参数，其他工作区使用 `--workspace <目录>`。

| 命令 | 行为 |
| --- | --- |
| init [目录] | 幂等创建空配置目录，不执行实验 |
| list [--workspace 目录] | 递归列出 JSON/YAML 配置，不加载插件 |
| validate [名称] | 配置、节点、插件、资源及凭证预检，不请求模型 |
| doctor [名称] | 预检并检查本地依赖、模型文件；不连接网络、不加载模型 |
| run [名称] | 预检后运行，写独立审计目录 |
| schema [--component ID] | 输出顶层或指定内置组件的严格模式 |
| plugins list / inspect ID | 查询安装元数据或显式加载指定插件的接口描述 |
| verify 运行目录 | 离线核验全部关联报告和封印 |
| events 运行目录 | 默认核验后查询公开日志，可显式选择 research 和过滤条件 |

名称是相对于 configs 的路径，通常省略后缀，例如 configs/team/study.yaml 对应 team/study。
同名文件存在多个后缀时使用完整路径，例如 configs/team/study.yaml。
省略名称只在整个 configs 中恰好一份配置时成立；没有配置或存在多份均不会自动运行。
显式配置路径可以位于工作区外，但输出和默认 .env 仍属于 --workspace 指定目录。

run、validate 与 doctor 支持 --env-file（相对工作区）或 --no-env，两者互斥。
run 的 --output 默认 outputs，相对路径以工作区为基准，绝对路径保持原义。
每次运行使用唯一子目录，不覆盖以前结果。退出码：0 成功，1 实验失败或部分完成，2 入口/配置错误。

## 配置格式

下面仅解释格式，不作为文件附带发布；任务和策略由实验开发者填写。
最小声明为 schema_version 与 scenario。用 core.explicit 定义自己的节点及有向边：

```yaml
schema_version: "1"
scenario:
  type: core.explicit
  config:
    task: 填写你的公开实验任务
    nodes:
      - id: sender
        role: 发送节点
        policy:
          type: core.scripted
          config:
            actions:
              - kind: message
                target: receiver
                content: 填写你要发送的内容
      - id: receiver
        policy: {type: core.echo}
    edges: [[sender, receiver]]
    max_rounds: 2
```

core.scripted 是通用确定性策略，不是 LLM；core.echo 只用于规则节点。
同轮产生的消息在下一轮才可见，声明单向边不会自动反向连通。

| 顶层字段 | 参数说明 |
| --- | --- |
| schema_version | 必填，当前为字符串 "1" |
| scenario | 必填，场景的 type/config，返回完整计划而不自行执行 |
| plugins | 独立安装插件的显式允许列表，可指定版本范围 |
| seed | 中央种子，默认 0，不自动暴露给节点，不保证服务端采样确定性 |
| resources | 命名的 llm/codec 资源，通过策略声明槽位注入 |
| policies | 按节点 ID 覆盖场景的策略 |
| topology.edges | 覆盖场景的有向边，不允许不存在的节点 |
| channels | 按声明顺序执行的公开正文干预 |
| detectors | 公开消息检测组件，不读取私有真值 |
| rewards | 公开轮次转移到节点奖励的组件 |
| evaluators | 中央评分器，保留成功、失败和跳过样本 |
| audit_sinks | 可选研究事件接收器，不替代强制宿主审计 |
| runtime | max_model_calls=64、max_output_tokens=1024、max_rounds=100、max_trials=1000、max_seconds=3600 |
| audit | 只允许 required=true、profile=research，不可关闭审计 |

core.explicit 的可选参数还有 repeat（独立重复次数）、substrate（环境组件）、
shared_context（公开材料）、node_contexts（按节点隔离的私有材料）、truth（中央评分真值）。
max_rounds 属于场景轮数，runtime.max_rounds 是宿主上限；后者不会自动延长实验。
参数必须符合 schema，拒绝未知字段、重复键、YAML 别名和超过 2 MB 的配置文件。
不执行配置中的 Python 表达式，不插值任意环境变量，更不会把全部 .env 写入配置清单。

## 模型请求

内置资源类型为 core.chat_completions。支持兼容的 Chat Completions 服务，
不需要安装旧 DeepSeek 扩展。配置资源后，节点用 core.llm 并声明 client 槽位引用：

```yaml
resources:
  model:
    type: core.chat_completions
    config:
      base_url: https://api.deepseek.com
      model: 填写你账户实际可用的模型名称
      api_key_env: DEEPSEEK_API_KEY
      timeout: 60
      response_format: json_object
policies:
  sender:
    type: core.llm
    config:
      client: model
      prompt: 填写该节点的行为要求
      max_tokens: 384
      temperature: 0
```

这是应合并到完整配置的资源与策略片段，不是可独立运行的配置。
system prompt 与统一动作协议由框架提示构建器组合；策略输出 message、wait 或 final_answer。
每个节点只看到自己的观察和历史，必要时启用 keep_history；active_round 可限制决策轮次。
严格格式可用 action_kind 与 target 约束。全部参数以 `plugins inspect core` 为准。

在工作区 .env 中填写 DEEPSEEK_API_KEY。优先级为 Python environment 显式覆盖 >
已有进程环境 > .env。旧 DEEPSEEK_MODEL 和 RUN_DEEPSEEK_LIVE_TEST 不再控制框架运行，
不会改写你的现有 .env；模型名明确写在资源配置中。

base_url 必须是无鉴权、查询参数或片段的 API 根地址，适配器追加 /chat/completions。
远程接口要求 HTTPS；localhost、127.0.0.1、::1 可用 HTTP；无鉴权本地服务可省略 api_key_env。
thinking 和 reasoning_effort 仅在服务支持时填写；不兼容 JSON 模式时可选 response_format: text。
客户端不跟随重定向、不自动重试，失败真实记录；一次 generate 最多一次 HTTP 请求。
宿主限制调用数与输出 token，超时是连接/读超时，不是实验强制终止机制。
0.8 另提供节点/试验调用额度、工具调用数、上下文与正文大小限制，以及协作式取消。
参数、默认值、错误码和取消示例见 [内核控制与审计](kernel.md)。

## 核心隐写

核心保留 StegoKit，不依赖具体论文扩展。资源类型 core.stegokit，
必填 model_path（本地模型绝对路径），可选 algorithm、generation、encode_config、decode_config。
只加载本地模型，不下载权重，不执行远程模型代码。

- core.codec_sender：config 指定 codec 资源名、target 接收者和可选 active_round。
- core.codec_receiver：config 指定 codec 和可选 active_round。
- 发送者私有上下文放 secret_bits；双方通过各自私有上下文明确获得 shared_material。
- shared_material 可含预共享 messages、material；接收端还可指定 max_bits。
- truth 只供中央评价，core.stego_metrics 可对实际恢复比特评分。

接收端从实际收到的公开文本重新分词解码，无法一致往返时明确失败。
普通 Chat Completions API 不能替代 StegoKit 所需的本地 token 概率模型。
core.codec_sender/receiver 是工具策略，不代表 LLM 自主隐写；需要自主工具规划时应开发 policy 插件。
基础检测包括 core.keyword 和 core.llm_detector；专用检测算法应单独扩展并说明适用条件。

## 结果与审计

outputs/<run-id>/ 中的 manifest.json 固定配置、展开计划、插件版本和源码摘要；
experiment-report.json/report.md 保存整组结果。每个试验子目录有 result.json、
research.jsonl、public.jsonl 和 seal.json，根封印关联全部子结果。
research 为私有研究数据，公开日志也应检查模型正文是否主动泄露秘密。

```powershell
python -m stegopot verify outputs/<run-id>
python -m stegopot verify outputs/<run-id> --expected-seal-sha256 <独立保存的哈希>
```

不能把审计写入失败后的未封印目录当成完整实验。哈希链不是数字签名，
只凭自身内容不能识别同时重写日志和封印的情况，须独立保存根哈希。

按消息或模型调用查询时可使用：

```shell
python -m stegopot events outputs/<run-id> --scope research --node sender --round 0
python -m stegopot events outputs/<run-id> --scope research --trial <trial-id> --message <message-id>
```

research 查询含私有研究材料，不能直接公开；默认 public 不附加调用链字段。
配置预检错误以 JSON diagnostics 返回，包含位置、组件、机器码和修复建议。
