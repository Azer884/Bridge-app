import { useCallback, useEffect, useRef, useState } from "react";
import { Pressable, View } from "react-native";
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { api, explainError } from "../../../shared/api";
import { money, timeAgo } from "../../../shared/format";
import type { QuoteItem } from "../../../shared/types";
import { useActor } from "../actor";
import { useAsync } from "../hooks";
import { enableNotifications, pushState, type PushState } from "../push";
import { C, useTheme } from "../theme";
import { Banner, Btn, Empty, Pill, T, Screen, success } from "../ui";

const greeting = (h: number) => (h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening");

/** What needs a person right now. This is the app's main screen: a quote arrives, the owner reviews it, approves or rejects. */
export default function ApproveScreen() {
  useTheme();
  const nav = useNavigation<any>();
  const { me, canDecide } = useActor();
  const { data, error, loading, reload } = useAsync(
    async () => [...(await api.listQuotes("pending_approval")), ...(await api.listQuotes("needs_inspection"))],
    [me?.id],
    10_000,
  );
  const [refreshing, setRefreshing] = useState(false);
  const [push, setPush] = useState<PushState>("unsupported");
  const seen = useRef<number | null>(null);

  useFocusEffect(useCallback(() => { void reload(); void pushState().then(setPush); }, [reload]));

  const items = data ?? [];
  // Buzz in the hand when a new quote arrives while the app is open.
  useEffect(() => {
    if (!data) return;
    if (seen.current != null && items.length > seen.current) success();
    seen.current = items.length;
  }, [items.length, data]);

  const open = (q: QuoteItem) => nav.navigate("QuoteDetail", { userId: q.user_id, name: q.job.name });
  const first = (me?.name ?? "").split(" ")[0];

  return (
    <Screen onRefresh={async () => { setRefreshing(true); await reload(); setRefreshing(false); }} refreshing={refreshing}>
      <View style={{ gap: 4 }}>
        <T v="title">{greeting(new Date().getHours())}{first ? `, ${first}` : ""}</T>
        <T v="sub">
          {items.length === 0 ? "Nothing needs you right now." : `${items.length} ${items.length === 1 ? "quote needs" : "quotes need"} your decision. Customers only see the total once you approve.`}
        </T>
      </View>

      {push === "off" || push === "denied" ? (
        <View style={{ backgroundColor: C.blueWash, borderRadius: 14, padding: 14, gap: 10 }}>
          <T v="headline">Get a notification for each new quote</T>
          <T v="sub">{push === "denied" ? "Notifications are blocked. Turn them on in your phone's settings." : "So you can approve while you are on the job, without opening the app."}</T>
          {push === "off" ? <Btn small label="Turn on notifications" onPress={async () => setPush(await enableNotifications())} /> : null}
        </View>
      ) : null}
      {!canDecide ? <Banner kind="info" text="You can read quotes but not approve them. Ask an approver, or switch role in More." /> : null}
      {error != null && !data ? <Banner text={explainError(error)} action="Try again" onAction={reload} /> : null}
      {loading && !data ? <Empty icon="hourglass-outline" title="Loading" /> : null}
      {data && items.length === 0 ? <Empty icon="checkmark-circle-outline" title="You are all caught up" text="New quotes appear here the moment a customer finishes chatting." /> : null}

      {items.map((q) => (
        <Pressable
          key={q.user_id}
          accessibilityRole="button"
          accessibilityLabel={`Review the estimate for ${q.customer}`}
          onPress={() => open(q)}
          style={({ pressed }) => ({ backgroundColor: C.paper, borderRadius: 16, borderWidth: 1, borderColor: C.line, padding: 16, gap: 10, opacity: pressed ? 0.85 : 1 })}
        >
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 12 }}>
            <View style={{ flex: 1, gap: 2 }}>
              <T v="headline">{q.job.name ?? q.customer}</T>
              <T v="foot" numberOfLines={2}>{q.job.address ?? "No address yet"}</T>
            </View>
            {q.status === "needs_inspection" ? <Pill status="needs_inspection" label="Visit first" /> : null}
          </View>
          <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "flex-end" }}>
            <View>
              <T v="foot">{q.status === "needs_inspection" ? "No price yet" : "Estimate"}</T>
              {q.quote ? <T v="money">{money(q.quote.total, q.quote.currency)}</T> : null}
            </View>
            <T v="foot">{timeAgo(q.updated_at)}</T>
          </View>
          <Btn label={canDecide ? "Review and approve" : "Open"} onPress={() => open(q)} />
        </Pressable>
      ))}
    </Screen>
  );
}