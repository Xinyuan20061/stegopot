import { useMemo, useState } from "react";
import {
  ArrowRight,
  Binary,
  CheckCircle2,
  CircleAlert,
  Clock3,
  Eye,
  ListFilter,
  MessageSquareText,
  ScanSearch,
  ShieldAlert,
} from "lucide-react";
import type {
  DetectionView,
  ExperimentView,
  MessageView,
  ResearchTraceView,
} from "../types/contracts";
import { formatAction, formatDuration, formatPercent } from "../lib/format";

type WorkspaceTab = "messages" | "detections" | "rounds";

interface MessageWorkspaceProps {
  report: ExperimentView;
  selectedMessageId: string | null;
  onSelectMessage: (messageId: string) => void;
}

/** 将检测判定显示为紧凑状态标签。 */
function DetectionBadge({ detection }: { detection?: DetectionView }) {
  if (!detection) return <span className="status-badge is-muted">未检测</span>;
  if (detection.verdict === "error") {
    return <span className="status-badge is-error">检测失败</span>;
  }
  if (detection.is_suspicious) {
    return <span className="status-badge is-warning">可疑</span>;
  }
  return <span className="status-badge is-clear">通过</span>;
}

/** 格式化研究真值中的二分类结局。 */
function outcomeLabel(outcome?: string): string {
  const labels: Record<string, string> = {
    true_positive: "正确检出",
    true_negative: "正确放行",
    false_positive: "误报",
    false_negative: "漏报",
  };
  return outcome ? labels[outcome] ?? outcome : "未分类";
}

/** 消息、检测与轮次记录的统一工作区。 */
export function MessageWorkspace({
  report,
  selectedMessageId,
  onSelectMessage,
}: MessageWorkspaceProps) {
  const [tab, setTab] = useState<WorkspaceTab>("messages");
  const traces = useMemo(
    () =>
      new Map(
        (report.research?.traces ?? []).map((trace) => [trace.message_id, trace]),
      ),
    [report.research],
  );
  const selectedMessage =
    report.messages.find((message) => message.id === selectedMessageId) ??
    report.messages[0];
  const selectedTrace = selectedMessage
    ? traces.get(selectedMessage.id)
    : undefined;

  return (
    <section className="panel workspace-panel">
      <div className="workspace-header">
        <div>
          <span className="section-kicker">TRANSCRIPT</span>
          <h2>交互记录</h2>
        </div>
        <div className="tab-list" role="tablist" aria-label="交互记录视图">
          <button
            type="button"
            role="tab"
            aria-selected={tab === "messages"}
            className={tab === "messages" ? "is-active" : ""}
            onClick={() => setTab("messages")}
          >
            <MessageSquareText size={15} />消息
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "detections"}
            className={tab === "detections" ? "is-active" : ""}
            onClick={() => setTab("detections")}
          >
            <ScanSearch size={15} />检测
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === "rounds"}
            className={tab === "rounds" ? "is-active" : ""}
            onClick={() => setTab("rounds")}
          >
            <ListFilter size={15} />轮次
          </button>
        </div>
      </div>

      <div className="workspace-grid">
        <div className="workspace-list">
          {tab === "messages" && (
            <MessageList
              messages={report.messages}
              traces={traces}
              selectedMessageId={selectedMessage?.id ?? null}
              onSelect={onSelectMessage}
            />
          )}
          {tab === "detections" && (
            <DetectionList
              detections={report.detections}
              messages={report.messages}
              selectedMessageId={selectedMessage?.id ?? null}
              onSelect={onSelectMessage}
            />
          )}
          {tab === "rounds" && <RoundList report={report} />}
        </div>
        <MessageInspector
          message={selectedMessage}
          trace={selectedTrace}
          scope={report.view_scope}
        />
      </div>
    </section>
  );
}

interface MessageListProps {
  messages: MessageView[];
  traces: Map<string, ResearchTraceView>;
  selectedMessageId: string | null;
  onSelect: (messageId: string) => void;
}

/** 按发送轮次排列公开消息。 */
function MessageList({ messages, traces, selectedMessageId, onSelect }: MessageListProps) {
  if (messages.length === 0) {
    return <div className="content-empty">本次实验没有投递消息</div>;
  }
  return (
    <div className="message-list">
      {messages.map((message) => {
        const trace = traces.get(message.id);
        return (
          <button
            type="button"
            key={message.id}
            className={`message-row ${selectedMessageId === message.id ? "is-active" : ""}`}
            onClick={() => onSelect(message.id)}
          >
            <span className="round-index">R{message.round_index + 1}</span>
            <span className="message-main">
              <span className="message-route">
                <strong>{message.sender}</strong>
                <ArrowRight size={13} />
                <strong>{message.recipient}</strong>
              </span>
              <span className="message-preview">{message.content}</span>
            </span>
            <span className="message-statuses">
              {trace?.is_stego && <span className="status-badge is-private">隐写</span>}
              <DetectionBadge detection={message.detection} />
            </span>
          </button>
        );
      })}
    </div>
  );
}

interface DetectionListProps {
  detections: DetectionView[];
  messages: MessageView[];
  selectedMessageId: string | null;
  onSelect: (messageId: string) => void;
}

