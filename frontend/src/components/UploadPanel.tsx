import { useRef, useState } from "react";

export function validateFile(file: File): string | null {
  if (!/\.(pdf|txt)$/i.test(file.name))
    return "Choose a PDF or UTF-8 text file.";
  if (file.size > 20 * 1024 * 1024)
    return "Each file must be 20 MiB or smaller.";
  if (!file.size) return "Empty files cannot be uploaded.";
  return null;
}
export default function UploadPanel({
  onUpload,
  busy,
}: {
  onUpload: (files: File[]) => Promise<void>;
  busy: boolean;
}) {
  const [error, setError] = useState("");
  const input = useRef<HTMLInputElement>(null);
  async function submit(files: File[]) {
    const invalid = files.map(validateFile).find(Boolean);
    if (invalid) {
      setError(invalid);
      return;
    }
    setError("");
    await onUpload(files);
  }
  return (
    <section
      className="upload-zone"
      aria-label="Upload documents"
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        if (!busy) void submit(Array.from(event.dataTransfer.files));
      }}
    >
      <span className="upload-mark" aria-hidden="true">
        ↑
      </span>
      <h2>Add your source material</h2>
      <p>Drop documents here, or choose files to get started.</p>
      <input
        ref={input}
        type="file"
        accept=".pdf,.txt"
        multiple
        aria-label="Choose documents"
        disabled={busy}
        onChange={(event) => {
          void submit(Array.from(event.target.files || []));
          event.target.value = "";
        }}
      />
      <small>
        PDF and UTF-8 text · up to 20 MiB each · text-bearing PDFs only
      </small>
      {error && (
        <p role="alert" className="error-text">
          {error}
        </p>
      )}
    </section>
  );
}
