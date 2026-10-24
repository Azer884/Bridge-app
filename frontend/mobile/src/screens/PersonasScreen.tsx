import { useState } from "react";
import { View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { api, explainError } from "../../../shared/api";
import { PERSONA_LIMITS, type Persona } from "../../../shared/types";
import { useAsync } from "../hooks";
import { C, useTheme } from "../theme";
import { Banner, Btn, Empty, Field, Group, Row, Screen, Sheet, T, success } from "../ui";

const FIELDS: { key: keyof Persona; label: string; hint: string; area: boolean }[] = [
  { key: "name", label: "Name", hint: "What customers see as the sender.", area: false },
  { key: "style", label: "Voice", hint: "How the assistant talks. Tone, length, slang.", area: true },
  { key: "greeting", label: "Greeting", hint: "First message. Use {name}, {business} and {owner}.", area: true },
  { key: "service_question", label: "First question", hint: "Asked after the greeting.", area: true },
  { key: "closing", label: "Closing", hint: "Sent when the chat is done and the quote is drafted.", area: true },
];
const BLANK: Persona = { name: "", style: "", greeting: "", service_question: "", closing: "" };
const fill = (t: string, p: Persona) => t.split("{name}").join(p.name || "Name").split("{business}").join("Your Business").split("{owner}").join("the owner");
const slug = (s: string) => s.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

export default function PersonasScreen() {
  useTheme();
  const { data, error, loading, reload } = useAsync(() => api.listPersonas(), []);
  const [editId, setEditId] = useState<string | null>(null); // "" = new
  const [form, setForm] = useState<Persona>(BLANK);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ text: string; bad: boolean } | null>(null);

  const personas = data?.personas ?? {};
  const isNew = editId === "";
  const over = FIELDS.some((f) => form[f.key].length > PERSONA_LIMITS[f.key]);
  const empty = FIELDS.some((f) => !form[f.key].trim());

  async function run(fn: () => Promise<unknown>, ok: string) {
    setBusy(true);
    try {
      await fn();
      setMsg({ text: ok, bad: false });
      success();
      await reload();
      return true;
    } catch (e) {
      setMsg({ text: explainError(e), bad: true });
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function save() {
    const id = isNew ? slug(form.name) : editId!;
    if (!id) return setMsg({ text: "Give the persona a name first.", bad: true });
    if (isNew && personas[id]) return setMsg({ text: "A persona with that name already exists.", bad: true });
    if (await run(() => api.savePersona(id, form), "Persona saved")) setEditId(null);
  }

  return (
    <>
      <Screen onRefresh={reload}>
        <T v="sub">The character who chats with your customers. A new voice applies from the next customer message.</T>
        {msg && editId == null ? <Banner kind={msg.bad ? "danger" : "info"} text={msg.text} /> : null}
        {error != null && !data && <Banner text={explainError(error)} action="Try again" onAction={reload} />}
        {loading && !data ? <Empty icon="hourglass-outline" title="Loading personas" /> : null}
        <Group>
          {Object.entries(personas).map(([id, p]) => (
            <Row
              key={id}
              left={<Ionicons name={id === data?.active ? "radio-button-on" : "radio-button-off"} size={24} color={id === data?.active ? C.blue : C.ink3} />}
              title={p.name}
              subtitle={p.style}
              onPress={() => { setForm(p); setEditId(id); setMsg(null); }}
            />
          ))}
        </Group>
        <Btn kind="tinted" icon="add" label="New persona" onPress={() => { setForm(BLANK); setEditId(""); setMsg(null); }} />
      </Screen>

      <Sheet visible={editId !== null} title={isNew ? "New persona" : "Edit persona"} onClose={() => setEditId(null)}>
        {FIELDS.map((f) => (
          <Field key={f.key} label={f.label} hint={f.hint} multiline={f.area} value={form[f.key]} onChangeText={(t) => setForm({ ...form, [f.key]: t })} counter={{ len: form[f.key].length, max: PERSONA_LIMITS[f.key] }} />
        ))}
        <View style={{ backgroundColor: "#E5DDD5", borderRadius: 18, padding: 12, gap: 8 }}>
          <T v="label" style={{ color: "#3F3A33" }}>Preview in WhatsApp</T>
          {[fill(form.greeting, form), null, fill(form.service_question, form), null, fill(form.closing, form)].map((m, i) =>
            m === null ? (
              <View key={i} style={{ alignSelf: "flex-end", backgroundColor: "#D9FDD3", borderRadius: 12, padding: 10 }}><T style={{ color: "#041B2D" }}>{i === 1 ? "Hi, I need a quote." : "My kitchen sink is leaking."}</T></View>
            ) : (
              <View key={i} style={{ alignSelf: "flex-start", backgroundColor: "#FFFFFF", borderRadius: 12, padding: 10, maxWidth: "90%" }}><T style={{ color: "#041B2D" }}>{m || "…"}</T></View>
            ),
          )}
          <T v="foot" style={{ color: "#3F3A33" }}>The server fills in your real business and owner names.</T>
        </View>
        {msg?.bad ? <Banner text={msg.text} /> : null}
        <Btn label="Save persona" busy={busy} disabled={over || empty} onPress={save} />
        {!isNew && editId !== data?.active ? <Btn kind="tinted" label="Make active" disabled={busy} onPress={async () => { if (await run(() => api.setActivePersona(editId!), `${personas[editId!]?.name ?? "Persona"} is now active`)) setEditId(null); }} /> : null}
      </Sheet>
    </>
  );
}
