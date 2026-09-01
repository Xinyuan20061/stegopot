import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  Check,
  CircleAlert,
  Hash,
  RefreshCw,
  Route,
  X,
} from "lucide-react";
import {
  getHealth,
  getReport,
  importReport,
  listReports,
} from "./api/client";
import { MessageWorkspace } from "./components/MessageWorkspace";
import { MetricsStrip } from "./components/MetricsStrip";
import { ReportSidebar } from "./components/ReportSidebar";
import { TopologyPanel } from "./components/TopologyPanel";
import {
  formatDate,
  formatPercent,
  formatTermination,
} from "./lib/format";
import type {
  ExperimentView,
  ReportSummary,
  ViewScope,
} from "./types/contracts";

/** StegoPot 实验报告工作台。 */
export default function App() {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [report, setReport] = useState<ExperimentView | null>(null);
  const [scope, setScope] = useState<ViewScope>("public");
  const [selectedMessageId, setSelectedMessageId] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingReport, setLoadingReport] = useState(false);
  const [importing, setImporting] = useState(false);
  const [reloadToken, setReloadToken] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const refreshReports = useCallback(async (preferredId?: string) => {
    setLoadingList(true);
    try {
      const response = await listReports();
      setReports(response.reports);
      setConnected(true);
      setSelectedId((current) => {
        const preferred = preferredId ?? current;
        if (preferred && response.reports.some((item) => item.id === preferred)) {
          return preferred;
        }
        return response.reports[0]?.id ?? null;
      });
    } catch (cause) {
      setConnected(false);
      setError(cause instanceof Error ? cause.message : "报告列表读取失败");
    } finally {
      setLoadingList(false);
    }
  }, []);

  useEffect(() => {
    void getHealth()
      .then(() => setConnected(true))
      .catch(() => setConnected(false));
    void refreshReports();
  }, [refreshReports]);

  useEffect(() => {
    if (!selectedId) {
      setReport(null);
      setSelectedMessageId(null);
      return;
    }
    let active = true;
    setLoadingReport(true);
    void getReport(selectedId, scope)
      .then((nextReport) => {
        if (!active) return;
        setReport(nextReport);
        setSelectedMessageId((current) =>
          current && nextReport.messages.some((message) => message.id === current)
            ? current
            : nextReport.messages[0]?.id ?? null,
        );
        setConnected(true);
      })
      .catch((cause) => {
        if (!active) return;
        setError(cause instanceof Error ? cause.message : "实验报告读取失败");
      })
      .finally(() => {
        if (active) setLoadingReport(false);
      });
    return () => {
      active = false;
    };
  }, [reloadToken, scope, selectedId]);

  const selectedMessage = useMemo(
    () => report?.messages.find((message) => message.id === selectedMessageId),
    [report, selectedMessageId],
  );

  const handleImport = async (file: File) => {
    setImporting(true);
    setError(null);
    try {
      const response = await importReport(file);
      setScope("public");
      await refreshReports(response.id);
      setReloadToken((value) => value + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "实验报告导入失败");
    } finally {
      setImporting(false);
    }
  };

  const handleRefresh = async () => {
    setError(null);
    await refreshReports(selectedId ?? undefined);
    setReloadToken((value) => value + 1);
  };

  return (
    <div className="app-shell">
      <ReportSidebar
        reports={reports}
        selectedId={selectedId}
        connected={connected}
        loading={loadingList}
        importing={importing}
        onSelect={setSelectedId}
        onImport={handleImport}
      />

      <main className="main-area">
        {error && (
          <div className="error-banner" role="alert">
            <CircleAlert size={17} />
            <span>{error}</span>
            <button type="button" onClick={() => setError(null)} title="关闭错误提示">
              <X size={16} />
            </button>
          </div>
        )}

        {!report && !loadingReport ? (
          <EmptyWorkspace connected={connected} />
        ) : report ? (
          <>
            <header className="topbar">
              <div className="report-heading">
                <div className="heading-line">
                  <h1>{report.run.title}</h1>
                  <span className="run-status"><Check size={13} />已完成</span>
                </div>
                <div className="report-subline">
                  <span>{report.run.id}</span>
                  <span aria-hidden="true">·</span>
                  <span>{formatDate(report.run.created_at)}</span>
                  {report.run.tags.map((tag) => (
                    <span className="tag" key={tag}>{tag}</span>
                  ))}
                </div>
              </div>
              <div className="topbar-actions">
                <div className="scope-control" aria-label="数据视图">
                  <button
                    type="button"
                    className={scope === "public" ? "is-active" : ""}
                    onClick={() => setScope("public")}
                  >
                    公开视图
                  </button>
                  <button
                    type="button"
                    className={scope === "research" ? "is-active" : ""}
                    onClick={() => setScope("research")}
                  >
                    研究视图
                  </button>
                </div>
                <button
                  className="icon-button"
                  type="button"
                  onClick={handleRefresh}
                  title="刷新报告"
                  aria-label="刷新报告"
                >
                  <RefreshCw size={17} className={loadingReport ? "is-spinning" : ""} />
                </button>
              </div>
            </header>

            <div className="content-area">
              <MetricsStrip metrics={report.metrics} />
              <div className="overview-grid">
                <TopologyPanel
                  topology={report.topology}
                  selectedMessage={selectedMessage}
                />
                <RunFacts report={report} />
              </div>
              <MessageWorkspace
                report={report}
                selectedMessageId={selectedMessageId}
                onSelectMessage={setSelectedMessageId}
              />
            </div>
          </>
        ) : (
          <LoadingWorkspace />
        )}
      </main>
    </div>
  );
}

