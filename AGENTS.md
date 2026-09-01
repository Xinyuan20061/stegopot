# StegoPot 开发约束

修改本仓库前先阅读 `ARCHITECTURE.md`。项目采用四层结构，依赖方向只能是：

```text
bootstrap -> application / infrastructure -> domain
```

## L0：领域层

- 稳定数据模型和领域规则放在 `stegopot/domain/model/`。
- 所有 ABC、Protocol 和稳定扩展契约放在 `stegopot/domain/interface/`。
- `domain/model` 不得依赖 StegoPot 的其他逻辑区域。
- `domain/interface` 只能依赖 `domain/model` 和自身。

## L1：应用层

- 节点状态、观察构建、消息路由和轮次调度放在
  `stegopot/application/engine/`。
- 面向完整用例的应用服务放在 `stegopot/application/services/`。
- 应用层只能依赖领域层，不得导入 DeepSeek、StegoKit 或具体 Substrate。

## L2：基础设施层

- LLM 策略、提示、解析器和客户端放在 `stegopot/infrastructure/llm/`。
- 隐写检测器实现放在 `stegopot/infrastructure/detectors/`，并且只能依赖
  `StegoDetector`、检测领域模型及注入的稳定能力接口。
- Substrate 实现放在 `stegopot/infrastructure/substrates/`；复杂功能必须使用
  独立子目录，例如 `substrates/stego/`。
- 第三方 SDK 适配器放在 `stegopot/infrastructure/integrations/<provider>/`。
- 环境变量等技术配置放在 `stegopot/infrastructure/settings/`。
- JSON、数据库等报告记录器放在 `stegopot/infrastructure/recorders/`，记录器
  只能接收标准映射，不能反向导入应用层报告类型。
- 固定的上游源码放在 `stegopot/infrastructure/vendor/<project>/`。
- Stego Substrate 必须依赖 `StegoTool`，不能直接导入 StegoKitAdapter 或 StegoKit。
- Detection Substrate 必须依赖 `StegoDetector`，不能直接导入具体检测器。
- 检测器只能读取公开消息，不得读取秘密比特、算法材料或中央真实标签。

## L3：启动层

- 对象组装、默认实现选择和 Builder 放在 `stegopot/bootstrap/`。
- 只有启动层可以同时导入应用层和多个基础设施实现。
- 业务算法不得写入 Builder。

## 禁止事项

- 不得在 `stegopot/` 根目录新增第五个平级逻辑包。
- 不得重新创建 `core`、`interface`、`llm`、`substrates` 等根级技术包。
- 不得创建职责混杂的 `utils`、`tools` 或空 `configs` 目录。
- 不得通过根包大范围重导出隐藏真实依赖路径。
- 内层组件必须通过构造参数接收接口，不能直接实例化外层具体实现。

## 代码与测试

- 新增和修改的注释、文档字符串使用中文。
- 公共类、函数及其参数必须有完整说明。
- 修改行为时增加对应单元测试。
- 修改目录或依赖时同步更新 `ARCHITECTURE.md` 和架构测试。
- 完成前运行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
