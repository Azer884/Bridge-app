import { useEffect, useMemo, useRef, useState } from "react";
import { Linking, TextInput, View } from "react-native";
import { useNavigation, useRoute } from "@react-navigation/native";
import { api, explainError } from "../../../shared/api";
import { money, phone } from "../../../shared/format";
import { STAGES, validateParams } from "../../../shared/params";
import type { ParamValue, QuoteDetail as Detail, QuoteDraft } from "../../../shared/types";
import { useAsync } from "../hooks";
import { AuditList } from "../quote/AuditList";
import { ChatView } from "../quote/ChatView";
import { ParamsEditor } from "../quote/ParamsEditor";
import { FinalCard } from "../quote/FinalCard";
import { PdfCard } from "../quote/PdfCard";
import { RejectSheet } from "../quote/RejectSheet";
import { PriceCard, type CalcState } from "../quote/PriceCard";
import { C, F, useTheme } from "../theme";
import { Banner, Btn, Empty, Group, OrbyteChip, Pill, Row, Screen, Segmented, Sheet, T, success } from "../ui";

type Tab = "quote" | "chat" | "activity";

export default function QuoteDetailScreen() {
  useTheme();
  const { userId } = useRoute<any>().params as { userId: string };
  const [tab, setTab] = useState<Tab>("quote");
  const { data, error, loading, reload } = useAsync(() => api.getQuoteDetail(userId), [userId], 3_000);

  if (!data) {
    return (
      <Screen>
        {error != null ? <Banner text={explainError(error)} action="Try again" onAction={reload} /> : <Empty icon="hourglass-outline" title={loading ? "Loading quote" : "Quote not found"} />}
      </Screen>
    );
  }
  // Tab lives here so it survives the remount when the status changes. The activity list reads straight from `d`, so it updates on each poll.
  return <Loaded key={userId + data.status + !!data.revising} d={data} reload={reload} tab={tab} setTab={setTab} />;
}

