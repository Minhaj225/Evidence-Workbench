import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, upload, useDocuments } from "../api";
import UploadPanel from "../components/UploadPanel";
import DocumentList from "../components/DocumentList";

export default function DocumentsPage() {
  const documents = useDocuments(),
    client = useQueryClient();
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [demo, setDemo] = useState(false);
  async function uploadFiles(files: File[]) {
    setBusy(true);
    setError("");
    try {
      for (const file of files) await upload(file, true);
      await client.invalidateQueries({ queryKey: ["documents"] });
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function loadDemo() {
    setBusy(true);
    setError("");
    try {
      await api("/demo", { method: "POST" });
      await client.invalidateQueries({ queryKey: ["documents"] });
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function remove(id: string) {
    if (
      !window.confirm(
        "Delete this document, both retrieval indexes, and its cached pages?",
      )
    )
      return;
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      await client.invalidateQueries({ queryKey: ["documents"] });
    } catch (error) {
      setError((error as Error).message);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR KNOWLEDGE BASE</p>
          <h1>Documents</h1>
          <p>
            Bring your sources together. Ask questions grounded in what they
            say.
          </p>
        </div>
        <button className="secondary" onClick={() => setDemo(!demo)}>
          Demo corpus setup
        </button>
      </div>
      {demo && (
        <div className="notice">
          <strong>Load the pinned NIST corpus</strong>
          <button disabled={busy} onClick={() => void loadDemo()}>
            Load demo corpus
          </button>
          <p>
            Run <code>make corpus</code>, then <code>make ingest-demo</code> on
            the server. These use the same upload pipeline and verify both
            publication checksums.
          </p>
        </div>
      )}
      {error && (
        <div className="notice error" role="alert">
          {error}
        </div>
      )}
      <UploadPanel onUpload={uploadFiles} busy={busy} />
      <div className="section-heading">
        <h2>
          Document library{" "}
          <span className="count">{documents.data?.length || 0}</span>
        </h2>
        <span>Ready documents are available to both strategies.</span>
      </div>
      {documents.isPending ? (
        <p role="status">Loading your library…</p>
      ) : documents.error ? (
        <p role="alert">{documents.error.message}</p>
      ) : documents.data?.length ? (
        <DocumentList records={documents.data} onDelete={remove} />
      ) : (
        <div className="empty">
          <h3>Your library is ready for its first document</h3>
          <p>
            Upload a source above. Processing status and chunk counts will
            appear here.
          </p>
        </div>
      )}
    </>
  );
}
