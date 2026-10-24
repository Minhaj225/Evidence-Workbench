import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { vi, test, expect } from "vitest";
import App from "../App";
import { api, upload } from "../api";
import { validateFile } from "../components/UploadPanel";
import QuestionForm from "../components/QuestionForm";
import AnswerPanel from "../components/AnswerPanel";
import type { Answer } from "../types";

const id = "843d70c1-6bb3-4f82-8a88-0a43204babce";
const document = {
  id,
  original_filename: "Risk framework.pdf",
  media_type: "application/pdf",
  byte_size: 2048,
  page_count: 2,
  status: "ready",
  baseline_chunk_count: 3,
  semantic_chunk_count: 4,
  created_at: "2026-10-18T10:00:00Z",
};
const citation = {
  source_id: "S1",
  document_id: id,
  document_title: document.original_filename,
  chunk_id: id,
  heading_path: ["Core functions"],
  page_start: 1,
  page_end: 2,
  excerpt: "The four functions are GOVERN, MAP, MEASURE, and MANAGE.",
  dense_score: 0.8,
  reranker_score: 3.2,
};
const answer: Answer = {
  answer: "The four functions are GOVERN, MAP, MEASURE, and MANAGE [S1].",
  insufficient_context: false,
  citations: [citation],
  strategy: "enhanced",
  timings_ms: { total: 12, embedding: 3 },
  usage: { input_tokens: 20, output_tokens: 10 },
};
const metric = {
  hit_rate_at_5: 0.5,
  precision_at_5: 0.5,
  recall_at_5: 0.5,
  mrr_at_5: 0.5,
  faithfulness: null,
  context_precision: null,
  context_recall: null,
  citation_validity: null,
  citation_coverage: null,
};
const report = {
  id,
  passed: false,
  created_at: document.created_at,
  dataset_sha256: "abc",
  strategies: {
    baseline: {
      metrics: metric,
      latencies_ms: { total: { p50: 20, p95: 30 } },
    },
    enhanced: {
      metrics: { ...metric, hit_rate_at_5: 0.6 },
      latencies_ms: { total: { p50: 40, p95: 60 } },
    },
  },
  deltas: { ...metric, hit_rate_at_5: 0.1 },
  quality_gates: {},
  errors: {},
};

function setup(
  path: string,
  handler?: (url: string, options?: RequestInit) => unknown,
) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      const custom = handler?.(url, options);
      const body =
        custom ??
        (url === "/api/health"
          ? { status: "degraded", components: { generation: "degraded" } }
          : url === "/api/documents"
            ? [{ document, job: null }]
            : url === "/api/answers"
              ? answer
              : url === "/api/evaluations"
                ? [
                    {
                      id,
                      status: "failed",
                      created_at: document.created_at,
                      progress_current: 65,
                      progress_total: 65,
                      report_available: true,
                      error_message: "A quality gate failed.",
                    },
                  ]
                : url.endsWith("format=cases")
                  ? JSON.stringify({
                      id: "q-001",
                      question: "What are the functions?",
                      reference_answer: "Four functions.",
                      corpus_group: "100",
                      difficulty: "easy",
                      question_type: "enumeration",
                      strategy: "enhanced",
                      error_code: null,
                      metrics: metric,
                      evidence: [
                        { page: 1, text: "Source evidence", document_id: id },
                      ],
                      retrieved: [
                        {
                          id,
                          page_start: 1,
                          body_text: "Source text",
                          citation,
                        },
                      ],
                    })
                  : report);
      return body instanceof Response
        ? body
        : new Response(typeof body === "string" ? body : JSON.stringify(body), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          });
    }),
  );
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("library uploads, displays errors, and deletes through the API", async () => {
  const user = userEvent.setup();
  setup("/documents");
  await screen.findByRole("button", { name: /Delete\s+Risk/ });
  expect(screen.getByText(/Answer generation needs/)).toBeInTheDocument();
  await user.click(screen.getByText("Demo corpus setup"));
  expect(screen.getByText("make corpus")).toBeInTheDocument();
  const file = new File(["source"], "source.txt", { type: "text/plain" });
  await user.upload(screen.getByLabelText("Choose documents"), file);
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(
      "/api/documents",
      expect.objectContaining({ method: "POST" }),
    ),
  );
  vi.spyOn(window, "confirm").mockReturnValue(true);
  await user.click(screen.getByRole("button", { name: /Delete\s+Risk/ }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith(`/api/documents/${id}`, {
      method: "DELETE",
    }),
  );
});

