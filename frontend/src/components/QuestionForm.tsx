import type { FormEvent } from "react";

export default function QuestionForm({
  question,
  setQuestion,
  strategy,
  setStrategy,
  available,
  pending,
  onSubmit,
}: {
  question: string;
  setQuestion: (value: string) => void;
  strategy: string;
  setStrategy: (value: string) => void;
  available: boolean;
  pending: boolean;
  onSubmit: () => void;
}) {
  function submit(event: FormEvent) {
    event.preventDefault();
    onSubmit();
  }
  const valid = question.trim().length >= 3 && /[\p{L}\p{N}]/u.test(question);
  return (
    <form onSubmit={submit} className="question-form">
      <label htmlFor="question">What would you like to know?</label>
      <textarea
        id="question"
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        maxLength={2000}
        rows={4}
        placeholder="Ask a specific question about your documents…"
      />
      <div className="form-footer">
        <label>
          Retrieval strategy
          <select
            value={strategy}
            onChange={(event) => setStrategy(event.target.value)}
          >
            <option value="enhanced">Enhanced · semantic + reranking</option>
            <option value="baseline">Baseline · dense comparison</option>
          </select>
        </label>
        <span className="character-count">{question.length} / 2,000</span>
        <button disabled={!available || !valid || pending}>
          {pending ? "Finding evidence…" : "Ask question"}
        </button>
      </div>
    </form>
  );
}
