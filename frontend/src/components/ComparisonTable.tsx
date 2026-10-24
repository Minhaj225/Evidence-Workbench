import type { Report } from "../types";

export const labels: Record<string, string> = {
  hit_rate_at_5: "HitRate@5",
  precision_at_5: "Precision@5",
  recall_at_5: "Recall@5",
  mrr_at_5: "MRR@5",
  faithfulness: "Faithfulness",
  context_precision: "Context precision",
  context_recall: "Context recall",
  citation_validity: "Citation ID validity",
  citation_coverage: "Citation coverage",
};
export default function ComparisonTable({ report }: { report: Report }) {
  const format = (value: number | null) =>
    value == null ? "Unavailable" : (value * 100).toFixed(2) + "%";
  return (
    <div className="table-scroll">
      <table>
        <caption>
          Quality comparison. Higher is better for every metric below.
        </caption>
        <thead>
          <tr>
            <th>Metric</th>
            <th>Baseline</th>
            <th>Enhanced</th>
            <th>Change (pp)</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(labels).map(([key, name]) => (
            <tr key={key}>
              <th>{name}</th>
              <td>{format(report.strategies.baseline.metrics[key])}</td>
              <td>{format(report.strategies.enhanced.metrics[key])}</td>
              <td>
                {report.deltas[key] == null
                  ? "Unavailable"
                  : `${report.deltas[key]! >= 0 ? "+" : ""}${(report.deltas[key]! * 100).toFixed(2)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
