# 内核控制与审计

本页对应 StegoPot 0.8.0 / 插件 API 1.1。新增能力遵守四层依赖：
领域层声明数据与契约，应用层控制执行，基础设施实现诊断和日志，组装层连接配置与入口。

## 执行预算

在用户完整实验配置的 runtime 中设置以下参数：

| 参数 | 默认值 | 含义 |
| --- | --- | --- |
| max_model_calls | 64 | 整组模型调用上限；1 到 100000 |
| max_model_calls_per_trial | 不额外限制 | 单次试验模型调用上限；正整数 |
| max_model_calls_per_node | 不额外限制 | 单次试验中每节点模型调用上限；正整数 |
| max_tool_calls | 256 | 整组 codec 编码与解码总调用上限；正整数 |
| max_tool_calls_per_trial | 不额外限制 | 单次试验工具调用上限；正整数 |
| max_tool_calls_per_node | 不额外限制 | 单次试验中每节点工具调用上限；正整数 |
| max_output_tokens | 1024 | 每次宿主模型请求的输出 token 上限；1 到 65536 |
| max_total_tokens | 1000000 | 累计服务端已报告 total_tokens 上限；正整数 |
| max_message_bytes | 65536 | 单条正文 UTF-8 字节上限；正整数 |
| max_context_bytes | 1000000 | 单次观察、模型输入、工具请求等 JSON 序列化后的 UTF-8 字节上限；正整数 |
| max_rounds | 100 | 允许计划的轮数上限；1 到 10000，实际轮数仍由场景声明 |
| max_trials | 1000 | 允许计划的试验数上限；1 到 10000 |
| max_seconds | 3600 | 执行阶段协作式截止秒数；正数，不包含预检阶段 |

未声明的局部调用上限不额外生效；不要填写 null 或 0 代表无限。
较大的上限不代表本机具有相应资源，仍须匹配模型和硬件。

- 通过宿主注入模型的 generate，或 codec 的 encode/decode，在调用前原子预占一次额度。调用失败仍占用已预留次数。
- 工具调用目前指 codec 接口，不是任意 Python 函数；codec 内部本地生成不额外算远程模型请求。
- 局部额度耗尽只使当前试验失败；全局耗尽阻止后续试验。中央 evaluator 只使用全局调用预算。
- 恰好达到 token 上限时拒绝下一次模型请求；单次响应导致超额时，保留真实响应后在下一检查点停止。
- total_tokens 缺失或不可用增加 calls_without_token_usage，不宣称为真实零消耗，不估算未返回费用。
- 消息在路由和信道处理前后检查大小；超限失败，不截断载体或悄悄改变隐写内容。
- max_context_bytes 是宿主 JSON 载荷限制，不等同于供应商 token 窗口，也不是进程内存上限。

预算依赖可信插件遵守注入和一次调用契约。插件不得自行创建未审计客户端、隐藏重试或绕过宿主联网。
框架不是操作系统级沙箱，不能对恶意插件提供硬费用或资源保证。

## 协作式取消

Python 嵌入调用不修改进程信号处理器：

```python
from threading import Timer

from stegopot.bootstrap.experiments.api import run_file
from stegopot.domain.model.execution import CancellationToken

token = CancellationToken()
timer = Timer(30, token.cancel)  # 30 秒后请求取消，不强制终止模型计算。
timer.start()
try:
    report, directory = run_file(
        "communication",
        workspace="D:/Research/my-workspace",
        cancellation=token,
    )
finally:
    timer.cancel()
print(report["status"], report["execution"], directory)
```

cancel() 可重复调用，也可从其他线程调用；cancelled 属性读取当前状态。
已取消令牌不用于新实验，每次新运行应创建新令牌。

节点、轮次、模型/工具、环境处理、组件构造和中央评价等边界设置检查点。
若取消发生在请求内部，框架等待该调用返回或由客户端超时退出，
先记录实际得到的响应，再停止后续执行。长时间阻塞的任意插件不会被强制杀死。

CLI 首次 Ctrl+C 请求取消，尽量完成资源关闭和失败/跳过报告封印；
再次 Ctrl+C 抛出 KeyboardInterrupt，可能留下未封印目录。
杀进程、断电或审计介质故障也无法保证完整报告。

### 报告兼容性

继续使用 stegopot.report/1，不改变原有状态枚举：

