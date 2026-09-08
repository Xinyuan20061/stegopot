"""标准研究报告的人类可读视图；不依赖具体实验或业务对象。"""

from collections.abc import Mapping
import json


def render_report(report: Mapping) -> str:
  """将 report 标准映射渲染为研究专用 Markdown，不声称这是公开脱敏报告。"""
  lines = ["# StegoPot 实验报告", "", "> 研究专用：可能包含合成秘密、模型输出与私有条件。", "",
           f"运行编号：{report['run_id']}", f"状态：{report['status']}", "",
           "## 执行控制", "", "    " + json.dumps(report.get("execution", {}), ensure_ascii=False), "",
           "## 汇总", "", "    " + json.dumps(report["summary"], ensure_ascii=False), "",
           "## 逐次试验", ""]
  for record in report["trials"]:
    lines.extend([f"### {record['trial']['trial_id']}", "", f"状态：{record['status']}", ""])
    if record.get("session_id"):
      lines.extend([
          "生命周期：" + " / ".join((
              record["condition_id"],
              record["session_id"],
              record["episode_id"],
          )),
          "",
      ])
    for message in record["result"].get("messages", []):
      lines.append(f"{message['sender']} -> {message['recipient']}")
      lines.extend("    " + line for line in message["content"].splitlines())
      lines.append("")
    lines.append("    " + json.dumps(record["result"].get("final_answers", {}), ensure_ascii=False))
    if record.get("outcome_rewards"):
      lines.append("    结果奖励：" + json.dumps(record["outcome_rewards"], ensure_ascii=False))
    if record.get("feedback"):
      lines.append("    下次反馈：" + json.dumps(record["feedback"], ensure_ascii=False))
    if record.get("error") or record.get("skip_reason"):
      lines.append("    " + json.dumps(record.get("error") or record["skip_reason"], ensure_ascii=False))
    lines.append("")
  return "\n".join(lines) + "\n"
