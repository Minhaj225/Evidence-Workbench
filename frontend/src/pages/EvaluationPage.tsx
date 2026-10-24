import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "../api";
import type { CaseResult, Report, Run } from "../types";
import MetricCard from "../components/MetricCard";
import ComparisonTable, { labels } from "../components/ComparisonTable";

const errorReasons: Record<string, string> = {
  generation_rate_limited:
    "Gemini request quota exceeded. Check AI Studio limits and reduce the request rate before a new run.",
  generation_quota_exhausted:
    "Gemini daily quota exhausted. Wait for the quota reset before a new run.",
  generation_not_configured:
    "This run had no Gemini API key. Update .env, recreate the API container, and start a new run.",
  generation_authentication:
    "Gemini rejected the API credentials. Check the server configuration.",
  generation_model_unavailable:
    "The configured Gemini model is unavailable to this project.",
  generation_invalid_citations:
    "Generated citations failed validation after a repair attempt.",
  generation_invalid_schema: "Gemini returned an incomplete or invalid answer.",
  generation_timeout: "A Gemini request timed out.",
  evaluation_failed:
    "An evaluation step failed. Inspect the per-question results.",
  evaluation_judge_failed: "The judge could not complete its assessment.",
  evaluation_judge_invalid: "The judge returned an invalid assessment.",
};

