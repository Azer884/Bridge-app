import { Link, useParams } from "react-router-dom";
import { api } from "@shared/api";
import { phone } from "@shared/format";
import { useAsync } from "../hooks";
import { QuoteDetail } from "../quote/QuoteDetail";

/** One project (Orbyte's word for a job): what Gesir read, the price, approve or reject, the chat, the PDF and the activity log.
 * Opened from Projects, Clients or the Dashboard. */
export default function Quotes() {
  const { userId = "" } = useParams();
  const rows = useAsync(() => api.listPipeline(), [], 30_000);
  const row = rows.data?.find((r) => r.user_id === userId);
  const name = row?.job.name ?? phone(userId);

  return (
    <>
      <nav className="ob-crumbs" aria-label="Breadcrumb">
        <Link to="/app/pipeline">Projects</Link>
        <span aria-hidden>/</span>
        <b>Repaint for {name}</b>
      </nav>
      <QuoteDetail key={userId} userId={userId} onChanged={() => void rows.reload()} />
    </>
  );
}
