# StegoPot 架构

## 定位

StegoPot 提供一类 LLM 隐写与多智能体实验共同需要的底层能力：

```text
StegoPot Core
  = Controlled Model Runtime
  + Dataset Pipeline
  + Research Lifecycle
  + Multi-Agent Runtime
  + Steganography Foundations
  + Plugin and Audit Contracts
```

具体实验由配置和外部插件组成。核心提供通用 EAP 基础实现，但不知道秘密比特、
clean/corrupt、carrier、线性 Probe 或某篇论文场景的含义。

## 四层目录

```text
stegopot/
  domain/
    model/          通用值对象：TensorRef、Trace、Sample、Context、消息和拓扑
    interface/      ModelAdapter、Dataset、Probe、Scenario、Plugin 等协议
  application/
    engine/         多 Agent 节点、路由、环境和轮次状态
    services/
      runtime/      ModelRuntime、事件总线和基础干预算子
      data/         数据流水线及逐层 Probe 数据视图
      research/     通用实验生命周期
      experiments/ 多 Agent 场景与执行
      rewards/      多 Agent 奖励
  infrastructure/
    model_adapters/ Hugging Face 可控模型适配
    llm/            Chat Completions 黑盒客户端与 Agent 策略
    integrations/   StegoKit、EAP 等核心能力集成
    storage/        实验工件和磁盘张量
    plugins/        已安装插件发现
    recorders/      多 Agent 审计
    settings/       配置和工作区
  bootstrap/
    experiments/    v1/v2 配置、组件组装、CLI 和文件级 API
```

## 依赖方向

| 区域 | 可依赖 |
| --- | --- |
| domain.model | 标准库和自身 |
| domain.interface | domain |
| application | domain、application |
| infrastructure | domain、infrastructure |
| bootstrap | 全部层，仅负责组装 |

实现层不得反向导入 `bootstrap`。所有 Protocol 位于 `domain/interface`。

## 稳定抽象

1. `ModelAdapter`：把模型生态映射为 capability。
2. `ModelRuntime`：统一检查能力、合并干预并管理后端生命周期。
3. `TensorRef`：统一定位 module/layer/component/token。
4. `ActivationTrace`：保存选择性激活和可选梯度。
5. `EAP`：根据显式 source delta、target gradient 与 edge 定义计算通用归因。
6. `Intervention`：把外部算子绑定到目标与可选条件。
7. `Sample` / `DatasetBundle`：不包含实验特定语义的数据边界。
8. `ResearchScenario`：定义一个样本如何发生。
9. `ComponentDefinition`：插件工厂、依赖、凭证和 capability 声明。

## 两条执行链

通用机制实验使用 v2 配置：

```text
Config v2
 -> PluginCatalog / capability preflight
 -> ComponentSession
 -> ModelAdapter -> ModelRuntime
 -> DatasetPipeline
 -> ResearchScenario
 -> Analyzer -> Metric -> Reporter
 -> FileArtifactStore
```

多 Agent 实验继续使用 v1 配置：

```text
Config v1
 -> ScenarioProvider -> ExperimentPlan
 -> ThreatModelCompiler
 -> MultiAgentRuntime
 -> Channel / Detector / Reward / Evaluator
 -> AuditJournal
```

两条链共用插件目录、配置读取、凭证约定和 CLI。它们没有两套注册系统。

## 后端能力

`core.huggingface` 提供 forward、generation、token-step control、activation read/write
和 gradient read。`core.chat_completions` 是多 Agent 可用的黑盒 LLM 资源，不声明模型
内部能力。外部 TransformerLens、vLLM 或自定义后端通过 `model_adapter` 插件接入。

## 保持轻量

- PyTorch/Transformers 是 `whitebox` 可选依赖。
- 默认只采集显式 TensorRef；不默认保存所有层。
- Trace 可留在设备、转 CPU 或写外部 TraceStore。
- 基础 EAP 随核心安装；EAP-IG、AtP、Probe 模型、SAE 和论文协议由插件提供。
- 只有 `FileArtifactStore`、基础张量算子和 Hugging Face 适配器作为参考实现。

## 信任边界

第三方插件是同进程可信代码。宿主限制正常接口能看到的资源、凭证和数据，但不能阻止
恶意 Python 代码直接访问进程、文件或网络。需要强隔离时应在外部容器或受限进程中运行。
