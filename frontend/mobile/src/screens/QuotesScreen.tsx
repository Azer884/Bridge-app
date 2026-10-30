import { useCallback, useEffect, useRef, useState } from "react";
import { View } from "react-native";
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { explainError } from "../../../shared/api";
import { money, phone, timeAgo } from "../../../shared/format";
import type { QuoteStatus } from "../../../shared/types";
import { loadAllQuotes } from "../data";
import { useAsync } from "../hooks";
import { STATUS_COLOR, useTheme } from "../theme";
import { Banner, Empty, Group, Row, Screen, Segmented, T, success } from "../ui";

const TABS: { id: QuoteStatus; label: string }[] = [
  { id: "pending_approval", label: "Needs OK" },
  { id: "approved", label: "Approved" },
  { id: "needs_inspection", label: "Inspect" },
  { id: "rejected", label: "Rejected" },
];

export default function QuotesScreen() {
  useTheme();
  const nav = useNavigation<any>();
  const [tab, setTab] = useState<QuoteStatus>("pending_approval");
  const { data, error, loading, reload } = useAsync(loadAllQuotes, [], 15_000);
  const [refreshing, setRefreshing] = useState(false);
  const seen = useRef<number | null>(null);

  useFocusEffect(useCallback(() => { void reload(); }, [reload]));

  const items = data ?? [];
  const pending = items.filter((q) => q.status === "pending_approval").length;

  // No push yet: polling stands in. Buzz when a new draft arrives.
  useEffect(() => {
    if (!data) return;
    if (seen.current != null && pending > seen.current) success();
    seen.current = pending;
  }, [pending, data]);

  const visible = items.filter((q) => q.status === tab);
  const count = (id: QuoteStatus) => items.filter((q) => q.status === id).length;

  return (
    <Screen onRefresh={async () => { setRefreshing(true); await reload(); setRefreshing(false); }} refreshing={refreshing}>
      <T v="sub">Gesir drafted these on your behalf. Nothing goes to a customer until you approve, and they only see the total.</T>
      <Segmented value={tab} onChange={setTab} options={TABS.map((t) => ({ id: t.id, label: `${t.label} ${count(t.id)}` }))} />
      {error != null && !data && <Banner text={explainError(error)} action="Try again" onAction={reload} />}
      {loading && !data ? <Empty icon="hourglass-outline" title="Loading quotes" /> : null}
      {data && visible.length === 0 ? (
        <Empty icon="checkmark-circle-outline" title={tab === "pending_approval" ? "Nothing waiting" : "Nothing here yet"} text={tab === "pending_approval" ? "New drafts show up as customers finish their chat." : "Quotes appear here after you act on them."} />
      ) : null}
      {visible.length > 0 && (
        <Group>
          {visible.map((q) => (
            <Row
              key={q.user_id}
              left={<View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: STATUS_COLOR[q.status] }} />}
              title={q.job.name ?? phone(q.job.phone ?? q.user_id)}
              subtitle={q.job.address ?? "No address yet"}
              right={
                <View style={{ alignItems: "flex-end" }}>
                  <T v="headline">{q.quote?.total != null ? money(q.quote.total, q.quote.currency) : "Inspect"}</T>
                  <T v="foot">{timeAgo(q.updated_at)}</T>
                </View>
              }
              onPress={() => nav.navigate("QuoteDetail", { userId: q.user_id, name: q.job.name })}
            />
          ))}
        </Group>
      )}
      <T v="foot" style={{ textAlign: "center" }}>Pull down to refresh. Updates every 15 seconds.</T>
    </Screen>
  );
}