test("invalid uploads are rejected and network failures are shown", async () => {
  expect(validateFile(new File([], "a.txt"))).toContain("Empty");
  expect(validateFile(new File(["a"], "a.exe"))).toContain("PDF");
  expect(
    validateFile({ name: "a.pdf", size: 21 * 1024 * 1024 } as File),
  ).toContain("20 MiB");
  setup("/documents", (url) =>
    url === "/api/documents"
      ? new Response(
          JSON.stringify({ error: { message: "Storage is unavailable." } }),
          { status: 503 },
        )
      : undefined,
  );
  await screen.findByText("Storage is unavailable.");
  fireEvent.drop(screen.getByRole("region", { name: "Upload documents" }), {
    dataTransfer: { files: [new File(["x"], "a.exe")] },
  });
  expect(
    await screen.findByText("Choose a PDF or UTF-8 text file."),
  ).toBeInTheDocument();
});

test("question flow renders safe citations and opens the source drawer", async () => {
  const user = userEvent.setup();
  setup("/ask");
  await screen.findByText("All ready documents (1)");
  const submit = screen.getByRole("button", { name: "Ask question" });
  expect(submit).toBeDisabled();
  await user.click(screen.getByText("All ready documents (1)"));
  await user.click(screen.getByRole("checkbox"));
  await user.type(
    screen.getByLabelText("What would you like to know?"),
    "What are the functions?",
  );
  await user.click(submit);
  await screen.findByText("Grounded answer");
  const marker = screen.getByRole("button", { name: "Open source S1" });
  await user.click(marker);
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(screen.getByAltText(/Page 1 of Risk/)).toHaveAttribute(
    "src",
    `/api/documents/${id}/pages/1`,
  );
  await user.click(screen.getByRole("button", { name: "Close source" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(marker).toHaveFocus();
  await user.click(screen.getByText("Timing and token usage"));
  expect(screen.getByText("12.0 ms")).toBeInTheDocument();
});

test("insufficient evidence is explicit and raw HTML is text", () => {
  render(
    <AnswerPanel
      answer={{
        ...answer,
        answer: "<img onerror=alert(1)> Insufficient evidence.",
        insufficient_context: true,
        citations: [],
      }}
      onCitation={vi.fn()}
    />,
  );
  expect(screen.getByText("Insufficient evidence")).toBeInTheDocument();
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});

test("question controls respect availability, punctuation and pending state", () => {
  const props = {
    question: "???",
    setQuestion: vi.fn(),
    strategy: "baseline",
    setStrategy: vi.fn(),
    available: true,
    pending: false,
    onSubmit: vi.fn(),
  };
  const { rerender } = render(<QuestionForm {...props} />);
  expect(screen.getByRole("button")).toBeDisabled();
  fireEvent.change(screen.getByRole("combobox"), {
    target: { value: "enhanced" },
  });
  expect(props.setStrategy).toHaveBeenCalledWith("enhanced");
  rerender(<QuestionForm {...props} question="A valid question" pending />);
  expect(screen.getByText("Finding evidence…")).toBeDisabled();
});

test("evaluation renders actual report, filters cases and exposes downloads", async () => {
  const user = userEvent.setup();
  setup("/evaluation");
  await screen.findByText("Baseline HitRate@5");
  expect(screen.getByText("+10.00")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Download CSV" })).toHaveAttribute(
    "href",
    `/api/evaluations/${id}/report?format=csv`,
  );
  await user.click(await screen.findByText("What are the functions?"));
  expect(screen.getByText("Four functions.")).toBeInTheDocument();
  expect(screen.getByText("Source text", { exact: false })).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText("result"), "failed");
  expect(screen.queryByText("What are the functions?")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Run benchmark" }));
  await waitFor(() =>
    expect(fetch).toHaveBeenCalledWith("/api/evaluations", { method: "POST" }),
  );
});

test("empty views and errors do not show fabricated data", async () => {
  setup("/ask", (url) => (url === "/api/documents" ? [] : undefined));
  await screen.findByText("All ready documents (0)");
  expect(screen.getByRole("button", { name: "Ask question" })).toBeDisabled();
});

test("API handles empty success and safe errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(new Response("Bad", { status: 500 })),
  );
  expect(await api("/document", { method: "DELETE" })).toBeUndefined();
  await expect(upload(new File(["data"], "x.txt"))).rejects.toThrow(
    "Request failed (500).",
  );
});
