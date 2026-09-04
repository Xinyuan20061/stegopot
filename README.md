<p align="center">
  <img src="assets/stegopot-icon.png" alt="StegoPot" width="160">
</p>
<h1 align="center">StegoPot</h1>
<p align="center">开放接口、可配置拓扑、内置隐写能力与全过程审计的多智能体实验框架</p>

StegoPot 面向多 Agent 隐写研究。核心负责节点隔离、通信调度、隐写工具接入、
信道干预、运行预算和审计；论文复现、特定共谋协议与专用评价方法通过独立扩展包接入。
当前版本为 **0.6.0**，插件契约为 **1.0**，不是所有接口长期不变的稳定版承诺。

## 核心能力

- 自定义有向拓扑、同步轮次、局部收件箱和节点策略；同轮消息下一轮可见。
- 内置 StegoKit 适配器与载体级编解码接口，保留原有 Stego Substrate。
- 私有比特、公开载体、预共享材料、中央真值分离；检测器只接收最终公开消息。
- 可组合的信道变换、检测、奖励和中央评分；不需要修改运行器接入新算法。
- 显式插件允许列表、版本检查、严格配置校验、受限资源注入和统一生命周期。
- 双视图审计、实际模型与工具调用记录、失败保留、配对原文重放、报告封印校验。
- 装饰器注册与数据类参数模式，减少扩展包的重复接入代码。

**StegoKit 与基础审计是核心能力，不需要另外安装 StegoKit 插件。**
PyTorch/Transformers 按需加载；使用本地隐写模型才需要安装重型依赖。
DeepSeek 是可选供应商扩展，共谋复现是可选实验扩展。

## 快速开始

在仓库根目录、项目自己的虚拟环境中运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m stegopot validate experiments/basic.yaml
.\.venv\Scripts\python.exe -m stegopot run experiments/basic.yaml
```

基础实验不调用外部 API。运行输出包含本次结果目录，查看其中的
`report.md` 和 `experiment-report.json`：

```powershell
.\.venv\Scripts\python.exe -m stegopot verify artifacts/experiments/<本次运行目录>
.\.venv\Scripts\python.exe -m stegopot plugins inspect core
```

PyCharm 解释器选择本项目 `.venv\Scripts\python.exe`，工作目录选择仓库根目录，
以模块 `stegopot` 运行，参数填写 `run experiments/basic.yaml`。

## 核心隐写实验

直接运行无需下载模型的真实 AC 接线示例（使用微型模型，不调用 API）：

```powershell
.\.venv\Scripts\python.exe examples/standard_stego_demo.py
```

它经过新载体接口和统一审计，接收端只从实际收到的文本恢复比特。
模型和短语词表仅供测试，不用于证明自然度、不可检测性或 LLM 自发共谋。

使用自己的本地模型：

```powershell
git submodule update --init --recursive
.\.venv\Scripts\python.exe -m pip install -e ".[stego]"
.\.venv\Scripts\python.exe -m stegopot run experiments/stego/local-model.yaml
```

运行前修改该配置的 `resources.codec.config.model_path` 为本地因果语言模型目录。
示例只加载本地文件，不自动下载模型，不允许远程模型代码。
算法需要匹配的 tokenizer/chat template；文本与 token 不能一致往返时明确失败，
不会把编码端内部 token ID 暗中交给接收者。

`core.codec_sender/receiver` 是工具节点，不代表 LLM 自主推断。
已有真实 AC 算法微型模型演示仍可用：

```powershell
.\.venv\Scripts\python.exe examples/steganography_interaction_demo.py
```

该旧演示验证算法和授权链路，使用内部 token 侧信息；文本信道研究应优先使用
新 `StegoCodec` 契约，并核查实际接收载体。

## 扩展实验

```powershell
.\.venv\Scripts\python.exe -m pip install -e extensions/stegopot-collusion
.\.venv\Scripts\python.exe -m stegopot run experiments/collusion/offline.yaml
```

离线版本是确定性接线测试，不是模型共谋证据。真实 DeepSeek 配置另需：

```powershell
.\.venv\Scripts\python.exe -m pip install -e extensions/stegopot-deepseek
.\.venv\Scripts\python.exe -m stegopot validate experiments/collusion/deepseek.yaml --env-file .env
.\.venv\Scripts\python.exe -m stegopot run experiments/collusion/deepseek.yaml --env-file .env
```

`.env` 使用 `DEEPSEEK_API_KEY`。密钥不写入 YAML，也不提交 Git。
最后一条命令会产生 API 费用；`validate` 不创建模型客户端、不发起模型请求。
共谋扩展是**人工提供共享协议的指令式能力实验**，不证明激励驱动的自发共谋。

## 配置与开发

修改 `scenario.config.nodes` 和 `edges` 即可定义基础拓扑；
也可用顶层 `policies`、`topology` 覆盖场景默认声明。
启用的插件必须同时已安装在当前解释器，并列入配置 `plugins`。

```text
stegopot/
  domain/          稳定模型、开放接口、注册契约
  application/     多节点引擎、统一实验用例
  infrastructure/  核心隐写、检测、模型策略、配置与审计
  bootstrap/       注册、依赖组装、统一 CLI
extensions/        独立实验与供应商包
templates/plugin/  可安装的装饰器扩展示例
stegopot-console/  独立前后端，未适配本次新报告格式
```

接口与示例见 [扩展开发指南](docs/plugin_development.md)，
分层规则见 [架构说明](ARCHITECTURE.md)。
通过 `python -m stegopot schema` 获取顶层 JSON Schema，
通过 `plugins inspect <名称>` 获取组件参数与资源声明。

## 审计边界

每次运行固定配置、展开计划、组件版本及 Python 源码摘要，保存所有成功、
失败和跳过的试验。每个目录包含独立研究日志与公开日志，根封印关联全部子试验。
完整研究报告可能包含合成秘密和提示词，**不能直接公开或送入前端**。
公开日志不包含中央私有字段，但无法撤回模型在消息正文中主动泄露的信息。

哈希链检查完整性，不是数字签名；应把根 `seal.json` 的 SHA-256 独立保存。
同时重写全部日志和封印时，没有外部锚点就不能证明原始性。
插件是可信 Python 代码，接口限制不等于进程安全沙箱。
热插拔指实验之间切换组件，不支持运行中替换模块。
调用预算限制经宿主接口的调用次数，时间限制是试验边界的软截止。

## 测试

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

真实 API 测试默认跳过；StegoKit 算法测试需要 `.[stego]` 依赖。
[历史共谋实验记录](docs/collusion_reproduction.md) 保留其原始版本与证据说明。

## 许可

核心采用 [Apache-2.0](LICENSE)。StegoKit 保留上游源码、许可证及固定子模块版本；
衍生算法的适用条件应同时参考对应上游实现。
