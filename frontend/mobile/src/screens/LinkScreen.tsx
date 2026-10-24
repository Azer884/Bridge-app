import { useState } from "react";
import { Ionicons } from "@expo/vector-icons";
import { TextInput, View } from "react-native";
import { api, explainError } from "../../../shared/api";
import { COUNTRIES, DEFAULT_COUNTRY, countryByIso, toE164, validNational } from "../../../shared/countries";
import { phone } from "../../../shared/format";
import { useAsync } from "../hooks";
import { C, F, useTheme } from "../theme";
import { Banner, Btn, Field, Group, Pill, Row, Screen, Sheet, T } from "../ui";

export default function LinkScreen() {
  useTheme();
  const [iso, setIso] = useState(DEFAULT_COUNTRY);
  const [national, setNational] = useState("");
  const [picking, setPicking] = useState(false);
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const link = useAsync(() => api.whatsappStatus(), [], 3_000);
  const status = link.data?.status ?? "unlinked";
  const country = countryByIso(iso);
  const matches = COUNTRIES.filter((c) => `${c.name} +${c.dial}`.toLowerCase().includes(query.trim().toLowerCase()));

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      await link.reload();
    } catch (e) {
      setMsg(explainError(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Screen>
        <T v="sub">Gesir chats with your customers from your own number, on your behalf. It asks you first.</T>

        {status === "unlinked" ? (
          <>
            <Group title="Your number" footer={`The number your customers already message. Leave out the first 0. Sent as +${toE164(country, national) || country.dial}.`}>
              <Row title="Country" value={`${country.name} (+${country.dial})`} onPress={() => { setQuery(""); setPicking(true); }} />
              <Row
                title="Number"
                chevron={false}
                right={
                  <TextInput
                    accessibilityLabel="WhatsApp number"
                    keyboardType="phone-pad"
                    placeholder="12 345 6789"
                    placeholderTextColor={C.ink3}
                    value={national}
                    onChangeText={setNational}
                    style={{ minWidth: 160, minHeight: 44, textAlign: "right", fontFamily: F.sys, fontSize: 17, color: C.ink }}
                  />
                }
              />
            </Group>
            <Btn label="Link this number" icon="logo-whatsapp" busy={busy} disabled={!validNational(national)} onPress={() => run(() => api.linkWhatsapp(toE164(country, national)))} />
          </>
        ) : (
          <>
            <Group title="Your number">
              <Row title={phone(link.data?.number ?? undefined)} right={<Pill status={status === "linked" ? "approved" : "pending_approval"} label={status === "linked" ? "Linked" : "Confirm on your phone"} />} />
              <Row title={status === "linked" ? "Gesir is answering new customer messages on this number." : "Waiting for WhatsApp to confirm. This updates by itself."} chevron={false} />
            </Group>
            <Btn kind="danger" label="Unlink number" disabled={busy} onPress={() => run(() => api.unlinkWhatsapp())} />
          </>
        )}
        {msg ? <Banner text={msg} /> : null}
        {link.error != null && !link.data ? <Banner text={explainError(link.error)} /> : null}

        <Group title="Gesir does without asking">
          <Row title="Answers customers and asks the job questions" chevron={false} left={<Ionicons name="chatbubbles-outline" size={22} color={C.blue} />} />
          <Row title="Drafts a price from what the customer said" chevron={false} left={<Ionicons name="calculator-outline" size={22} color={C.blue} />} />
        </Group>
        <Group title="Gesir always asks you first">
          <Row title="Sending any price" subtitle="The customer gets it only after you approve." chevron={false} left={<Ionicons name="hand-left-outline" size={22} color={C.tape} />} />
          <Row title="Jobs it cannot price" subtitle="It flags them for a visit instead of guessing." chevron={false} left={<Ionicons name="flag-outline" size={22} color={C.tape} />} />
        </Group>
      </Screen>

      <Sheet visible={picking} title="Country code" onClose={() => setPicking(false)}>
        <Field label="Search" value={query} onChangeText={setQuery} placeholder="Country or code" autoCorrect={false} />
        <Group>
          {matches.map((c) => (
            <Row key={c.iso} title={c.name} value={`+${c.dial}`} chevron={false} right={c.iso === iso ? <Ionicons name="checkmark" size={22} color={C.blue} /> : undefined} onPress={() => { setIso(c.iso); setPicking(false); }} />
          ))}
        </Group>
      </Sheet>
    </>
  );
}
