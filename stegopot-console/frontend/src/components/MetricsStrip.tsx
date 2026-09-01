import { Binary, ScanSearch, Target, Timer } from "lucide-react";
import type { ExperimentView } from "../types/contracts";
import { formatDuration, formatPercent } from "../lib/format";

interface MetricsStripProps {
  metrics: ExperimentView["metrics"];
}

interface MetricItemProps {
  label: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
  tone?: "default" | "warning";
}

/** 单个稳定尺寸的指标单元。 */
function MetricItem({ label, value, detail, icon, tone = "default" }: MetricItemProps) {
  return (
    <div className={`metric-item tone-${tone}`}>
      <div className="metric-icon" aria-hidden="true">{icon}</div>
      <div className="metric-copy">
        <span>{label}</span>
        <strong>{value}</strong>
        <small>{detail}</small>
      </div>
    </div>
  );
}

/** 实验详情顶部的核心指标带。 */
export function MetricsStrip({ metrics }: MetricsStripProps) {
  const detection = metrics.detection;
  const stego = metrics.steganography;
  return (
    <section className="metrics-strip" aria-label="核心实验指标">
      <MetricItem
        label="检测 F1"
        value={formatPercent(detection.f1)}
        detail={`准确率 ${formatPercent(detection.accuracy)}`}
        icon={<Target size={18} />}
      />
      <MetricItem
        label="召回率"
        value={formatPercent(detection.recall)}
        detail={`漏报率 ${formatPercent(detection.false_negative_rate)}`}
        icon={<ScanSearch size={18} />}
        tone={detection.false_negative_rate > 0 ? "warning" : "default"}
      />
      <MetricItem
        label="比特恢复"
        value={formatPercent(stego.bit_recovery_accuracy)}
        detail={`${stego.recovered_bit_count} / ${stego.requested_bit_count} bit`}
        icon={<Binary size={18} />}
      />
      <MetricItem
        label="平均检测耗时"
        value={formatDuration(detection.average_detection_ms)}
        detail={`${detection.inspected_messages} 条已检查`}
        icon={<Timer size={18} />}
      />
    </section>
  );
}
