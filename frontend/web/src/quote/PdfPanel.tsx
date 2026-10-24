import { useEffect, useState } from "react";
import { api, explainError } from "@shared/api";
import type { ParamValue, PdfPreview } from "@shared/types";

interface Props {
  userId: string;
  params: Record<string, ParamValue>;
  /** Changes whenever anything that affects the PDF changes. */
  version: string;
  blocked: boolean;
  /** Called with the version that was previewed. */
  onPreviewed: (version: string) => void;
}

function toBlobUrl(base64: string) {
  const bin = atob(base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
}

/** The backend renders the PDF (ReportLab). This panel only shows it and says when it is out of date. */
export function PdfPanel({ userId, params, version, blocked, onPreviewed }: Props) {
  const [pdf, setPdf] = useState<{ meta: PdfPreview; src: string; version: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => () => {
    if (pdf?.src.startsWith("blob:")) URL.revokeObjectURL(pdf.src);
  }, [pdf]);

  async function generate() {
    setBusy(true);
    setErr(null);
    try {
      const meta = await api.pdfPreview(userId, params);
      const src = meta.base64 ? toBlobUrl(meta.base64) : meta.url!;
      setPdf({ meta, src, version });
      onPreviewed(version);
    } catch (e) {
      setErr(explainError(e));
    } finally {
      setBusy(false);
    }
  }

  const stale = pdf != null && pdf.version !== version;

  return (
    <div className="pdf">
      <div className="pdf-bar">
        <button className="btn small" onClick={generate} disabled={busy || blocked}>
          {busy ? "Generating…" : pdf ? (stale ? "Regenerate PDF" : "Refresh PDF") : "Preview PDF"}
        </button>
        {pdf && (
          <a className="btn small" href={pdf.src} download={pdf.meta.filename}>Download</a>
        )}
        {stale && <span className="status-chip pending_approval">Out of date: values changed</span>}
        {pdf && !stale && <span className="status-chip approved">Matches current values</span>}
      </div>
      {blocked && !pdf && <small className="muted">Fix the highlighted values to preview the PDF.</small>}
      {err && <div className="alert" role="alert">{err}</div>}
      {pdf && (
        <iframe className={`pdf-frame${stale ? " stale" : ""}`} title={`Quote PDF ${pdf.meta.filename}`} src={pdf.src} />
      )}
    </div>
  );
}
