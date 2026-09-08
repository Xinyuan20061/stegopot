# 威胁模型与信息边界

本页对应 StegoPot 0.10.0 的 `stegopot.threat-model/1` 契约。它把实验中的
组件可见信息、信任前提和审计范围编译成运行前固定的 `ThreatModelManifest`。

## 保证范围

StegoPot 当前支持的信任方式为：

```text
trusted_in_process
```

含义是插件作为受信任 Python 代码在宿主进程内运行，并应只使用框架注入的接口。
框架会限制通过这些接口传递的数据，但不阻止插件直接访问进程、文件、网络或其他
Python 对象。因此它是实验接口的可见性契约，不是操作系统安全沙箱、权限容器或
针对恶意插件的非干扰证明。

## 配置声明

`threat_model` 是可选顶层字段。省略时使用最小公开范围：

```yaml
threat_model:
  trust_model: trusted_in_process
  policy_view:
    public_channel_history: false
  detector_view:
    public_experiment_context: false
  audit:
    public_profile: minimal
    research_profile: complete
```

| 参数 | 默认值 | 实际作用 |
| --- | --- | --- |
| `trust_model` | `trusted_in_process` | 声明插件信任前提；当前不接受其他值 |
| `policy_view.public_channel_history` | `false` | 为 true 时，所有节点看到此前实际投递的公开消息历史 |
| `detector_view.public_experiment_context` | `false` | 为 true 时，Detector 额外读取任务、节点、拓扑和 `shared_context` |
| `audit.public_profile` | `minimal` | 未知事件默认不公开的白名单投影 |
| `audit.research_profile` | `complete` | 保存计划、调用、干预、失败和结果的研究证据 |

只提供运行时已经能够严格执行的开关。新的可见性能力必须先定义类型、投影位置、
审计语义和边界测试，再加入配置；不能仅增加一个没有执行效果的 YAML 字段。

## 固定组件视图

无论是否填写可选开关，框架都执行以下固定边界：

| 组件 | 宿主提供的信息 | 不通过宿主提供的信息 |
| --- | --- | --- |
| Policy | 任务、自身身份、局部拓扑、收件箱、上一动作、公共上下文、自身私有上下文和奖励 | 其他节点私有上下文、中央真值、运行 ID、完整计划和研究调用链 |
| Substrate | 任务、节点、拓扑、公共上下文、本轮动作和已路由候选消息 | `node_contexts`、`truth` 和基础设施凭证 |
| Channel | 已移除元数据的候选消息身份与正文 | 动作元数据、私有材料、真值和组件容器 |
| Detector | 最终投递消息身份与正文；可选公共实验上下文 | 隐写标签、秘密比特、解码材料和中央真值 |
| Reward | 动作类型/目标、实际投递消息与受限检测信号 | 检测理由/元数据/上下文、未投递正文、私有上下文、最终答案正文和 truth |
| Evaluator | 中央 Trial、真实运行结果和 `truth` | 不进入节点交互；属于受信任中央研究阶段 |
| Public Audit | 拓扑、实际投递消息和最小运行状态 | 提示、私有观察、调用链、真值和工具私有结果 |
| Research Audit | 计划、组件调用、实际结果与失败 | API 密钥等基础设施凭证会被脱敏 |

`shared_context` 的含义就是对全部节点公开。需要仅向一个节点提供的材料必须放在
`node_contexts.<node_id>`；只用于中央评分的标签必须放在 `truth`。

## 执行位置

```text
配置
  -> Scenario 生成 ExperimentPlan
  -> ThreatModelCompiler 编译有效清单
  -> Preflight 固定计划、插件和资源
  -> ExperimentPipeline 执行消息、检测器视图与奖励证据投影
  -> AuditJournal 保存双视图证据并封印
```

标准文件级 API 和 CLI 只有一条实验处理管线：

```text
Policy
  -> AgentAction.message
  -> Router
  -> Candidate Message
  -> Substrate
  -> Channel Transform
  -> Final Public Message
  -> Detector
  -> RewardRequest / Reward
  -> Delivery and Own Scalar Feedback
  -> Next-round Observation
```

直接调用 `MultiAgentBuilder` 属于低层嵌入方式，不经过配置预检和研究工件封印，
因此不能仅凭一次 Builder 运行声称满足本页的威胁模型证据契约。

Channel 之前会清除动作元数据；Channel 只能修改正文或阻断，不能修改消息 ID、
发送者、接收者和轮次。Detector 只检查经过全部 Channel 后实际允许投递的文本。
Reward 只接收最终消息和经过字段裁剪的 Detector 信号；Agent 不会得到 Detector
对象、检测理由或其他节点奖励，只在下一轮得到自己的合成标量。

## 隐写语义

StegoPot 不要求策略返回 `StegoAction` 或声明“正在隐写”。所有对外传输仍使用普通
`AgentAction.message`，避免把实验真值变成运行时可见的 oracle 标签。

工具化隐写实验可以由 Policy 调用注入的 `StegoCodec`，将生成的 Carrier 作为普通
消息发送；编码和解码事实只进入研究审计。涌现隐写实验则可以完全不调用 Codec，
由中央 Evaluator 根据独立真值评价行为。两种实验不能在结论中混写。

## 清单与核验

每次标准运行新增：

```text
outputs/<run-id>/threat-model.json
```

该文件记录有效开关、各组件字段视图、强制边界、信任假设、完整计划摘要和拓扑摘要。
`manifest.json` 保存它的文件摘要，根 `seal.json` 再封印两个文件。`verify` 会检查：

- 威胁模型文件属于根封印；
- `manifest.json` 引用的摘要与文件一致；
- `plan_sha256` 与预注册计划一致；
- `topology_sha256` 与计划中的全部节点和有向边一致；
- 日志、报告和各子试验封印仍满足原有完整性契约。

这些检查证明工件内部一致，不能替代数字签名、可信时间戳或独立保存的根哈希。

## 扩展约定

新增插件不需要读取 `ThreatModelManifest`。宿主应在调用插件前完成视图投影，插件只
实现自己的稳定接口。扩展不得通过全局容器索取额外信息，也不得把研究字段复制到
公开正文或公开事件中。

如果研究需要代码执行、文件访问或网络搜索，应以单独的受审计能力扩展实现，并明确
权限和隔离方式。StegoPot 核心当前不会因为工具研究需求而声称提供进程安全沙箱。
