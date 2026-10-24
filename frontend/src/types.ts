export type Document = {
  id: string;
  original_filename: string;
  media_type: string;
  byte_size: number;
  page_count: number | null;
  status: "queued" | "processing" | "ready" | "failed" | "deleting";
  error_message: string | null;
  baseline_chunk_count: number | null;
  semantic_chunk_count: number | null;
  created_at: string;
};
export type DocumentRecord = {
  document: Document;
  job: {
    stage: string;
    progress_current: number | null;
    progress_total: number | null;
  } | null;
};
export type Citation = {
  source_id: string;
  document_id: string;
  document_title: string;
  chunk_id: string;
  heading_path: string[];
  page_start: number;
  page_end: number;
  excerpt: string;
  dense_score: number;
  reranker_score: number | null;
};
export type Answer = {
  answer: string;
  insufficient_context: boolean;
  citations: Citation[];
  strategy: string;
  timings_ms: Record<string, number>;
  usage: { input_tokens: number; output_tokens: number };
};
export type Run = {
  configuration?: { fixture?: boolean };
  id: string;
  status: string;
  progress_current: number;
  progress_total: number;
  report_available: boolean;
  error_message: string | null;
  created_at: string;
};
export type Metrics = Record<string, number | null>;
export type Report = {
  id: string;
  passed: boolean;
  created_at: string;
  dataset_sha256: string;
  strategies: Record<
    string,
    {
      metrics: Metrics;
      latencies_ms: Record<string, { p50: number | null; p95: number | null }>;
    }
  >;
  deltas: Metrics;
  quality_gates: Record<string, boolean>;
  errors: Record<string, number>;
};
export type CaseResult = {
  id: string;
  question: string;
  reference_answer: string;
  corpus_group: string;
  difficulty: string;
  question_type: string;
  strategy: string;
  answer?: string;
  error_code: string | null;
  metrics: Metrics;
  evidence: { page: number; text: string; document_id: string }[];
  retrieved: {
    id: string;
    page_start: number;
    body_text: string;
    citation: Citation;
  }[];
};