| 情况 | 记录 |
| --- | --- |
| 正常完成 | trial.status 为 completed |
| 执行中取消、超时、额度或载荷超限 | 当前试验通常为 failed，error.code 说明原因 |
| 全局停止后的未开始试验 | skipped，不调用其模型或评价器 |
| 局部额度耗尽 | 当前试验 failed，其他独立试验仍可执行 |
| 开始前已取消 | 计划中试验均 skipped，整组 partial |
| 仅汇总被全局停止 | 正常试验保持 completed，整组 partial |
| 协议输出非法 | protocol_error，不生成替代动作或虚构响应 |

试验 error 保留首个错误，errors 保存后续错误，避免评价失败覆盖原始运行失败。
整组有失败试验即为 failed；无失败但有跳过或全局停止导致汇总未完成时为 partial。
execution.stop_reason 仅表示全局停止原因，局部超限须看试验错误。

稳定分类包括 cancelled、deadline_exceeded、budget_exceeded、payload_exceeded、
protocol_error 和普通组件的 component_error。
受控停止另带 resource，例如 max_tool_calls_per_node，指出触发的限制。

## 预检与离线诊断

```shell
python -m stegopot validate communication
python -m stegopot doctor communication
```

两者不构造模型、不发送付费请求。场景生成和插件钩子是可信代码，
必须遵守无副作用约定，框架没有在操作系统层禁止任意第三方代码联网。

validate 在参数模式、资源引用和计划校验基础上调用纯预检钩子。
内置策略检查活动轮次、发送目标、出邻居、必要私有比特和预共享材料。
最后一轮消息无法在本试验下一轮读取时给出警告，不一律拒绝。
重放覆盖的发送节点不再要求执行原策略所需的模型或秘密材料。

doctor 额外检查已知 StegoKit 资源的安装元数据、供应商源码、本地模型目录、
config.json、常见 tokenizer 文件、权重文件或分片索引。
不下载权重、不导入重型推理包、不验证远程账户，不证明架构、算法和 tokenizer 实际兼容。
ready 仅表示已实施的检查没有 error；network_checked 固定为 false。

```python
from stegopot.bootstrap.experiments.api import diagnose_file
from stegopot.domain.model.diagnostic import PreflightError

try:
    diagnostics = diagnose_file("communication", workspace="D:/Research/my-workspace")
except PreflightError as error:
    diagnostics = error.diagnostics
for item in diagnostics:
    print(item.to_dict())
```

Diagnostic 包含 code、path、message、hint、severity 和可选 component。
error 阻止预检，warning 提示风险，info 说明检查范围。
模式和钩子错误可读取 PreflightError.diagnostics；文件、解析和部分基础计划错误
仍可能是原有异常类型，不应假设所有入口异常都是 PreflightError。
diagnose_file 将环境不就绪作为 error 级诊断返回，调用者应检查 severity。

## 扩展预检

API 1.1 新增可选 preflight 声明，未声明的 API 1.0 插件继续工作。
数据类注册时，工厂和预检收到同一种已验证参数对象：

```python
from dataclasses import dataclass, field

from stegopot.domain.interface.plugin import BuildContext
from stegopot.domain.interface.registration import Plugin
from stegopot.domain.model.action import AgentAction
from stegopot.domain.model.diagnostic import Diagnostic, PreflightContext

plugin = Plugin("checked", "0.1.0")

@dataclass(frozen=True)
class SendConfig:
    target: str = field(metadata={"description": "接收节点 ID，必须是当前节点的出邻居"})
    content: str = field(metadata={"description": "首次发送的公开正文，不包含秘密材料"})

def check_send(config: SendConfig, context: PreflightContext) -> list[Diagnostic]:
    """config 为已验证参数；context 只含当前节点的拓扑和授权材料。"""
    if config.target not in context.outgoing:
        return [Diagnostic(
            code="checked.target",
            path=context.path + ".target",
            message="接收者不是当前节点的出邻居",
            hint="调整发送目标或显式添加有向边",
        )]
    return []

class SendOnce:
    """一次发送策略；只有节点局部状态，不拥有外部资源。"""

    def __init__(self, config: SendConfig) -> None:
        """config 保存预检通过的目标和正文。"""
        self._config = config

    def initial_state(self):
        """返回是否已发送的初始状态。"""
        return False

    def step(self, observation, prev_state):
        """observation 为局部观察；prev_state 为发送标记；返回动作和新状态。"""
        if prev_state:
            return AgentAction(kind="wait", content=""), prev_state
        return AgentAction(
            kind="message", target=self._config.target, content=self._config.content,
        ), True

    def close(self) -> None:
        """无资源需要释放。"""

@plugin.component("policy", "send_once", config=SendConfig, preflight=check_send)
def build_send(config: SendConfig, context: BuildContext) -> SendOnce:
    """config 为预检参数；context 为构造上下文，本组件无需资源。"""
    return SendOnce(config)
```

