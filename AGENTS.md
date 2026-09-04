# StegoPot 开发约束

修改前阅读 docs/architecture.md。项目是开放的多 Agent 隐写实验框架，不是论文实验集合。

## 仓库边界

- 源码只放 stegopot，用户配置只放 configs，文档只放 docs。
- 不重新加入旧实验、历史结果、Console、演示脚本或论文专用扩展。
- tests/contracts 只在本地维护宿主契约回归，不提交 GitHub、不随安装包分发；不得强制添加被忽略的测试。
- configs 只提交 README.md；用户配置和子目录由 .gitignore 排除，文档可说明格式，不默认附带可运行实验。
- outputs 运行时按需创建，不能提交研究数据；.env 保留且不得提交或回显。
- 正式第三方插件独立开发和安装，不把它们的场景或评分硬编码进内核。
- 保留根 README、AGENTS、打包配置及许可文件；不随意移动 .venv 和 IDE 环境。

## 四层依赖

依赖方向：bootstrap -> application / infrastructure -> domain。

- domain/model 只依赖自身和标准库；所有 ABC/Protocol 放 domain/interface。
- application/engine 处理轮次、路由、隔离与管线；application/services 编排通用用例。
- application 不导入具体配置读取器、供应商或记录器；依赖领域接口。
- infrastructure 提供工作区、配置、模型、隐写、插件发现、检测和审计实现。
- infrastructure/recorders 只接收标准 Mapping，不反向导入应用报告类型。
- 同一能力内部按职责分目录，不创建混合职责的 utils/tools/core。
- bootstrap 只接入、预检、组装和管理资源所有权，不编写实验算法。
- stegopot 根目录只保留 domain、application、infrastructure、bootstrap 四个逻辑层。

## 接口与参数

- 优先使用 domain/interface/registration.py 的 Plugin 装饰器，不使用全局可变注册表。
- 组件统一为 type/config，数据类参数必须有中文 metadata.description。
- 公共函数有类型注解和中文参数、返回值、所有权及失败边界说明。
- 注释与文档字符串使用中文；不改变第三方 vendor 源码的原始声明。
- 模型、codec 和审计通过声明槽位注入，组件不得访问未授权资源。
- 宿主拥有注入资源，组件不得重复关闭依赖；工厂失败自行释放未移交资源。
- 插件只能导入 stegopot.domain 契约，不反向依赖框架引擎和基础设施。
- 安装与启用分离，仅配置明确允许的 entry point 可加载；不执行目录内任意脚本。

## 隐写与审计

- StegoKit、隐写接口、通信隔离、基础检测和强制审计属于核心能力。
- 私有比特、公开载体、预共享材料、中央真值必须显式分离。
- 新载体接口按实际收到的文本解码，不暗传编码端 token ID。
- 检测器只读最终公开消息，不读取私有标签和密钥；节点不自动获得中央种子。
- CLI 和文件级 API 不允许关闭宿主审计；写入失败立即中止，不伪造完整封印。
- 记录真实请求、响应、工具调用、信道干预和失败；不得把失败当阴性样本。
- 配对重放与真实生成、工具结果与模型决策必须区分；研究数据不得直接公开。
- 模型适配器不得自动重试或绕过宿主预算；不从配置文本直接读取 API 密钥。
- ExecutionGuard 由应用层实现，模型、codec 和运行器只依赖领域契约；停止后仍须释放资源。
- 取消与时间上限为协作式检查，不声称能够强制终止第三方线程或网络请求。
- 调用链标识只进入研究事件，不能加入节点观察、公开消息或公开审计投影。
- 纯 preflight 钩子只接收当前组件与节点材料副本，不构造模型、不读取凭证、不联网。
- 凭证文件读取不能修改全局环境；不同工作区之间不得隐式共享文件凭证。

## 验证

- 手动编辑使用 apply_patch，不还原用户变更；结构变化同步 README 与架构文档。
- 不恢复旧实验测试；新的框架契约测试集中在 tests/contracts，夹具和结果只进入临时工作区。
- 本地具备测试时，修改内核后执行 python -m unittest discover -s tests/contracts -v；同时检查独立分发包。缺少测试时应明确说明验证范围。
- 验证配置发现、歧义拒绝、拓扑隔离、资源注入、失败记录、审计封印和安装包独立运行。
- 检查目录和依赖方向；打包前初始化 StegoKit 子模块，避免发布缺失核心能力的包。
- 默认只运行离线或本地模拟请求；付费 API 必须明确授权，临时结果不留在仓库。