/** 按消息展示检测器分数和耗时。 */
function DetectionList({
  detections,
  messages,
  selectedMessageId,
  onSelect,
}: DetectionListProps) {
  const messageMap = new Map(messages.map((message) => [message.id, message]));
  if (detections.length === 0) {
    return <div className="content-empty">本次实验没有检测记录</div>;
  }
  return (
    <div className="detection-table" role="table" aria-label="检测记录">
      <div className="detection-table-head" role="row">
        <span>消息</span><span>检测器</span><span>分数</span><span>耗时</span><span>结论</span>
      </div>
      {detections.map((detection) => {
        const message = messageMap.get(detection.message_id);
        return (
          <button
            type="button"
            role="row"
            key={detection.message_id}
            className={selectedMessageId === detection.message_id ? "is-active" : ""}
            onClick={() => onSelect(detection.message_id)}
          >
            <span>{message ? `R${message.round_index + 1}` : detection.message_id}</span>
            <span>{detection.detector_id}</span>
            <span>{detection.score == null ? "—" : detection.score.toFixed(2)}</span>
            <span>{formatDuration(detection.elapsed_ms)}</span>
            <DetectionBadge detection={detection} />
          </button>
        );
      })}
    </div>
  );
}

/** 显示每轮节点动作和环境事件数量。 */
function RoundList({ report }: { report: ExperimentView }) {
  return (
    <div className="round-list">
      {report.rounds.map((round) => (
        <article className="round-row" key={round.index}>
          <div className="round-row-head">
            <span>第 {round.index + 1} 轮</span>
            <small>{round.message_ids.length} 条消息 · {round.event_count} 个环境事件</small>
          </div>
          <div className="action-list">
            {round.actions.map((action) => (
              <div className="action-row" key={`${round.index}-${action.node_id}`}>
                <strong>{action.node_id}</strong>
                <span>{formatAction(action.kind)}</span>
                <small>{action.target ? `→ ${action.target}` : action.error ?? ""}</small>
              </div>
            ))}
          </div>
        </article>
      ))}
    </div>
  );
}

interface MessageInspectorProps {
  message?: MessageView;
  trace?: ResearchTraceView;
  scope: ExperimentView["view_scope"];
}

/** 展示当前消息的公开判定与可选研究真值。 */
function MessageInspector({ message, trace, scope }: MessageInspectorProps) {
  if (!message) {
    return <aside className="message-inspector content-empty">没有可检查的消息</aside>;
  }
  const detection = message.detection;
  return (
    <aside className="message-inspector">
      <div className="inspector-heading">
        <div>
          <span>消息详情</span>
          <strong>{message.id}</strong>
        </div>
        <DetectionBadge detection={detection} />
      </div>

      <div className="inspector-section">
        <span className="inspector-label"><Eye size={14} />公开内容</span>
        <p className="public-message">{message.content}</p>
        <div className="inline-facts">
          <span>{message.sender}</span><ArrowRight size={13} /><span>{message.recipient}</span>
          <span className="fact-separator" />
          <span>第 {message.round_index + 1} 轮</span>
        </div>
      </div>

      <div className="inspector-section">
        <span className="inspector-label"><ScanSearch size={14} />检测分析</span>
        {detection ? (
          <>
            <div className="score-line">
              <span>风险分数</span>
              <strong>{detection.score == null ? "—" : detection.score.toFixed(2)}</strong>
            </div>
            <div className="score-track" aria-hidden="true">
              <span style={{ width: `${Math.max(0, Math.min(1, detection.score ?? 0)) * 100}%` }} />
            </div>
            <p className="analysis-reason">{detection.reason}</p>
            <div className="inline-facts">
              <Clock3 size={13} />
              <span>{formatDuration(detection.elapsed_ms)}</span>
              <span className="fact-separator" />
              <span>{detection.detector_id}</span>
            </div>
          </>
        ) : (
          <p className="empty-copy">没有对应检测结果</p>
        )}
      </div>

      {scope === "research" && (
        <ResearchTrace trace={trace} />
      )}
    </aside>
  );
}

/** 研究范围内展示实际隐写和恢复数据。 */
function ResearchTrace({ trace }: { trace?: ResearchTraceView }) {
  return (
    <div className="inspector-section research-section">
      <span className="inspector-label"><Binary size={14} />研究真值</span>
      {!trace ? (
        <p className="empty-copy">没有关联的研究轨迹</p>
      ) : (
        <>
          <div className="truth-header">
            <span className={`truth-icon ${trace.is_stego ? "is-stego" : ""}`}>
              {trace.is_stego ? <ShieldAlert size={15} /> : <CheckCircle2 size={15} />}
            </span>
            <div>
              <strong>{trace.is_stego ? "真实隐写消息" : "普通公开消息"}</strong>
              <small>{outcomeLabel(trace.outcome)}</small>
            </div>
          </div>
          {trace.is_stego && (
            <>
              <div className="research-facts">
                <span><small>算法</small><strong>{trace.algorithm ?? "—"}</strong></span>
                <span><small>嵌入</small><strong>{trace.consumed_bit_count} bit</strong></span>
                <span><small>匹配</small><strong>{trace.matching_bit_count} bit</strong></span>
              </div>
              <BitBlock label="原始秘密" value={trace.secret_bits} />
              <BitBlock label="解码结果" value={trace.decoded_bits} />
              <div className="recovery-state">
                {trace.complete_recovery ? <CheckCircle2 size={15} /> : <CircleAlert size={15} />}
                <span>{trace.complete_recovery ? "完整恢复" : "未完整恢复"}</span>
                <strong>
                  {formatPercent(
                    trace.consumed_bit_count
                      ? trace.matching_bit_count / trace.consumed_bit_count
                      : 0,
                  )}
                </strong>
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

/** 使用等宽文本展示一段二进制载荷。 */
function BitBlock({ label, value }: { label: string; value?: string }) {
  return (
    <div className="bit-block">
      <span>{label}</span>
      <code>{value ?? "不可用"}</code>
    </div>
  );
}
