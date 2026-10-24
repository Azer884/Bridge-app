import { useState } from "react";
import { api, explainError } from "../../../shared/api";
import { money, phone } from "../../../shared/format";
import type { QuoteDraft } from "../../../shared/types";
import { Banner, Btn, Field, Group, Row, Sheet, T, success } from "../ui";

interface Props {
  userId: string;
  number: string;
  quote: QuoteDraft;
  /** The estimate is approved and no final price has been sent yet. */
  open: boolean;
  onSent: () => void;
}

/** After the site visit the owner measures and sends the final price. The backend only accepts it once the estimate was approved. */
export function FinalCard({ userId, number, quote, open, onSent }: Props) {
  const sent = quote.approved_total ?? quote.total ?? 0;
  const [raw, setRaw] = useState(String(sent || ""));
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);

  const total = Number(raw);
  const valid = raw !== "" && Number.isFinite(total) && total > 0;

  if (!open) {
    return quote.final_total != null ? (
      <Group title="Final price sent">
        <Row title="Estimate" value={money(sent, quote.currency)} chevron={false} />
        <Row title="Final" value={money(quote.final_total, quote.currency)} chevron={false} />
      </Group>
    ) : null;
  }

  async function send() {
    setBusy(true);
    setErr(null);
    try {
      await api.confirmFinal(userId, total);
      success();
      setConfirm(false);
      onSent();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Group title="Final price after the visit" footer={valid ? "This replaces the estimate for the customer." : "Enter an amount above zero."}>
        <Row title="Estimate sent" value={money(sent, quote.currency)} chevron={false} />
        <Field label={`Final total (${quote.currency})`} keyboardType="decimal-pad" value={raw} onChangeText={(t) => setRaw(t.replace(/[^0-9.]/g, ""))} />
      </Group>
      <Btn label="Send final price" disabled={!valid} onPress={() => { setErr(null); setConfirm(true); }} />

      <Sheet visible={confirm} title="Send the final price?" onClose={() => !busy && setConfirm(false)}>
        <Group>
          <Row title="Total" right={<T v="money">{money(total, quote.currency)}</T>} />
          <Row title="Goes to" value={phone(number)} />
        </Group>
        <T v="sub">It is sent on WhatsApp right away. You cannot take the message back. It is saved to the activity log.</T>
        {err != null ? <Banner text={explainError(err)} /> : null}
        <Btn label={err ? "Try again" : "Send final price"} busy={busy} onPress={send} />
      </Sheet>
    </>
  );
}
