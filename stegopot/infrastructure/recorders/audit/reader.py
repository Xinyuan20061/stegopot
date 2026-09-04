"""只读审计查询；默认先验证关联封印，再逐条读取选定视图。"""

from collections.abc import Iterator, Mapping
import json
from pathlib import Path
from typing import Any, Literal

from stegopot.infrastructure.recorders.audit.integrity import verify_experiment


class AuditReader:
  """查询一次运行；research 含私有材料，公开查询不会拼接研究字段。"""

  def __init__(
      self, directory: str | Path, *, verify: bool = True,
      expected_seal_sha256: str | None = None,
  ) -> None:
    """初始化只读查询。

    参数：
      directory: 实验结果根目录，不跟随越出该目录的日志链接。
      verify: 默认验证完整实验；调查中断目录时可显式 False，结果不代表已核验。
      expected_seal_sha256: 独立保存的根封印哈希；仅在 verify=True 时允许。
    """
    if expected_seal_sha256 is not None and not verify:
      raise ValueError("提供外部封印哈希时不能关闭验证")
    self.directory = Path(directory).resolve()
    if not self.directory.is_dir():
      raise ValueError("审计目录不存在")
    if verify:
      verify_experiment(self.directory, expected_seal_sha256=expected_seal_sha256)
      report = json.loads((self.directory / "experiment-report.json").read_text(encoding="utf-8"))
      self._trials = tuple(item["artifact_dir"] for item in report["trials"])
    else:
      self._trials = None
    self.verified = verify

  def events(
      self, *, scope: Literal["public", "research"] = "public",
      trial_id: str | None = None, node_id: str | None = None,
      round_index: int | None = None, message_id: str | None = None,
      call_id: str | None = None, span_id: str | None = None, kind: str | None = None,
  ) -> Iterator[dict[str, Any]]:
    """流式查询选定视图；先根日志，再按封印报告顺序读取，未核验时按目录名读取。

    参数：
      scope: public 默认只读公开白名单；research 须由调用者明确选择。
      trial_id: 试验 ID；兼容旧日志时使用子目录名称。
      node_id: 关联节点，消息事件也匹配公开发送者或接收者。
      round_index: 轮次，从 0 开始；None 不筛选。
      message_id: 实际消息 ID。
      call_id: 模型或工具的请求 ID，仅研究日志可用。
      span_id: 当前调用 ID，仅研究日志可用。
      kind: 精确事件类型；None 不筛选。

    返回：
      原始日志行的独立字典。verified 仅描述初始化时的核验，不能防止之后文件被外部改写。
    """
    if scope not in {"public", "research"}:
      raise ValueError("审计视图只能是 public 或 research")
    if round_index is not None and (type(round_index) is not int or round_index < 0):
      raise ValueError("轮次必须为非负整数")
    children = ([self.directory / name / f"{scope}.jsonl" for name in self._trials]
                if self._trials is not None else sorted(self.directory.glob(f"*/{scope}.jsonl")))
    paths = [self.directory / f"{scope}.jsonl", *children]
    for path in paths:
      if not path.is_file():
        continue
      if not path.resolve().is_relative_to(self.directory):
        raise ValueError("日志路径越出运行目录")
      owner = None if path.parent == self.directory else path.parent.name
      if trial_id is not None and trial_id != owner:
        continue
      with path.open(encoding="utf-8") as stream:
        for line in stream:
          record = json.loads(line)
          if not isinstance(record, dict) or not isinstance(record.get("event"), Mapping):
            raise ValueError("审计事件结构无效")
          event = record["event"]
          data = event.get("data", {})
          trace = event.get("trace", {})
          data = data if isinstance(data, Mapping) else {}
          trace = trace if isinstance(trace, Mapping) else {}
          message = data.get("message")
          message = message if isinstance(message, Mapping) else {}
          identity = trace.get("message_id") or message.get("message_id")
          actors = (event.get("actor"), trace.get("node_id"), message.get("sender"), message.get("recipient"))
          if node_id is not None and node_id not in actors:
            continue
          if round_index is not None and event.get("round_index") != round_index:
            continue
          inputs = data.get("input_message_ids", [])
          inputs = inputs if isinstance(inputs, list) else []
          if message_id is not None and message_id != identity and message_id not in inputs:
            continue
          if any(expected is not None and expected != actual for expected, actual in (
              (call_id, data.get("call_id")),
              (span_id, trace.get("span_id")), (kind, event.get("kind")))):
            continue
          yield record
