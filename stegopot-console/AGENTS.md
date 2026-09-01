# StegoPot Console 开发约束

本目录位于仓库根目录，是与 `stegopot` Python 业务包平级的独立展示工具。

## 依赖边界

```text
frontend -> HTTP JSON contract -> backend projection -> report JSON
```

- `frontend/` 不得引用 Python 源码或核心业务对象。
- `backend/` 不得导入 `stegopot` 包，只能读取其标准 JSON 报告。
- 完整研究报告必须先经过 `app/projector.py`，不得直接返回浏览器。
- 公开视图不得包含秘密比特、解码比特、逐消息真实标签或原始观察。
- 研究数据只能放在 `ExperimentView.research` 中。
- 前后端不兼容变更必须升级 `schema_version` 并保留旧契约。

## 代码与验证

- Python 注释、文档字符串和参数说明使用中文。
- React 组件按单一界面职责拆分，禁止把数据读取逻辑写入展示组件。
- 图标使用 Lucide，拓扑交互使用 React Flow。
- 后端测试：`backend/.venv/Scripts/python.exe -m pytest -q`。
- 前端验证：在 `frontend/` 执行 `npm run build`。
