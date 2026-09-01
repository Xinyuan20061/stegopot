# 数据契约

本目录保存前后端之间的版本化 JSON Schema。前端不得导入 StegoPot 的
Python 业务类型，只能通过 HTTP JSON 和这里定义的读取模型访问实验数据。

- `experiment-view-v1.schema.json`：实验详情公开/研究视图，版本 `1.0`。
- 后端模型变化后运行 `backend/scripts/export_contracts.py` 更新 Schema。
- 不兼容字段变更必须创建新的契约版本，不能覆盖旧版本语义。
