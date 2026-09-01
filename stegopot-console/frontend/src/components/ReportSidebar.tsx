import { useMemo, useRef, useState } from "react";
import {
  Database,
  FileJson,
  Search,
  Upload,
} from "lucide-react";
import type { ReportSummary } from "../types/contracts";
import { formatDate, formatPercent } from "../lib/format";

interface ReportSidebarProps {
  reports: ReportSummary[];
  selectedId: string | null;
  connected: boolean;
  loading: boolean;
  importing: boolean;
  onSelect: (reportId: string) => void;
  onImport: (file: File) => Promise<void>;
}

/** 报告检索、选择和导入所在的独立导航区。 */
export function ReportSidebar({
  reports,
  selectedId,
  connected,
  loading,
  importing,
  onSelect,
  onImport,
}: ReportSidebarProps) {
  const [query, setQuery] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);
  const visibleReports = useMemo(() => {
    const normalized = query.trim().toLocaleLowerCase();
    if (!normalized) return reports;
    return reports.filter((report) =>
      [report.title, report.id, ...report.tags]
        .join(" ")
        .toLocaleLowerCase()
        .includes(normalized),
    );
  }, [query, reports]);

  const handleFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) await onImport(file);
  };

  return (
    <aside className="sidebar">
      <div className="brand-block">
        <span className="brand-mark" aria-hidden="true">
          <img src="/stegopot-icon.png" alt="" />
        </span>
        <div>
          <strong>StegoPot</strong>
          <span>Experiment Console</span>
        </div>
      </div>

      <button
        className="import-button"
        type="button"
        onClick={() => fileInput.current?.click()}
        disabled={importing}
      >
        <Upload size={16} />
        {importing ? "正在导入" : "导入实验报告"}
      </button>
      <input
        ref={fileInput}
        type="file"
        accept="application/json,.json"
        className="visually-hidden"
        onChange={handleFileChange}
      />

      <label className="search-field">
        <Search size={15} aria-hidden="true" />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索报告"
          aria-label="搜索报告"
        />
      </label>

      <div className="sidebar-section-heading">
        <span>实验记录</span>
        <span>{reports.length}</span>
      </div>

      <nav className="report-list" aria-label="实验报告列表">
        {loading && reports.length === 0 ? (
          <div className="sidebar-status">正在读取报告</div>
        ) : visibleReports.length === 0 ? (
          <div className="sidebar-empty">
            <FileJson size={20} />
            <span>暂无实验报告</span>
          </div>
        ) : (
          visibleReports.map((report) => (
            <button
              type="button"
              key={report.id}
              className={`report-item ${selectedId === report.id ? "is-active" : ""}`}
              onClick={() => onSelect(report.id)}
            >
              <span className="report-item-title">{report.title}</span>
              <span className="report-item-meta">
                {formatDate(report.created_at)}
                <span aria-hidden="true">·</span>
                {report.message_count} 条消息
              </span>
              <span className="report-item-score">
                F1 {formatPercent(report.f1)}
              </span>
            </button>
          ))
        )}
      </nav>

      <div className="connection-state">
        <Database size={14} />
        <span className={connected ? "status-dot is-online" : "status-dot"} />
        <span>{connected ? "报告服务在线" : "报告服务离线"}</span>
      </div>
    </aside>
  );
}
