import { Ionicons } from "@expo/vector-icons";
import { useNavigation } from "@react-navigation/native";
import { apiMode } from "../../../shared/api";
import { C, useTheme, type Pref } from "../theme";
import { Group, Row, Screen, Segmented, T } from "../ui";

const ic = (name: keyof typeof Ionicons.glyphMap) => <Ionicons name={name} size={22} color={C.blue} />;

export default function SettingsScreen() {
  const { pref, setPref } = useTheme();
  const nav = useNavigation<any>();
  return (
    <Screen>
      <Group title="Gesir">
        <Row left={ic("logo-whatsapp")} title="WhatsApp number" subtitle="Link the number Gesir chats from" onPress={() => nav.navigate("Link")} />
        <Row left={ic("people-outline")} title="Customers" subtitle="Everyone Gesir has talked to" onPress={() => nav.navigate("Customers")} />
        <Row left={ic("person-circle-outline")} title="Personas" subtitle="The character customers talk to" onPress={() => nav.navigate("Personas")} />
        <Row left={ic("pulse-outline")} title="Status" subtitle="Models and recent events" onPress={() => nav.navigate("Status")} />
      </Group>

      <Group title="Appearance" footer="System follows your phone's setting.">
        <Row title={<Segmented<Pref> value={pref} onChange={setPref} options={[{ id: "system", label: "System" }, { id: "light", label: "Light" }, { id: "dark", label: "Dark" }]} />} chevron={false} />
      </Group>

      <T v="foot" style={{ textAlign: "center" }}>{apiMode() === "mock" ? "Showing sample data" : "Connected to the live backend"}</T>
    </Screen>
  );
}
