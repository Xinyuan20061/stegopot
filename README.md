# StegoPot 多智能体实验框架

这个仓库已经从 Google DeepMind Melting Pot 裁剪成一个轻量的
多智能体实验框架。当前版本先实现通用的 LLM 多节点交互、自定义
通信拓扑、同步调度和完整运行记录，暂不包含隐写相关逻辑。

## 当前可用功能

- 创建任意数量的 LLM 或自定义 Policy 节点
- 使用任意有向图定义节点间的通信权限
- 支持定向消息和向全部出邻居广播
- 支持环形、星形、全连接和手工连接拓扑
- 按同步轮次调度，消息在下一轮送达
- 支持最大轮数、任一节点完成、全部节点完成三种终止方式
- 支持严格或宽松的非法路由处理
- 保存每轮观察、动作、消息转录、最终答案和错误记录
- 支持 Mock 模型离线测试和 DeepSeek API 真实运行

## 模块结构

```text
meltingpot/utils/multi_agent/
├── topology.py       # 节点、边和预定义拓扑
├── message.py        # 消息对象和拓扑路由
├── node.py           # 节点身份、Policy 和内部状态
├── observation.py    # 局部观察构造，可在以后插入隐写处理
├── runtime.py        # 同步轮次、终止条件和运行记录
└── builder.py        # 面向使用者的链式构建入口
```

一次运行的数据流如下：

```text
上一轮收件箱 -> ObservationBuilder -> AgentNode/Policy -> AgentAction
                                                        |
下一轮收件箱 <- MessageRouter <- AgentTopology <--------+
```

## 在 PyCharm 中运行

项目解释器选择仓库中的：

```text
.venv\Scripts\python.exe
```

把仓库根目录设为运行配置的工作目录。先直接运行：

```text
examples/multi_agent_mock_demo.py
```

该示例不访问网络，会运行下面的自定义拓扑：

```text
planner -> writer <-> reviewer
```

## 使用 DeepSeek

仓库根目录的 `.env` 至少需要包含：

```dotenv
DEEPSEEK_API_KEY=你的真实密钥
DEEPSEEK_MODEL=deepseek-v4-flash
```

然后在 PyCharm 中运行：

```text
examples/multi_agent_deepseek_demo.py
```

这个示例最多运行 4 轮。每个仍处于活跃状态的节点在每轮会产生
一次模型请求，实际请求次数取决于节点何时输出 `final_answer`。

## 自定义多智能体系统

```python
from meltingpot.utils.llm import DeepSeekClient
from meltingpot.utils.multi_agent import MultiAgentBuilder
from meltingpot.utils.multi_agent import RuntimeConfig

builder = MultiAgentBuilder()

builder.add_llm_node(
    node_id="planner",
    role="规划者",
    client=DeepSeekClient(),
    system_prompt="拆解任务，并把方案发给 worker。",
)
builder.add_llm_node(
    node_id="worker",
    role="执行者",
    client=DeepSeekClient(),
    system_prompt="执行 planner 的方案并给出最终答案。",
)

# 有向边表示 planner 可以直接给 worker 发消息。
builder.connect("planner", "worker")

runtime = builder.build(config=RuntimeConfig(
    max_rounds=5,
    termination_mode="any_final",
))

with runtime:
  result = runtime.run(
      "完成一个示例任务",
      shared_context={"language": "zh-CN"},
  )

print(result.final_answers)
print(result.messages)
```

消息动作的 `target` 必须满足拓扑约束：

- 指定节点 ID：只投递给该直接出邻居
- `null` 或 `"*"`：广播给发送者的全部直接出邻居
- 非邻居：严格模式下立即报错，宽松模式下记录并丢弃

## 预定义拓扑

不使用 Builder 时，也可以直接创建拓扑并传给 `MultiAgentRuntime`：

```python
from meltingpot.utils.multi_agent import AgentTopology

ring = AgentTopology.ring(["a", "b", "c"])
star = AgentTopology.star("center", ["a", "b", "c"])
complete = AgentTopology.complete(["a", "b", "c"])
custom = AgentTopology.from_edges([
    ("a", "b"),
    ("b", "c"),
    ("c", "b"),
])
```

## 运行测试

在项目根目录执行：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

默认测试全部离线，不会消耗 DeepSeek API 额度。原有真实 API 测试仍然
只有在显式设置 `RUN_DEEPSEEK_LIVE_TEST=1` 后才会运行。