/** 显示实验运行的稳定摘要字段。 */
function RunFacts({ report }: { report: ExperimentView }) {
  const stego = report.metrics.steganography;
  return (
    <section className="panel run-facts">
      <div className="panel-heading">
        <div>
          <span className="section-kicker">RUN</span>
          <h2>运行摘要</h2>
        </div>
      </div>
      <p className="run-task">{report.run.task}</p>
      <dl className="fact-list">
        <div>
          <dt><Route size={14} />终止条件</dt>
          <dd>{formatTermination(report.run.termination_reason)}</dd>
        </div>
        <div>
          <dt><Hash size={14} />随机种子</dt>
          <dd>{report.run.seed}</dd>
        </div>
        <div>
          <dt><CalendarClock size={14} />完成轮次</dt>
          <dd>{report.run.completed_rounds}</dd>
        </div>
      </dl>
      <div className="capacity-block">
        <div>
          <span>嵌入覆盖率</span>
          <strong>{formatPercent(stego.embedding_coverage)}</strong>
        </div>
        <div className="capacity-track" aria-hidden="true">
          <span style={{ width: `${Math.max(0, Math.min(1, stego.embedding_coverage)) * 100}%` }} />
        </div>
        <small>{stego.encoded_messages} 次编码 · {stego.decoded_messages} 次解码</small>
      </div>
    </section>
  );
}

/** 报告目录为空或服务离线时显示工作台空状态。 */
function EmptyWorkspace({ connected }: { connected: boolean }) {
  return (
    <div className="workspace-state">
      <div className="state-mark"><Route size={24} /></div>
      <h1>{connected ? "暂无实验报告" : "报告服务不可用"}</h1>
      <p>{connected ? "导入一份 StegoPot JSON 报告后即可查看。" : "后端连接恢复后将自动显示实验记录。"}</p>
    </div>
  );
}

/** 报告切换期间保持稳定布局的加载状态。 */
function LoadingWorkspace() {
  return (
    <div className="loading-workspace" aria-label="正在加载实验报告">
      <div className="loading-heading" />
      <div className="loading-metrics">
        {Array.from({ length: 4 }, (_, index) => <span key={index} />)}
      </div>
      <div className="loading-panel" />
    </div>
  );
}
