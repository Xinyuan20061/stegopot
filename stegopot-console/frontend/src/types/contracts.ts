export type ViewScope = "public" | "research";

export interface RunView {
  id: string;
  title: string;
  created_at: string;
  task: string;
  status: "completed";
  seed: number;
  tags: string[];
  completed_rounds: number;
  termination_reason: string;
  message_count: number;
  detection_count: number;
}

export interface NodeView {
  id: string;
  label: string;
  role: string;
  sent_count: number;
  received_count: number;
  reward: number;
}

export interface EdgeView {
  id: string;
  source: string;
  target: string;
}

export interface TopologyView {
  nodes: NodeView[];
  edges: EdgeView[];
}

export interface ActionView {
  node_id: string;
  kind: string;
  target?: string;
  content?: string;
  error?: string;
}

export interface RoundView {
  index: number;
  actions: ActionView[];
  message_ids: string[];
  event_count: number;
  routing_errors: string[];
}

export interface DetectionView {
  message_id: string;
  detector_id: string;
  verdict: "suspicious" | "clear" | "error";
  is_suspicious?: boolean;
  score?: number;
  confidence?: number;
  reason: string;
  elapsed_ms: number;
}

export interface MessageView {
  id: string;
  round_index: number;
  sender: string;
  recipient: string;
  content: string;
  detection?: DetectionView;
}

export interface DetectionMetricsView {
  precision: number;
  recall: number;
  f1: number;
  accuracy: number;
  false_positive_rate: number;
  false_negative_rate: number;
  inspected_messages: number;
  failed: number;
  average_detection_ms: number;
}

export interface SteganographyMetricsView {
  embedding_coverage: number;
  bit_recovery_accuracy: number;
  complete_recovery_rate: number;
  bits_per_token: number;
  encoded_messages: number;
  decoded_messages: number;
  requested_bit_count: number;
  recovered_bit_count: number;
  encode_time_ms: number;
  decode_time_ms: number;
}

export interface ResearchTraceView {
  message_id: string;
  is_stego: boolean;
  outcome?: string;
  algorithm?: string;
  secret_bits?: string;
  decoded_bits?: string;
  requested_bit_count: number;
  consumed_bit_count: number;
  matching_bit_count: number;
  complete_recovery?: boolean;
}

export interface ExperimentView {
  schema_version: "1.0";
  view_scope: ViewScope;
  run: RunView;
  topology: TopologyView;
  rounds: RoundView[];
  messages: MessageView[];
  detections: DetectionView[];
  metrics: {
    detection: DetectionMetricsView;
    steganography: SteganographyMetricsView;
  };
  final_answers: Record<string, string>;
  research?: {
    traces: ResearchTraceView[];
  };
}

export interface ReportSummary {
  id: string;
  title: string;
  created_at: string;
  tags: string[];
  completed_rounds: number;
  message_count: number;
  suspicious_count: number;
  f1: number;
  bit_recovery_accuracy: number;
}

export interface ReportListResponse {
  reports: ReportSummary[];
  total: number;
}

export interface HealthResponse {
  status: "ok";
  contract_version: "1.0";
  report_count: number;
}

export interface ImportResponse {
  id: string;
  imported: boolean;
}
