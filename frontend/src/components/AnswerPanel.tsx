import type { Answer, Citation } from "../types";

export default function AnswerPanel({
  answer,
  onCitation,
}: {
  answer: Answer;
  onCitation: (citation: Citation) => void;
}) {
  const parts = answer.answer.split(/(\[S\d+\])/g);
  return (
    <section className="answer-panel" aria-labelledby="answer-heading">
      <div className="section-heading">
        <h2 id="answer-heading">
          {answer.insufficient_context
            ? "Insufficient evidence"
            : "Grounded answer"}
        </h2>
        <span className="status ready">{answer.strategy}</span>
      </div>
      <div className="answer-text">
        {parts.map((part, index) => {
          const citation = answer.citations.find(
            (c) => `[${c.source_id}]` === part,
          );
          return citation ? (
            <button
              key={index}
              className="citation-marker"
              aria-label={`Open source ${citation.source_id}`}
              onClick={() => onCitation(citation)}
            >
              {citation.source_id}
            </button>
          ) : (
            <span key={index}>{part}</span>
          );
        })}
      </div>
      {!!answer.citations.length && (
        <div className="sources">
          <h3>Sources</h3>
          {answer.citations.map((c) => (
            <button
              className="source-link"
              key={c.source_id}
              onClick={() => onCitation(c)}
            >
              <span>{c.source_id}</span>
              <strong>{c.document_title}</strong>
              <small>
                p. {c.page_start}
                {c.page_end !== c.page_start && `–${c.page_end}`}
              </small>
            </button>
          ))}
        </div>
      )}
      <details>
        <summary>Timing and token usage</summary>
        <dl className="timings">
          {Object.entries(answer.timings_ms).map(([key, value]) => (
            <div key={key}>
              <dt>{key.replaceAll("_", " ")}</dt>
              <dd>{value.toFixed(1)} ms</dd>
            </div>
          ))}
          <div>
            <dt>Tokens, input / output</dt>
            <dd>
              {answer.usage.input_tokens} / {answer.usage.output_tokens}
            </dd>
          </div>
        </dl>
      </details>
    </section>
  );
}
