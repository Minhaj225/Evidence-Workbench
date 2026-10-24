export default function MetricCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: number | null;
  detail: string;
}) {
  return (
    <div className="metric">
      <h3>{label}</h3>
      <strong>
        {value == null ? "Unavailable" : `${(value * 100).toFixed(1)}%`}
      </strong>
      <p>{detail}</p>
    </div>
  );
}