function Loaded({ d, reload, tab, setTab }: { d: Detail; reload: () => Promise<void>; tab: Tab; setTab: (t: Tab) => void }) {
  useTheme();
  const nav = useNavigation<any>();
  const [rejecting, setRejecting] = useState(false);

  const params = d.params;
  const server = params?.current ?? {};
  const [values, setValues] = useState<Record<string, ParamValue>>(server);
  const [quote, setQuote] = useState<QuoteDraft | null>(d.quote);
  const [duration, setDuration] = useState<number | null>(d.duration_hours);
  const [calc, setCalc] = useState<CalcState>({ status: "idle" });
  const [manual, setManual] = useState<string | null>(null);
  const [previewed, setPreviewed] = useState<string | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [sending, setSending] = useState(false);
  const [sendErr, setSendErr] = useState<unknown>(null);
  const seq = useRef(0);

  const readOnly = d.locked || d.status === "collecting" || !!d.revising || !d.quote || !params;
  const errors = useMemo(() => (params ? validateParams(params.schema, values) : {}), [params, values]);
  const hasErrors = Object.keys(errors).length > 0;
  const dirty = JSON.stringify(values) !== JSON.stringify(server);
  const overrides = params ? params.schema.filter((f) => values[f.key] != null && values[f.key] !== params.ai[f.key]).length : 0;

  // Live recalculation: wait for typing to pause, drop answers that arrive late.
  useEffect(() => {
    if (readOnly || !params) return;
    if (!dirty) {
      setQuote(d.quote);
      setDuration(d.duration_hours);
      setCalc({ status: "idle" });
      return;
    }
    if (hasErrors) return;
    const mine = ++seq.current;
    setCalc({ status: "loading" });
    const t = setTimeout(async () => {
      try {
        const r = await api.recalculate(d.user_id, values);
        if (mine !== seq.current) return;
        setQuote(r.quote);
        setDuration(r.duration_hours);
        setCalc({ status: "idle" });
      } catch (e) {
        if (mine !== seq.current) return;
        setCalc({ status: "error", message: `Could not recalculate. ${explainError(e)} The price shown may be out of date.` });
      }
    }, 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values]);

  const cur = quote?.currency ?? "MYR";
  const calcTotal = quote?.total ?? 0;
  const manualNum = manual == null ? null : Number(manual);
  const manualValid = manualNum == null || (Number.isFinite(manualNum) && manualNum > 0);
  const manualActive = manualNum != null && manualValid && Math.abs(manualNum - calcTotal) > 0.004;
  const finalTotal = manualActive ? manualNum! : calcTotal;
  const version = JSON.stringify([values, manualActive ? manualNum : null]);
  const pdfStale = previewed !== version;
  const canSend = !readOnly && !hasErrors && calc.status === "idle" && manualValid && finalTotal > 0;
  const stage = STAGES.find((s) => s.id === d.stage);

  const goCalendar = () => nav.getParent()?.navigate("CalendarTab", { screen: "CalendarHome", params: { book: d.user_id } });

  async function send() {
    setSending(true);
    setSendErr(null);
    try {
      if (dirty) await api.saveParams(d.user_id, values);
      await api.approveQuote(d.user_id, manualActive ? manualNum! : undefined);
      success();
      setConfirm(false);
      await reload();
    } catch (e) {
      setSendErr(e);
    } finally {
      setSending(false);
    }
  }

  const footer =
    tab === "quote" && !readOnly && quote ? (
      <View style={{ flexDirection: "row", alignItems: "center", gap: 14 }}>
        <View style={{ flex: 1 }}>
          <T v="foot">The customer gets</T>
          <T v="money">{money(finalTotal, cur)}</T>
        </View>
        <View style={{ flex: 1.2 }}>
          <View style={{ gap: 8 }}>
            <Btn label={calc.status === "loading" ? "Recalculating…" : "Approve and send"} disabled={!canSend} onPress={() => { setSendErr(null); setConfirm(true); }} />
            <Btn kind="danger" small label="Reject and re-prompt" disabled={calc.status === "loading"} onPress={() => setRejecting(true)} />
          </View>
        </View>
      </View>
    ) : undefined;

  return (
    <>
      <Screen footer={footer}>
        <Group>
          <Row title={d.job.name ?? "Unnamed customer"} subtitle={d.job.address ?? "No address yet"} right={<View style={{ alignItems: "flex-end", gap: 6 }}><Pill status={d.stage} label={stage?.label} /><OrbyteChip q={d} /></View>} />
          <Row title="WhatsApp" value={phone(d.job.phone ?? d.user_id)} onPress={() => Linking.openURL(`https://wa.me/${(d.job.phone ?? d.user_id).replace(/\D/g, "")}`)} />
          {d.job.location ? <Row title="Shared location" value={d.job.location.name ?? d.job.location.address ?? "Open in Maps"} onPress={() => Linking.openURL(d.job.location!.maps_url)} /> : null}
          {d.job.preferred_datetime ? <Row title="They asked for" value={d.job.preferred_datetime} chevron={false} /> : null}
        </Group>

        {(d.needs_human || d.attention) && tab !== "chat" ? <Banner kind="warn" text="Needs you: open Chat to reply." action="Open chat" onAction={() => setTab("chat")} /> : null}

        <Segmented value={tab} onChange={setTab} options={[{ id: "quote", label: "Quote" }, { id: "chat", label: `Chat · ${d.photos.length} photos` }, { id: "activity", label: `Activity · ${d.audit.length}` }]} />

        {d.revising ? <Banner kind="info" text="Gesir is redrafting this quote with your note. Nothing was sent to the customer. The new draft appears here in a moment." /> : null}

        {tab === "chat" && <ChatView name={d.job.name ?? "Customer"} number={d.job.phone ?? d.user_id} chat={d.chat} photos={d.photos} userId={d.user_id} needsHuman={d.needs_human} humanActive={d.human_active} onSent={() => void reload()} />}
        {tab === "activity" && <AuditList entries={d.audit} />}

        {tab === "quote" && (
          <>
            {d.status === "needs_inspection" && (
              <Group title="Needs a visit" footer="Gesir could not price this from chat alone. Look at the photos, visit the site, then reply yourself.">
                <Row title="See photos and chat" onPress={() => setTab("chat")} />
                <Row title="Book a site visit" tint={C.blue} onPress={goCalendar} />
              </Group>
            )}

            {d.status === "collecting" && <Banner kind="info" text="Gesir is still asking the customer questions. Fields fill in as they answer, and the price appears when everything is known." />}

            {quote && (quote.flags.length > 0 || quote.assumptions.length > 0) && (
              <View style={{ gap: 8 }}>
                <T v="label" style={{ paddingHorizontal: 16 }}>Check before sending</T>
                {quote.flags.map((f) => <Banner key={f} kind="warn" text={f} />)}
                {quote.assumptions.map((a) => <T key={a} v="foot" style={{ paddingHorizontal: 16 }}>Assumed: {a}</T>)}
              </View>
            )}

            {params && (
              <View style={{ gap: 6 }}>
                <View style={{ flexDirection: "row", justifyContent: "space-between", paddingHorizontal: 16 }}>
                  <T v="label">What Gesir read</T>
                  {overrides > 0 && !readOnly ? <T v="label" style={{ color: C.ink }}>{overrides} changed by you</T> : null}
                </View>
                {!readOnly && <T v="foot" style={{ paddingHorizontal: 16 }}>Fix anything that looks wrong. The price updates as you type.</T>}
                <ParamsEditor
                  params={params}
                  values={values}
                  errors={errors}
                  readOnly={readOnly}
                  onChange={(k, v) => setValues((s) => ({ ...s, [k]: v }))}
                  onReset={(k) => setValues((s) => ({ ...s, [k]: params.ai[k] }))}
                />
              </View>
            )}

            {quote && (
              <View style={{ gap: 6 }}>
                <T v="label" style={{ paddingHorizontal: 16 }}>{d.locked ? "Price sent" : "Price"}</T>
                <PriceCard quote={quote} before={d.quote!} calc={calc} durationHours={duration} />
              </View>
            )}

            {quote && !readOnly && (
              <Group title="Adjust the final total (optional)" footer={!manualValid ? "Enter an amount above zero." : manualActive ? `Replaces the calculated ${money(calcTotal, cur)}.` : "Same as calculated."}>
                <Row
                  title={cur}
                  right={
                    <TextInput
                      accessibilityLabel="Final total"
                      keyboardType="decimal-pad"
                      value={manual ?? String(calcTotal)}
                      onChangeText={(t) => setManual(t.replace(/[^0-9.]/g, ""))}
                      style={{ minWidth: 110, minHeight: 44, textAlign: "right", fontFamily: F.display, fontSize: 24, color: manualValid ? C.ink : C.danger }}
                    />
                  }
                />
                {manual != null ? <Row title="Use calculated total" chevron={false} tint={C.blue} onPress={() => setManual(null)} /> : null}
              </Group>
            )}

            {quote && (d.status === "approved" || d.status === "completed") && (
              <FinalCard userId={d.user_id} number={d.job.phone ?? d.user_id} quote={quote} open={d.status === "approved"} onSent={() => void reload()} />
            )}

            {quote && params && (
              <PdfCard
                userId={d.user_id}
                customer={d.job.name ?? "customer"}
                quote={quote}
                params={values}
                version={version}
                blocked={hasErrors || (readOnly && !d.locked)}
                onPreviewed={setPreviewed}
              />
            )}

            {quote && (d.locked || (!readOnly && duration != null)) && (
              <Btn kind="tinted" icon="calendar-outline" label={d.locked ? "Find a time" : "See suggested times"} onPress={goCalendar} />
            )}
            {!readOnly && hasErrors ? <Banner text="Fix the highlighted values before sending." /> : null}
          </>
        )}
      </Screen>

      <RejectSheet visible={rejecting} userId={d.user_id} name={d.job.name ?? "the customer"} onClose={() => setRejecting(false)} onDone={() => { setRejecting(false); void reload(); }} />

      <Sheet visible={confirm} title="Send this quote?" onClose={() => !sending && setConfirm(false)}>
        <Group>
          <Row title="Total" right={<T v="money">{money(finalTotal, cur)}</T>} />
          <Row title="Goes to" value={phone(d.job.phone ?? d.user_id)} />
          <Row title="Your changes" value={overrides > 0 || manualActive ? `${overrides} value${overrides === 1 ? "" : "s"}${manualActive ? " + total" : ""}` : "None"} />
          <Row title="PDF preview" value={pdfStale ? "Not checked" : "Matches"} />
        </Group>
        {pdfStale ? <Banner kind="warn" text="You have not previewed the PDF with these values." /> : null}
        <T v="sub">It is sent from your WhatsApp number by Gesir, on your behalf, right away. You cannot take the message back. Changes are saved to the activity log.</T>
        {sendErr != null ? <Banner text={explainError(sendErr)} /> : null}
        <Btn label={sendErr ? "Try again" : "Send quote"} busy={sending} onPress={send} />
      </Sheet>
    </>
  );
}

