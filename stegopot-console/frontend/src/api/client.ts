import type {
  ExperimentView,
  HealthResponse,
  ImportResponse,
  ReportListResponse,
  ViewScope,
} from "../types/contracts";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

/** 后端返回非成功状态时抛出的结构化错误。 */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** 执行 JSON 请求并统一处理错误响应。 */
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | { detail?: string }
      | null;
    throw new ApiError(payload?.detail ?? "请求未成功完成", response.status);
  }
  return (await response.json()) as T;
}

/** 读取 API 健康状态。 */
export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>("/api/health");
}

/** 读取全部报告摘要。 */
export function listReports(): Promise<ReportListResponse> {
  return request<ReportListResponse>("/api/reports");
}

/** 按报告 ID 和数据范围读取实验详情。 */
export function getReport(
  reportId: string,
  scope: ViewScope,
): Promise<ExperimentView> {
  const query = new URLSearchParams({ scope });
  return request<ExperimentView>(
    `/api/reports/${encodeURIComponent(reportId)}?${query}`,
  );
}

/** 将用户选择的完整 JSON 报告导入后端仓储。 */
export async function importReport(file: File): Promise<ImportResponse> {
  const document = JSON.parse(await file.text()) as unknown;
  return request<ImportResponse>("/api/reports", {
    method: "POST",
    body: JSON.stringify(document),
  });
}
