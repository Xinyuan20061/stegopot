# StegoPot 开发约束

修改代码前阅读 `docs/architecture.md`。StegoPot 是面向 LLM 隐写通信、内部机制与
多智能体研究的轻量实验底座，不是某篇论文、某种归因算法或某个演示实验的实现。

## 核心边界

核心只负责以下不可替代能力：

- 模型后端能力声明与统一适配；
- 可控 forward 和逐 token generation；
- 指定 layer/component/token 的 activation 与 gradient 访问；
- 作用域明确、异常后必清理的运行时干预；
- 通用 Sample 的生成、变换、验证、分组切分和指纹；
- 从 ActivationTrace 构造 Probe 数据的接口；
- Dataset -> Scenario -> Analyze -> Evaluate -> Save 生命周期；
- 多 Agent 通信、信息投影、StegoKit、检测、奖励和审计；
- 插件注册、依赖注入、预检、能力匹配和资源关闭。

下列内容必须由外部插件或用户配置实现：

- EAP、AtP、SAE、特定 Probe 训练器和归因公式；
- clean/corrupt、secret pair、单比特协议等实验语义；
- 论文场景、数据内容、标签规则、指标与报告样式；
- 特定模型架构的非通用 head/circuit 映射；
- 可视化应用和历史实验结果。

## 最小化原则

- 新增模块前先证明现有 Protocol、组件 kind 或事件无法表达该需求。
- 能由插件的 20 至 50 行实现完成的实验语义，不在核心增加平行服务。
- 不因“以后可能使用”预置算法、配置字段或抽象层。
- 一个职责只能有一套稳定入口；禁止同时保留专用白盒 API 和通用 TensorRef API。
- 适配器只翻译后端，不实现研究算法；运行时只调度，不解释实验标签。
- 删除功能前检查真实调用者、公开契约和资源生命周期；不要为追求目录短小破坏扩展点。

## 四层结构

```text
bootstrap -> application -> domain
         \-> infrastructure -> domain
```

- `domain/model`：无外部依赖的值对象。
- `domain/interface`：全部 Protocol、插件声明与稳定契约。
- `application/engine`：多 Agent 状态与消息运行。
- `application/services`：通用运行时、数据和实验编排。
- `infrastructure`：模型、网络、文件、插件发现和 StegoKit 实现。
- `bootstrap`：配置、CLI、组件组装和生命周期所有权。

仓库只允许这四个顶层包。不要增加 `core`、`runtime`、`adapters` 等第五个物理层；
这些概念应作为现有四层内部的逻辑子目录表达。

## 接口与能力

- 抽象接口集中在 `domain/interface`，实现目录不得声明 Protocol/ABC。
- 插件通过 `@Plugin.component` 注册，不使用全局可变注册表。
- 配置对象拒绝未知字段；所有 dataclass 参数必须提供中文 `metadata.description`。
- 插件依赖模型能力，不依赖具体后端类。
- API 模型可以作为黑盒 `llm` 资源；只有真实支持 Hook 的后端才能声明
  `activation_read`、`activation_write` 或 `gradient_read`。
- capability 缺失必须在模型加载和实验执行前失败。
- TensorRef 无法解析时显式失败，不猜测未知架构。

## 数据与安全

- 通用 `Sample` 不包含 secret、carrier 或 clean/corrupt 等特定语义。
- 中央标签只在 Dataset、Analyzer、Metric 或 Probe 数据边界内流动。
- activation 原值不进入 RuntimeEvent 或普通 JSON 审计；磁盘轨迹只记录引用和摘要。
- `.env`、模型凭证、用户配置、测试、输出和 activation 工件不得提交。
- 插件按 `trusted_in_process` 运行；接口隔离不是操作系统安全沙箱。
- 文件写入必须独占，不能静默覆盖已有运行。

## 代码规范

- 注释、docstring 和面向用户的错误信息使用中文；标识符使用英文。
- 公开构造器和方法说明每个参数、返回值及所有权。
- 高内聚、低耦合；优先组合已有对象，不创建万能 manager 或 utils。
- 重型依赖惰性导入；基础安装不强制安装 PyTorch/Transformers。
- Hook、会话、模型、文件和插件资源必须在成功与异常路径中释放。
- 不吞异常，不把失败样本当成阴性，不伪造完成或封印状态。

## 验证

- 本地 `tests/contracts` 被 Git 忽略，只验证框架契约，不上传。
- 修改后运行完整契约测试、源码编译、wheel 构建和隔离安装。
- 白盒运行至少验证：选择性采集、梯度回收、真实干预、Hook 清理、逐 token 提交。
- 插件至少验证：严格 schema、依赖引用、capability 预检、失败关闭和向后兼容。
- 文档、版本号、内置插件版本与公开 API 必须一致。