PreflightContext.path 定位组件；node_id、max_rounds、outgoing、incoming 表示当前节点和试验。
无对应作用域时节点/轮次为 None，邻居为空。
private 是该节点授权材料的独立副本，不提供其他节点私有材料、中央真值、全局凭证或完整计划。

策略 step 必须接受 observation 和 prev_state 这两个关键字参数；宿主不是按自定义参数名传递。

钩子只检查，不构造、不联网、不写文件、不修改全局状态，也不得把秘密拼进诊断文本。
显式 schema 注册的钩子接收参数映射；直接使用 ComponentDefinition 时同样接收映射。
纯钩子不能代替工厂和运行时的类型、资源与行为检查。

## 审计查询

```shell
python -m stegopot events outputs/<run-id> --scope public --limit 20
python -m stegopot events outputs/<run-id> --scope research --trial <trial-id> --node sender
python -m stegopot events outputs/<run-id> --scope research --call <call-id>
python -m stegopot events outputs/<run-id> --scope research --trial <trial-id> --message <message-id>
```

默认核验报告、日志与关联封印，只查询封印报告声明的试验，不混入后来添加的无关子目录。
CLI 支持 --round、--span、--kind、--limit；limit 默认 100，范围 1 到 10000。
--expected-seal-sha256 接受独立保存的根哈希，不能和 --unverified 同时使用。

```python
from stegopot.infrastructure.recorders.audit.reader import AuditReader

reader = AuditReader("D:/Research/my-workspace/outputs/your-run-id")
for record in reader.events(scope="research", node_id="sender", kind="llm.response"):
    event = record["event"]
    print(event["trace"], event["data"]["call_id"])
```

Python 参数对应 trial_id、node_id、round_index、message_id、call_id、span_id、kind。
返回原始日志信封的独立字典，包含 event；不重组另一套研究事实。
先读取根日志，再按报告顺序读取试验日志，不承诺跨文件全局时间排序。

研究日志 trace 使用 stegopot.trace/1：

| 字段 | 含义 |
| --- | --- |
| run_id / trial_id | 实验与试验身份 |
| span_id / parent_span_id | 当前调用区段及父区段 |
| span_name | node.decision、llm.call、codec.encode、channel.transform 等操作 |
| node_id / round_index | 当前节点和轮次，无对应作用域时为空 |
| message_id | 当前处理的实际消息，无消息作用域时为空 |

data.call_id 连接一次实际请求、响应和失败。
观察事件的 input_message_ids 表明决策读到的消息，消息查询也匹配该字段。
路由和信道事件通过消息 ID、父 span 追溯决策和干预。
span 筛选仅精确匹配当前 span_id，不自动递归所有后代。
message_id 不是跨试验全局 ID，建议同时指定 trial_id。

公开视图继续遵守白名单，不增加内部 trace、调用内容或私有观察。
public 下按 call/span 筛选通常无结果，不可为方便查询拼接 research。
research 可能包含秘密、提示和预共享材料，仅供授权研究人员使用。

中断目录可显式使用 AuditReader(..., verify=False) 或 --unverified 调查。
这不构成完整性验证；损坏 JSON 行仍报错，不自动修复或伪造。
verified 仅说明初始化时的核验，不锁定文件，也不能防止之后被其他进程修改。

## 环境记录与测试

manifest 新增预检提示及 Python、平台、已安装分发包版本，
不复制进程环境变量、密钥或安装路径。
它不是完整模型权重哈希与随机状态快照，不保证远程采样或跨硬件逐位确定性。

```shell
python -m unittest discover -s tests/contracts -q
```

上述命令仅适用于本地具备 tests/contracts 的开发环境；测试目录由 Git 忽略，公开仓库不分发测试文件。
本地契约测试覆盖分层依赖、注册与预检、预算与取消、拓扑及重放兼容、类型失败、
资源关闭、审计因果关联和公开隔离，使用临时工作区和替身模型/codec，拒绝网络连接。
不验证付费 API 账户，也不替代真实 StegoKit 模型/算法的集成验收。

本版本不包含断点恢复、分布式调度、硬中断、隐藏重试、自动工具规划或论文结论。
后续扩展仍通过 domain/interface 注册和调用，不得绕开审计和所有权约定。
