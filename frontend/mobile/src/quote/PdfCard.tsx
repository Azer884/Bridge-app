import { createElement, useEffect, useState } from "react";
import { Linking, Platform, View } from "react-native";
import { api, explainError } from "../../../shared/api";
import { money } from "../../../shared/format";
import type { ParamValue, PdfPreview, QuoteDraft } from "../../../shared/types";
import { C, F } from "../theme";
import { Banner, Btn, Group, Row, Sheet, T, success } from "../ui";

interface Props {
  userId: string;
  customer: string;
  quote: QuoteDraft;
  params: Record<string, ParamValue>;
  /** Changes whenever anything that affects the PDF changes. */
  version: string;
  blocked: boolean;
  onPreviewed: (version: string) => void;
}

function toBlobUrl(base64: string) {
  const bin = atob(base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
}

/** The backend renders the PDF. On the web it shows in a frame; on phones the system viewer opens it. */
export function PdfCard({ userId, customer, quote, params, version, blocked, onPreviewed }: Props) {
  const [meta, setMeta] = useState<PdfPreview | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [seen, setSeen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => () => {
    if (src?.startsWith("blob:")) URL.revokeObjectURL(src);
  }, [src]);

  async function generate() {
    setBusy(true);
    setErr(null);
    try {
      const m = await api.pdfPreview(userId, params);
      setMeta(m);
      setSrc(Platform.OS === "web" && m.base64 ? toBlobUrl(m.base64) : m.url ?? null);
      setSeen(version);
      onPreviewed(version);
      setOpen(true);
      success();
    } catch (e) {
      setErr(explainError(e));
    } finally {
      setBusy(false);
    }
  }

  const stale = seen != null && seen !== version;

  return (
    <>
      <Group footer={blocked ? "Fix the highlighted values to preview the PDF." : undefined}>
        <Row
          title="Quote PDF"
          subtitle={seen == null ? "Not previewed yet" : stale ? "Out of date: values changed" : "Matches current values"}
          right={seen != null ? <T v="foot" style={{ color: stale ? C.dangerInk : C.okInk, fontFamily: F.semi }}>{stale ? "Out of date" : "Up to date"}</T> : undefined}
        />
        {seen != null ? <Row title="Open preview" onPress={() => setOpen(true)} /> : null}
      </Group>
      <Btn kind="tinted" icon="document-text-outline" label={busy ? "Generating…" : seen != null ? (stale ? "Regenerate PDF" : "Refresh PDF") : "Preview PDF"} busy={busy} disabled={blocked} onPress={generate} />
      {err ? <Banner text={err} /> : null}

      <Sheet visible={open && meta != null} title={meta?.filename ?? "Quote PDF"} onClose={() => setOpen(false)}>
        {stale ? <Banner kind="warn" text="This preview is out of date. Regenerate it after changing values." /> : null}
        {Platform.OS === "web" && src ? (
          <View style={{ height: 520 }}>
            {createElement("iframe", { src, title: "Quote PDF", style: { width: "100%", height: "100%", border: 0, borderRadius: 12, background: "#fff", opacity: stale ? 0.45 : 1 } })}
          </View>
        ) : (
          <View style={{ backgroundColor: "#FFFFFF", borderRadius: 12, padding: 20, gap: 10, opacity: stale ? 0.5 : 1 }}>
            <T v="title" style={{ color: "#041B2D" }}>Quote for {customer}</T>
            {quote.lines.map((l, i) => (
              <View key={i} style={{ flexDirection: "row", justifyContent: "space-between", gap: 12 }}>
                <T v="sub" style={{ flex: 1, color: "#041B2D" }}>{l.description}</T>
                <T v="sub" style={{ color: "#041B2D" }}>{money(l.amount, quote.currency)}</T>
              </View>
            ))}
            <View style={{ height: 1, backgroundColor: "#D2DFDF" }} />
            <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
              <T v="headline" style={{ color: "#041B2D" }}>Total</T>
              <T v="money" style={{ color: "#041B2D" }}>{money(quote.total, quote.currency)}</T>
            </View>
            <T v="foot">Layout preview. The real PDF is made by the server.</T>
          </View>
        )}
        {src && Platform.OS !== "web" ? <Btn kind="primary" icon="open-outline" label="Open PDF" onPress={() => Linking.openURL(src)} /> : null}
      </Sheet>
    </>
  );
}
