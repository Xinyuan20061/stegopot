/** 将 0 到 1 的比例格式化为百分数。 */
export function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** 将毫秒值压缩为适合操作界面的文本。 */
export function formatDuration(milliseconds: number): string {
  if (milliseconds < 1) {
    return `${milliseconds.toFixed(2)} ms`;
  }
  if (milliseconds < 1000) {
    return `${milliseconds.toFixed(1)} ms`;
  }
  return `${(milliseconds / 1000).toFixed(2)} s`;
}

/** 将 ISO 时间格式化为本地短日期。 */
export function formatDate(value: string): string {
  if (!value) return "时间未知";
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

/** 将内部终止原因映射为界面文字。 */
export function formatTermination(reason: string): string {
  const labels: Record<string, string> = {
    max_rounds: "达到轮次上限",
    any_final_answer: "节点提交最终答案",
    all_final_answers: "全部节点已完成",
    substrate_done: "环境主动结束",
  };
  return labels[reason] ?? reason;
}

/** 将策略动作类型映射为界面文字。 */
export function formatAction(kind: string): string {
  const labels: Record<string, string> = {
    message: "发送消息",
    broadcast: "广播消息",
    wait: "等待",
    final_answer: "完成",
  };
  return labels[kind] ?? kind;
}
