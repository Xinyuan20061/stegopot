<div align="center">

# StegoPot Console

**StegoPot 多智能体隐写检测实验的独立报告工作台**

</div>

StegoPot Console 位于 StegoPot 仓库根目录，是与 Python 业务包隔离的展示
子项目。它只读取 JSON 实验报告，不会把 FastAPI、React 或前端组件引入
核心业务依赖。

## 目录结构

```text
stegopot/
├── stegopot/                # Python 四层业务包
├── examples/
├── artifacts/
└── stegopot-console/        # 独立展示子项目
    ├── backend/             # 报告仓储、脱敏投影和 HTTP API
    │   ├── app/
    │   ├── scripts/
    │   └── tests/
    ├── frontend/            # React 实验工作台
    │   └── src/
    ├── contracts/           # 版本化 JSON Schema
    └── README.md
```

## 已有功能

- 浏览、搜索和导入 StegoPot JSON 实验报告。
- 查看节点角色、自定义有向拓扑和消息路径。
- 查看 Precision、Recall、F1、比特恢复率与检测耗时。
- 按消息、检测记录和同步轮次检查完整交互过程。
- 在公开视图中隔离秘密比特和逐消息真实标签。
- 在研究视图中关联隐写载荷、解码结果和检测结局。

## 运行

以下命令从 StegoPot 仓库根目录执行。先确保核心项目中至少有一份报告：

```powershell
.\.venv\Scripts\python.exe -B .\examples\stego_detection_demo.py
```

首次安装后端：

```powershell
cd ".\stegopot-console\backend"
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

安装并构建前端：

```powershell
cd "..\frontend"
npm install
npm run build
```

启动统一服务：

```powershell
cd "..\backend"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8787
```

浏览器打开 `http://127.0.0.1:8787`。后端默认读取仓库根目录的
`artifacts/detection/`，也可以通过 `STEGOPOT_REPORT_DIR` 指定目录。

## 开发模式

后端运行在 `8787` 端口后，在另一个终端启动 Vite：

```powershell
cd .\stegopot-console\frontend
npm run dev
```

开发页面地址为 `http://127.0.0.1:5173`，`/api` 会代理到后端。

## 数据边界

```text
ExperimentReport JSON
        ↓
ReportProjector
        ↓
ExperimentView 1.0
        ↓
HTTP JSON
        ↓
React Console
```

公开接口不会返回动作元数据、节点原始观察、`secret_bits`、`decoded_bits`、
`ground_truth` 或逐消息 `outcome`。研究视图是单独的显式请求范围。
