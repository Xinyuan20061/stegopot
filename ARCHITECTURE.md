# StegoPot 架构

## 定位与边界

这是多 Agent 隐写实验框架，而不是没有领域特征的任务调度器。
StegoKit、隐写契约、消息隔离、基础检测与审计属于核心；
专用共谋协议、论文场景、实验提示与专用评分属于扩展。
所有 ABC/Protocol 集中在 `stegopot/domain/interface`。

## 四层目录

```text
stegopot/
├── domain/
│   ├── interface/
│   │   ├── policy.py / llm.py           决策与模型
│   │   ├── substrate.py / channel.py   环境与正文干预
│   │   ├── codec.py / stego.py         新载体契约与兼容工具契约
│   │   ├── detector.py / audit.py      检测与审计
│   │   ├── experiment.py               场景、奖励、中央评价
│   │   └── plugin.py / registration.py 声明、上下文与装饰器
│   └── model/                         消息、拓扑、动作、实验计划
├── application/
│   ├── engine/                        节点、路由、轮次、环境管线
│   └── services/experiments/           显式场景、统一执行与通用评分
├── infrastructure/
│   ├── integrations/stegokit/         核心 StegoKit 适配与载体编解码
│   ├── vendor/stego-kit/               固定上游子模块
│   ├── llm/                           策略、提示、解析、模型/工具审计
│   ├── substrates/                    通信和兼容环境实现
│   ├── detectors/                     基础检测实现
│   ├── plugins/                       安装元数据发现、版本与模式校验
│   ├── settings/                      配置文件与环境变量读取
│   └── recorders/audit/                双日志、投影、封印、标准报告
└── bootstrap/experiments/             预检、组件组装、资源所有权、CLI
extensions/
├── stegopot-collusion/src/stegopot_collusion/
│   ├── domain/model/                  实验条件
│   ├── application/services/          场景计划与专用评价
│   ├── infrastructure/                角色策略、提示、信道
│   └── bootstrap/                     entry point
└── stegopot-deepseek/src/stegopot_deepseek/
    ├── infrastructure/                供应商 HTTP 实现
    └── bootstrap/                     entry point
```

空层不必创建，复杂功能必须在对应层中继续按职责分目录。
扩展只能导入核心公开 `domain` 契约，不能导入内核运行器或具体基础设施；
场景通过组件 ID 引用核心能力，不通过导入隐藏耦合。

## 调用关系

```text
CLI
 -> load_config -> prepare_experiment
 -> PluginCatalog（显式允许列表、API 与配置校验）
 -> ScenarioProvider.plan -> ExperimentPlan / TrialSpec
 -> ComponentSession（按声明注入模型、codec、凭证和审计）
 -> run_plan -> execute_trial -> MultiAgentRuntime
      -> Substrate.observe -> 节点局部观察 -> Policy.step
      -> 路由候选消息 -> ExperimentPipeline
           -> 环境处理 -> 身份检查 -> 清除元数据
           -> ChannelTransform -> StegoDetector -> RewardFunction
      -> 最终正文进入下一轮 inbox
 -> Evaluator（仅中央阶段接收 trial.truth）
 -> 宿主 AuditJournal -> 标准报告与关联封印
```

`Policy` 可以使用注入的 `LLMClient` 或 `StegoCodec`。
核心 `CodecPolicy` 是工具驱动策略；LLM 的决策与工具输出不得混为一谈。
新载体接口要求接收端从真实载体解码，旧 `StegoTool` 保留兼容。

## 依赖方向

| 区域 | 可依赖区域 |
| --- | --- |
| domain.model | 自身、标准库 |
| domain.interface | 自身、domain.model、标准库 |
| application.engine | 自身、domain |
| application.services | 自身、application.engine、domain |
| infrastructure.llm | 自身、settings、domain |
| infrastructure.integrations | 自身、domain.interface |
| infrastructure.substrates / detectors / plugins | 自身、domain |
| infrastructure.settings | 自身、domain.model |
| infrastructure.recorders | 自身、标准库 |
| bootstrap | 上述所有区域，仅做组装与边界接入 |

注册便利类 `Plugin` 只创建声明，不加载模块或运行组件。
安装发现与 JSON Schema 校验属于基础设施；工厂调用和所有权属于组合根。

## 信息边界

- `shared_context` 显式公开，不自动加入种子、计划、编号或真值。
- `node_contexts[id]` 只投影到该节点的 `environment.framework.private`。
- `truth` 仅用于中央评价与研究记录。
- `observe_public_channel` 授权读取最终公开转录，不暴露干预前的内部状态。
- 信道只能改变正文或阻断，不得改变身份、轮次、目标或增添元数据。
- 检测请求只有最终公开正文和身份，不含私有材料。
- 奖励接收轮次转移；当前接口不提供中央真值，节点只看到自身反馈。
- 模型/codec 资源按试验与节点缓存，构造时只注入已声明槽位。
- API 凭证只注入声明该环境变量字段的供应商工厂。

这些是可信组件的接口约束，不是抵御恶意 Python 插件的隔离机制。
插件自身创建网络连接或读取宿主文件不受进程沙箱约束。

## 生命周期与审计

预检阶段场景必须无副作用。执行阶段每次试验使用新会话，资源逆序关闭；
注入资源归宿主管理，组件不得重复关闭依赖。
原始模型客户端和 codec 由框架包装，记录请求、响应、异常与实际来源。
插件的自定义事件强制进入 `plugin.event`，不能伪造公开投递事件。

标准 CLI 强制审计，旧 Builder 保留可选审计以兼容已有嵌入程序。
审计失败中止执行；意外退出保留未封印记录，不生成虚假的完整报告。
中央评分只接收实际运行结果，失败不会补写答案。
源码摘要记录 Python 文件，不涵盖所有外部模型权重和操作系统依赖。
模型权重、数据集和实验外部材料仍需研究者固定版本。

新报告为 `stegopot.report/1`，历史共谋报告独立保留。
Console 仍消费旧报告格式，不在本次内核改动中适配；
前后端继续独立，不能直接暴露研究报告。

## 自动检查

`tests/test_architecture.py` 检查四层依赖、核心/扩展边界与抽象契约位置。
新增能力必须同步补充配置、中文参数说明、权限和失败用例。
