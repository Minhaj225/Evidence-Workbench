import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api, useDocuments } from "../api";
import type { Answer, Citation } from "../types";
import QuestionForm from "../components/QuestionForm";
import AnswerPanel from "../components/AnswerPanel";
import CitationDrawer from "../components/CitationDrawer";

export default function AskPage() {
  const documents = useDocuments();
  const ready =
    documents.data?.filter((r) => r.document.status === "ready") || [];
  const [selected, setSelected] = useState<string[]>([]),
    [question, setQuestion] = useState("");
  const [strategy, setStrategy] = useState("enhanced"),
    [citation, setCitation] = useState<Citation | null>(null);
  const answer = useMutation({
    mutationFn: () =>
      api<Answer>("/answers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, strategy, document_ids: selected }),
      }),
  });
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">FROM QUESTION TO EVIDENCE</p>
          <h1>Ask your documents</h1>
          <p>Get a concise answer, then inspect the passages behind it.</p>
        </div>
      </div>
      {documents.error && (
        <div className="notice error" role="alert">
          {documents.error.message}
        </div>
      )}
      {!ready.length && (
        <div className="notice">
          Upload a document and wait until it is ready to ask a question.
        </div>
      )}
      <details className="scope-picker">
        <summary>
          {selected.length
            ? `${selected.length} selected documents`
            : `All ready documents (${ready.length})`}
        </summary>
        <p>Leave all documents unchecked to search the entire ready library.</p>
        {ready.map(({ document: d }) => (
          <label key={d.id}>
            <input
              type="checkbox"
              checked={selected.includes(d.id)}
              onChange={(event) =>
                setSelected(
                  event.target.checked
                    ? [...selected, d.id]
                    : selected.filter((id) => id !== d.id),
                )
              }
            />
            {d.original_filename}
          </label>
        ))}
      </details>
      <QuestionForm
        question={question}
        setQuestion={setQuestion}
        strategy={strategy}
        setStrategy={setStrategy}
        available={ready.length > 0}
        pending={answer.isPending}
        onSubmit={() => {
          setCitation(null);
          answer.mutate();
        }}
      />
      <p className="privacy-note">
        Only your question and up to five retrieved passages are sent to Google Gemini.
      </p>
      {answer.error && (
        <div className="notice error" role="alert">
          {answer.error.message}
        </div>
      )}
      {answer.data && !answer.isPending && (
        <AnswerPanel answer={answer.data} onCitation={setCitation} />
      )}
      {!answer.data && !answer.isPending && (
        <div className="empty">
          <h2>An answer you can trace</h2>
          <p>
            Answers appear here with clickable source references. If your
            sources do not contain enough evidence, the answer will say so.
          </p>
        </div>
      )}
      {citation && answer.data && (
        <CitationDrawer
          citation={citation}
          citations={answer.data.citations}
          documents={documents.data || []}
          onSelect={setCitation}
          onClose={() => setCitation(null)}
        />
      )}
    </>
  );
}
