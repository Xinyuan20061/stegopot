# 框架架构

## 项目边界

StegoPot 是多 Agent 隐写实验框架。核心保留通信隔离、StegoKit、基础检测与审计，
不包含具体论文场景、共谋协议、历史配置、结果或可视化应用。
用户的实验由自己的配置和独立插件定义，安装框架不会自动创建或运行实验。

仓库只有三类主要目录：`stegopot/` 是实现，`configs/` 是用户输入，`docs/` 是文档。
`outputs/` 按运行需要生成。安装包只分发 `stegopot`，工作区可以建立在任何用户目录。
`.env` 与 `.venv` 属于本机环境，不属于业务层；凭证和结果不能提交仓库。

## 四层结构

```text
stegopot/
  domain/
    interface/                  所有 ABC/Protocol、插件声明与装饰器
    model/                      消息、动作、拓扑、计划与试验数据
  application/
    engine/                     节点状态、轮次调度、路由和信息投影
    services/experiments/       通用场景、试验执行、结果汇总
  infrastructure/
    settings/                   工作区发现、配置校验、独立环境快照
    plugins/                    已安装 entry point 发现与模式校验
    llm/                        策略、提示解析、请求与工具审计
      clients/                  通用 HTTP 模型适配与模拟客户端
    integrations/stegokit/     核心隐写适配与实际载体编解码
    vendor/stego-kit/           固定版本上游源码
    substrates/                通信、隐写环境和信道实现
    detectors/                 基础公开载体检测
    recorders/audit/            双日志、脱敏、封印、报告与核验
  bootstrap/
    experiments/               文件级 API、CLI、预检、组装和资源生命周期
```

目录体现调用职责，不按每个实验新建一套框架。兼容 Builder 接口仍可用于嵌入调用，
但标准实验推荐文件级 API/CLI，以得到强制审计、版本清单和统一失败记录。

## 依赖方向

| 区域 | 允许依赖 |
| --- | --- |
| domain.model | 自身、标准库 |
| domain.interface | 自身、domain.model、标准库 |
| application.engine | 自身、domain |
| application.services | 自身、application.engine、domain |
| infrastructure.settings | 自身、domain.model |
| infrastructure.llm | 自身、settings、domain |
| infrastructure.integrations | 自身、domain.interface |
| infrastructure.substrates / detectors / plugins | 自身、domain |
| infrastructure.recorders | 自身、标准库 |
| bootstrap | 上述区域，只做组装和边界接入 |
| 第三方插件 | 自己的实现与 stegopot.domain 契约 |

不创建第五个技术层，不把抽象类分散到实现目录，不用统一 utils 隐藏依赖。
Plugin 装饰器只生成组件声明；发现已安装插件属于基础设施，调用工厂属于组合根。

## 执行链路

```text
CLI / prepare_file / run_file
 -> ExperimentWorkspace：选择唯一配置、生成独立环境快照
 -> load_config：读取 JSON/YAML 并做严格校验
 -> prepare_experiment：发现允许的组件、校验凭证与引用、固定计划
 -> ScenarioProvider.plan：只返回 ExperimentPlan / TrialSpec
 -> ComponentSession：构造本次组件，注入声明的模型、codec 和审计
 -> MultiAgentRuntime：局部观察 -> Policy.step -> 候选消息
 -> 环境 -> 信道变换 -> 公开检测 -> 奖励 -> 下一轮收件箱
 -> Evaluator：中央评分，不回填模型答案
 -> AuditJournal：报告、研究/公开日志、关联封印
```

工作区发现不解析配置，预检不创建模型；第三方场景必须自行遵守纯计划约束。
文件级入口不切换进程工作目录、不修改 os.environ，输出默认属于指定工作区。
框架只解析自己定义的路径，不猜测插件任意字符串参数是否是文件路径。
当前本地 StegoKit 的 model_path 应使用绝对路径，插件自行声明自己的路径语义。

## 隔离与生命周期

- shared_context 显式公开；node_contexts[id] 只给对应节点；truth 只给中央评价。
- 不把中央种子、试验编号和完整计划自动投影给节点。
- 信道只能改公开正文或阻断，不能改变身份、轮次、目标或增加元数据。
- 检测器只读最终公开消息，不能通过宿主接口读取私有比特或预共享密钥。
- 模型和 codec 按试验及节点构造、缓存；所有权由宿主统一管理并逆序关闭。
- 凭证只传给声明 credentials 的模型工厂，不传给策略、信道或评分器。
- 内置模型适配不自动重试，不跟随重定向，不把鉴权头或服务端错误正文打印出来。
- 插件自定义事件进入 plugin.event 命名空间，不能伪造宿主的公开投递事件。

上述约束适用于可信组件，不是 Python 进程安全沙箱。安装的插件仍有宿主进程权限。
热插拔指两次实验之间启停或更换组件；更换已安装代码后使用新进程。

## 审计契约

标准输出契约为 stegopot.report/1。完整记录包括配置、计划、组件版本、源码摘要、
成功/失败/跳过状态、模型请求和实际回复、工具结果与消息干预。
CLI 和文件级 API 不能关闭宿主日志；写入失败中止，不生成虚假完整封印。
公开日志只是白名单投影，不能保证模型主动输出的正文不泄密。
哈希链检查内部一致性，配合独立根哈希锚点核验，不能宣传为签名或可信时间戳。

## 开发验证

仓库不保留之前的实验测试。框架修改仍需用临时工作区验证入口、拓扑、插件、
凭证隔离、失败行为和审计核验，并检查安装包脱离源码目录后能否工作。
测试结果和临时配置不得回填 configs 或作为框架预置实验发布。
