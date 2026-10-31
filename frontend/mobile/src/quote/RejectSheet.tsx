import { useState } from "react";
import { View } from "react-native";
import { api, explainError } from "../../../shared/api";
import { Banner, Btn, Chip, Field, Sheet, T, success } from "../ui";

const QUICK = ["Price is too high", "Wrong room size", "Missing a surface or item", "Check the photos again"];
const MIN = 5;

/** The owner turns the draft down and tells Gesir what to change. Nothing is sent to the customer. */
export function RejectSheet({ visible, userId, name, onClose, onDone }: { visible: boolean; userId: string; name: string; onClose: () => void; onDone: () => void }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const valid = note.trim().length >= MIN;

  async function submit() {
    setBusy(true);
    setErr(null);
    try {
      await api.rejectQuote(userId, note.trim());
      success();
      setNote("");
      onDone();
    } catch (e) {
      setErr(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <Sheet visible={visible} title="Reject this draft?" onClose={() => !busy && onClose()}>
      <T v="sub">Tell Gesir what is wrong. It redrafts the quote for {name}. Nothing is sent to the customer.</T>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {QUICK.map((q) => <Chip key={q} label={q} onPress={() => setNote((n) => (n.trim() ? `${n.trim()}. ${q}` : q))} />)}
      </View>
      <Field label="What should Gesir change?" hint={note.length > 0 && !valid ? "Write a few words so Gesir knows what to fix." : "Saved to the activity log with your name."} multiline maxLength={500} value={note} onChangeText={setNote} placeholder="For example: the ceiling is 3 m high, not 2.4 m" style={{ minHeight: 96, textAlignVertical: "top" }} />
      {err != null ? <Banner text={explainError(err)} /> : null}
      <Btn kind="danger" label={err ? "Try again" : "Reject and redraft"} busy={busy} disabled={!valid} onPress={submit} />
    </Sheet>
  );
}