export default function EvaluationPage() {
  const client = useQueryClient();
  const [selected, setSelected] = useState("");
  const [filters, setFilters] = useState({
    corpus_group: "",
    difficulty: "",
    question_type: "",
    strategy: "",
    result: "",
  });
  const runs = useQuery({
    queryKey: ["evaluations"],
    queryFn: () => api<Run[]>("/evaluations"),
    refetchInterval: (query) =>
      query.state.data?.some((r) => ["queued", "running"].includes(r.status))
        ? 2000
        : false,
  });
  const run = runs.data?.find((r) => r.id === selected) || runs.data?.[0];
  const report = useQuery({
    queryKey: ["report", run?.id, run?.report_available],
    queryFn: () => api<Report>(`/evaluations/${run!.id}/report`),
    enabled: !!run?.report_available,
  });
  const cases = useQuery({
    queryKey: ["cases", run?.id],
    queryFn: async () => {
      const response = await fetch(
        `/api/evaluations/${run!.id}/report?format=cases`,
      );
      if (!response.ok) throw new Error("Case details could not be loaded.");
      return (await response.text())
        .trim()
        .split("\n")
        .filter(Boolean)
        .map((line) => JSON.parse(line) as CaseResult);
    },
    enabled: !!run?.report_available,
  });
  const start = useMutation({
    mutationFn: () => api<Run>("/evaluations", { method: "POST" }),
    onSuccess: async (result) => {
      setSelected(result.id);
      await client.invalidateQueries({ queryKey: ["evaluations"] });
    },
  });
  const busy = runs.data?.some((r) => ["queued", "running"].includes(r.status));
  const quality =
    report.data &&
    Object.entries(labels)
      .slice(0, 5)
      .map(([key, name]) => ({
        name,
        Baseline: report.data!.strategies.baseline.metrics[key],
        Enhanced: report.data!.strategies.enhanced.metrics[key],
      }));
  const latency =
    report.data &&
    Object.keys(report.data.strategies.baseline.latencies_ms).map((key) => ({
      name: key.replaceAll("_", " "),
      Baseline: report.data!.strategies.baseline.latencies_ms[key].p50,
      Enhanced: report.data!.strategies.enhanced.latencies_ms[key].p50,
    }));
  const visible = cases.data?.filter((row) =>
    Object.entries(filters).every(
      ([key, value]) =>
        !value ||
        (key === "result"
          ? value === "failed"
            ? !!row.error_code || row.metrics.hit_rate_at_5 === 0
            : !row.error_code && row.metrics.hit_rate_at_5 === 1
          : row[key as keyof CaseResult] === value),
    ),
  );
  const enhanced = report.data?.strategies.enhanced;
  const enhancedCases = cases.data?.filter(
    (row) => row.strategy === "enhanced" && row.answerable,
  );
  const scored =
    enhanced?.metric_counts?.faithfulness ??
    enhancedCases?.filter((row) => row.metrics.faithfulness != null).length;
  const expected = enhanced?.cases ?? enhancedCases?.length;
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">MEASURE BEFORE YOU CLAIM</p>
          <h1>Evaluation</h1>
          <p>
            The same questions. Two retrieval strategies. Preserved results.
          </p>
        </div>
        <button
          onClick={() => start.mutate()}
          disabled={busy || start.isPending}
        >
          {busy ? "Evaluation in progress" : "Run benchmark"}
        </button>
      </div>
      <p className="method-note">
        30 answerable questions and 5 abstention cases, grounded in two
        checksum-verified NIST publications. Enhanced retrieval must gain at
        least two hits without reducing MRR.
      </p>
      {[runs.error, start.error, report.error, cases.error]
        .filter(Boolean)
        .map((error, index) => (
          <div className="notice error" role="alert" key={index}>
            {error!.message}
          </div>
        ))}
      {runs.data && runs.data.length > 0 && (
        <label className="run-picker">
          Benchmark run
          <select
            value={run?.id || ""}
            onChange={(event) => setSelected(event.target.value)}
          >
            {runs.data.map((r) => (
              <option key={r.id} value={r.id}>
                {new Date(r.created_at).toLocaleString()} · {r.status}
              </option>
            ))}
          </select>
        </label>
      )}
      {run?.configuration?.fixture && (
        <p className="notice">
          Synthetic browser fixture — these are not measured benchmark scores.
        </p>
      )}
      {run && (
        <div
          className={`notice ${run.status === "failed" ? "error" : ""}`}
          role="status"
        >
          <strong>
            {run.status === "completed"
              ? "Quality gates passed"
              : run.status === "failed"
                ? "Quality gates not passed"
                : "Running benchmark"}
          </strong>
          <p>
            {run.progress_current} / {run.progress_total} pipeline cases
            processed. {run.error_message}
          </p>
          {busy && (
            <progress
              max={run.progress_total}
              value={run.progress_current}
              aria-label="Evaluation progress"
            />
          )}
        </div>
      )}
      {report.data && (
        <>
          {Object.keys(report.data.errors).length > 0 && (
            <div className="notice error" role="alert">
              <strong>Why this run has missing scores</strong>
              <p>
                Judged metrics stay unavailable until every required case has a
                score. Earlier runs are preserved; fixes apply to new runs.
              </p>
              <ul>
                {Object.entries(report.data.errors).map(([code, count]) => (
                  <li key={code}>
                    {count} cases: {errorReasons[code] || code}
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div className="metric-grid">
            <MetricCard
              label="Baseline HitRate@5"
              value={report.data.strategies.baseline.metrics.hit_rate_at_5}
              detail="Fixed chunks · dense top five"
            />
            <MetricCard
              label="Enhanced HitRate@5"
              value={report.data.strategies.enhanced.metrics.hit_rate_at_5}
              detail="Semantic chunks · reranked top five"
            />
            <MetricCard
              label="Enhanced faithfulness"
              value={report.data.strategies.enhanced.metrics.faithfulness}
              detail={
                scored !== undefined && expected !== undefined
                  ? `LLM-judged support · ${scored} of ${expected} cases scored · target ≥ 85%`
                  : "LLM-judged support · target ≥ 85%"
              }
            />
          </div>
          <ComparisonTable report={report.data} />
          <div className="chart-grid">
            <section>
              <h2>Retrieval and answer quality</h2>
              <p>Scores from 0 to 1; missing scores are not plotted.</p>
              <div className="chart">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={quality}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" fontSize={10} />
                    <YAxis domain={[0, 1]} />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="Baseline" fill="#aeb8c8" />
                    <Bar dataKey="Enhanced" fill="#2456a6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
            <section>
              <h2>Median latency</h2>
              <p>Milliseconds; lower is better. Includes the measured host.</p>
              <div className="chart">
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={latency}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="name" fontSize={10} />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="Baseline" fill="#aeb8c8" />
                    <Bar dataKey="Enhanced" fill="#2456a6" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>
          <div className="section-heading">
            <h2>Per-question results</h2>
            <div className="downloads">
              {["json", "csv", "markdown"].map((format) => (
                <a
                  key={format}
                  href={`/api/evaluations/${run!.id}/report?format=${format}`}
                >
                  Download {format.toUpperCase()}
                </a>
              ))}
            </div>
          </div>
          <div className="filters">
            {(
              [
                "corpus_group",
                "difficulty",
                "question_type",
                "strategy",
                "result",
              ] as const
            ).map((key) => (
              <label key={key}>
                {key.replaceAll("_", " ")}
                <select
                  value={filters[key]}
                  onChange={(event) =>
                    setFilters({ ...filters, [key]: event.target.value })
                  }
                >
                  <option value="">All</option>
                  {(key === "result"
                    ? ["passed", "failed"]
                    : [
                        ...new Set(cases.data?.map((row) => String(row[key]))),
                      ].sort()
                  ).map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <div className="case-list">
            {visible?.map((row) => (
              <details key={`${row.id}-${row.strategy}`}>
                <summary>
                  <span>
                    {row.id} · {row.strategy}
                  </span>
                  <strong>{row.question}</strong>
                  <span
                    className={`status ${row.error_code ? "failed" : "ready"}`}
                  >
                    {row.error_code
                      ? "Error"
                      : row.metrics.hit_rate_at_5 === 0
                        ? "Miss"
                        : "Result"}
                  </span>
                </summary>
                <h3>Reference answer</h3>
                <p>{row.reference_answer}</p>
                <h3>Gold evidence</h3>
                {row.evidence.map((e, i) => (
                  <blockquote key={i}>
                    {e.document_id}, p. {e.page}: {e.text}
                  </blockquote>
                ))}
                <h3>Generated answer</h3>
                <p>{row.answer || row.error_code || "Unavailable"}</p>
                {row.error_code && (
                  <p className="notice error">
                    {row.error_stage && `${row.error_stage}: `}
                    {row.error_message ||
                      errorReasons[row.error_code] ||
                      row.error_code}
                  </p>
                )}
                <h3>Retrieved passages</h3>
                {row.retrieved.map((c) => (
                  <blockquote key={c.id}>
                    p. {c.page_start}: {c.body_text}
                  </blockquote>
                ))}
                <pre>{JSON.stringify(row.metrics, null, 2)}</pre>
              </details>
            ))}
          </div>
        </>
      )}
      {!run && !runs.isPending && (
        <div className="empty">
          <h2>No benchmark runs yet</h2>
          <p>
            Ingest the pinned corpus, then run the benchmark. No example scores
            are shown.
          </p>
        </div>
      )}
    </>
  );
}
