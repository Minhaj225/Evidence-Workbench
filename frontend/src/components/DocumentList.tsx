import type { DocumentRecord } from "../types";

export default function DocumentList({
  records,
  onDelete,
}: {
  records: DocumentRecord[];
  onDelete: (id: string) => void;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Document</th>
            <th>Status</th>
            <th>Pages</th>
            <th>Chunks</th>
            <th>Added</th>
            <th>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {records.map(({ document: d, job }) => (
            <tr key={d.id}>
              <td>
                <strong>{d.original_filename}</strong>
                <small>
                  {d.media_type === "application/pdf" ? "PDF" : "TEXT"} ·{" "}
                  {(d.byte_size / 1024).toFixed(1)} KiB
                </small>
                {d.error_message && (
                  <p className="error-text">{d.error_message}</p>
                )}
                {d.status === "failed" && (
                  <small>
                    Choose the original file above to retry processing.
                  </small>
                )}
              </td>
              <td>
                <span className={`status ${d.status}`}>{d.status}</span>
                {["processing", "queued"].includes(d.status) && (
                  <small>{job?.stage || "Waiting"}</small>
                )}
              </td>
              <td>{d.page_count ?? "—"}</td>
              <td>
                {d.baseline_chunk_count ?? "—"} /{" "}
                {d.semantic_chunk_count ?? "—"}
                <small>baseline / semantic</small>
              </td>
              <td>{new Date(d.created_at).toLocaleDateString()}</td>
              <td>
                <button
                  className="quiet danger"
                  aria-label={`Delete ${d.original_filename}`}
                  onClick={() => onDelete(d.id)}
                >
                  Delete
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
