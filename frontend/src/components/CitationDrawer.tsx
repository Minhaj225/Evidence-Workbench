import { useEffect, useRef } from "react";
import type { Citation, DocumentRecord } from "../types";

export default function CitationDrawer({
  citation,
  citations,
  documents,
  onSelect,
  onClose,
}: {
  citation: Citation;
  citations: Citation[];
  documents: DocumentRecord[];
  onSelect: (citation: Citation) => void;
  onClose: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.showModal();
    return () => {
      previous?.focus();
    };
  }, []);
  const index = citations.findIndex((c) => c.source_id === citation.source_id);
  const pdf =
    documents.find((d) => d.document.id === citation.document_id)?.document
      .media_type === "application/pdf";
  return (
    <dialog
      ref={dialog}
      className="citation-drawer"
      aria-labelledby="source-title"
      onKeyDown={(event) => {
        if (event.key !== "Tab") return;
        const controls = Array.from(
          event.currentTarget.querySelectorAll<HTMLButtonElement>(
            "button:not(:disabled)",
          ),
        );
        const first = controls[0],
          last = controls[controls.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <div className="drawer-top">
        <span className="eyebrow">SOURCE {citation.source_id}</span>
        <button className="quiet" onClick={onClose} aria-label="Close source">
          Close ×
        </button>
      </div>
      <h2 id="source-title">{citation.document_title}</h2>
      <p>
        Page {citation.page_start}
        {citation.page_end !== citation.page_start && `–${citation.page_end}`}
      </p>
      {!!citation.heading_path.length && (
        <p>{citation.heading_path.join(" / ")}</p>
      )}
      <blockquote>{citation.excerpt}</blockquote>
      <dl className="timings">
        <div>
          <dt>Dense score</dt>
          <dd>{citation.dense_score.toFixed(4)}</dd>
        </div>
        {citation.reranker_score !== null && (
          <div>
            <dt>Reranker score</dt>
            <dd>{citation.reranker_score.toFixed(4)}</dd>
          </div>
        )}
      </dl>
      <small>Scores are ranking signals, not probabilities.</small>
      {pdf ? (
        <img
          className="page-preview"
          src={`/api/documents/${citation.document_id}/pages/${citation.page_start}`}
          alt={`Page ${citation.page_start} of ${citation.document_title}`}
        />
      ) : (
        <p className="notice">
          Plain-text source. No rendered page is available.
        </p>
      )}
      <div className="drawer-navigation">
        <button
          className="secondary"
          disabled={index <= 0}
          onClick={() => onSelect(citations[index - 1])}
        >
          Previous source
        </button>
        <button
          className="secondary"
          disabled={index === citations.length - 1}
          onClick={() => onSelect(citations[index + 1])}
        >
          Next source
        </button>
      </div>
    </dialog>
  );
}
