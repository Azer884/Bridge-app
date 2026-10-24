import { useNavigation } from "@react-navigation/native";
import { api, explainError } from "../../../shared/api";
import { money, phone } from "../../../shared/format";
import { useAsync } from "../hooks";
import { useTheme } from "../theme";
import { Banner, Empty, Group, Row, Screen } from "../ui";

export default function CustomersScreen() {
  useTheme();
  const nav = useNavigation<any>();
  const { data, error, loading, reload } = useAsync(() => api.listCustomers(), [], 30_000);
  const list = data ?? [];

  return (
    <Screen onRefresh={reload} refreshing={loading && !!data}>
      {error != null ? <Banner text={explainError(error)} action="Try again" onAction={reload} /> : null}
      {data && list.length === 0 ? <Empty icon="people-outline" title="No customers yet" text="They appear here after their first WhatsApp message." /> : null}
      {list.length > 0 && (
        <Group footer="Everyone Gesir has talked to, with every job they have had.">
          {list.map((c) => {
            const last = c.orders[c.orders.length - 1]?.quote;
            const t = last?.final_total ?? last?.approved_total ?? last?.total;
            const jobs = `${c.orders.length} ${c.orders.length === 1 ? "job" : "jobs"}`;
            return (
              <Row
                key={c.user_id}
                title={c.name ?? "Unnamed customer"}
                subtitle={`${phone(c.phone ?? c.user_id)} · ${jobs}${c.needs_human || c.attention ? " · Needs you" : ""}`}
                value={last && t != null ? money(t, last.currency) : "No price yet"}
                onPress={() => nav.navigate("QuoteDetail", { userId: c.user_id, name: c.name ?? "Customer" })}
              />
            );
          })}
        </Group>
      )}
    </Screen>
  );
}
