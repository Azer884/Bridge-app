import { useCallback, useState } from "react";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { api, apiMode, explainError } from "../../../shared/api";
import { useActor } from "../actor";
import { enableNotifications, pushState, type PushState } from "../push";
import { C, useTheme, type Pref } from "../theme";
import { Banner, Btn, Group, Row, Screen, Segmented, T } from "../ui";

const ic = (name: keyof typeof Ionicons.glyphMap) => <Ionicons name={name} size={22} color={C.blue} />;
const ROLE = { admin: "Admin", approver: "Approver", reviewer: "Reviewer" } as const;
const STATE: Record<PushState, string> = { on: "On", off: "Off", denied: "Blocked in phone settings", unsupported: "Needs a real phone and the live backend" };

export default function SettingsScreen() {
  const { pref, setPref } = useTheme();
  const { users, me, choose } = useActor();
  const nav = useNavigation<any>();
  const [push, setPush] = useState<PushState>("unsupported");
  const [note, setNote] = useState<{ kind: "info" | "danger"; text: string } | null>(null);

  useFocusEffect(useCallback(() => { void pushState().then(setPush); }, []));

  async function test() {
    setNote(null);
    try {
      await api.testPush();
      setNote({ kind: "info", text: "Test sent. It should arrive on this phone in a few seconds." });
    } catch (e) {
      setNote({ kind: "danger", text: explainError(e) });
    }
  }

  return (
    <Screen>
      <Group title="Notifications" footer="Each new quote sends a notification. Tap it to review and approve.">
        <Row left={ic("notifications-outline")} title="Quotes to approve" value={STATE[push]} chevron={false} />
      </Group>
      {push === "off" ? <Btn label="Turn on notifications" onPress={async () => setPush(await enableNotifications())} /> : null}
      {push === "on" ? <Btn kind="tinted" label="Send a test notification" onPress={test} /> : null}
      {note ? <Banner kind={note.kind} text={note.text} /> : null}

      {users.length > 0 ? (
        <Group title="You are" footer="Approvers and admins can approve or reject. Reviewers can only read.">
          {users.map((u) => (
            <Row
              key={u.id}
              title={u.name}
              subtitle={ROLE[u.module_role]}
              chevron={false}
              right={me?.id === u.id ? <Ionicons name="checkmark" size={22} color={C.blue} /> : undefined}
              onPress={() => choose(u.id)}
            />
          ))}
        </Group>
      ) : null}

      <Group title="Business">
        <Row left={ic("albums-outline")} title="Pipeline" subtitle="Every job, start to finish" onPress={() => nav.navigate("Pipeline")} />
        <Row left={ic("calendar-outline")} title="Calendar" subtitle="Bookings and suggested times" onPress={() => nav.navigate("Calendar")} />
        <Row left={ic("people-outline")} title="Customers" subtitle="Everyone Gesir has talked to" onPress={() => nav.navigate("Customers")} />
        <Row left={ic("logo-whatsapp")} title="WhatsApp number" subtitle="Link the number Gesir chats from" onPress={() => nav.navigate("Link")} />
        <Row left={ic("person-circle-outline")} title="Personas" subtitle="The character customers talk to" onPress={() => nav.navigate("Personas")} />
        <Row left={ic("pulse-outline")} title="Status" subtitle="Models and recent events" onPress={() => nav.navigate("Status")} />
      </Group>

      <Group title="Appearance">
        <Row title={<Segmented<Pref> value={pref} onChange={setPref} options={[{ id: "light", label: "Light" }, { id: "dark", label: "Dark" }, { id: "system", label: "System" }]} />} chevron={false} />
      </Group>

      <T v="foot" style={{ textAlign: "center" }}>{apiMode() === "mock" ? "Showing sample data" : "Connected to the live backend"}</T>
    </Screen>
  );
}