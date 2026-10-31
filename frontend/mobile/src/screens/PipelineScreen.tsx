import { useCallback, useMemo, useState } from "react";
import { ScrollView, View } from "react-native";
import { useFocusEffect, useNavigation } from "@react-navigation/native";
import { api, explainError } from "../../../shared/api";
import { money, phone, timeAgo } from "../../../shared/format";
import { STAGES } from "../../../shared/params";
import type { PipelineRow, Stage } from "../../../shared/types";
import { useAsync } from "../hooks";
import { AuditList } from "../quote/AuditList";
import { C, useTheme } from "../theme";
import { Banner, Chip, Empty, Group, Pill, Row, Screen, Segmented, T } from "../ui";

type View_ = "list" | "board";
const STAGE_DOT: Record<Stage, string> = { pending_extraction: "#6B8290", requires_approval: "#E9B949", quote_sent: "#3FB5C8", scheduled: "#1C8F63", completed: "#6B8290", rejected: "#C0392B" };

export default function PipelineScreen() {
  useTheme();
  const nav = useNavigation<any>();
  const rows = useAsync(() => api.listPipeline(), [], 20_000);
  const activity = useAsync(() => api.listActivity(12), [], 20_000);
  const [stage, setStage] = useState<Stage | "all">("all");
  const [view, setView] = useState<View_>("list");
  const [refreshing, setRefreshing] = useState(false);

  useFocusEffect(useCallback(() => { void rows.reload(); void activity.reload(); }, [rows.reload, activity.reload]));

  const all = rows.data ?? [];
  const counts = useMemo(() => Object.fromEntries(STAGES.map((s) => [s.id, all.filter((r) => r.stage === s.id).length])) as Record<Stage, number>, [all]);
  const shown = (stage === "all" ? all : all.filter((r) => r.stage === stage)).slice().sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""));

  const open = (r: PipelineRow) => nav.navigate("QuoteDetail", { userId: r.user_id, name: r.job.name });
  const total = (r: PipelineRow) => (r.quote?.total != null ? money(r.quote.total, r.quote.currency) : "No price yet");
  const rowOf = (r: PipelineRow) => (
    <Row
      key={r.user_id}
      title={r.job.name ?? phone(r.user_id)}
      subtitle={r.job.surfaces ?? "Not given"}
      right={<View style={{ alignItems: "flex-end", gap: 2 }}><T v="headline">{total(r)}</T><Pill status={r.stage} /></View>}
      onPress={() => open(r)}
    />
  );

  return (
    <Screen onRefresh={async () => { setRefreshing(true); await Promise.all([rows.reload(), activity.reload()]); setRefreshing(false); }} refreshing={refreshing}>
      <T v="sub">Every job from first message to done. Open one to review it.</T>
      <Segmented value={view} onChange={setView} options={[{ id: "list", label: "List" }, { id: "board", label: "Board" }]} />
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }} style={{ flexGrow: 0 }}>
        <Chip label="All" count={all.length} on={stage === "all"} onPress={() => setStage("all")} />
        {STAGES.map((s) => <Chip key={s.id} label={s.label} count={counts[s.id] ?? 0} on={stage === s.id} onPress={() => setStage(s.id)} />)}
      </ScrollView>

      {rows.error != null && !rows.data && <Banner text={explainError(rows.error)} action="Try again" onAction={rows.reload} />}
      {rows.loading && !rows.data ? <Empty icon="hourglass-outline" title="Loading pipeline" /> : null}
      {rows.data && shown.length === 0 ? <Empty title="No jobs in this stage" text="Pick another stage to see more." /> : null}

      {view === "list" && shown.length > 0 && <Group>{shown.map(rowOf)}</Group>}

      {view === "board" && rows.data && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 12 }} style={{ marginHorizontal: -16 }} contentInset={{ left: 16, right: 16 }}>
          <View style={{ width: 4 }} />
          {STAGES.filter((s) => stage === "all" || s.id === stage).map((s) => {
            const col = shown.filter((r) => r.stage === s.id);
            return (
              <View key={s.id} style={{ width: 280, gap: 8 }}>
                <View style={{ flexDirection: "row", alignItems: "center", gap: 8, paddingHorizontal: 4 }}>
                  <View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: STAGE_DOT[s.id] }} />
                  <T v="headline">{s.label}</T>
                  <T v="sub">{col.length}</T>
                </View>
                {col.length === 0 ? <T v="foot" style={{ paddingHorizontal: 4 }}>None</T> : (
                  <Group>
                    {col.map((r) => (
                      <Row key={r.user_id} title={r.job.name ?? phone(r.user_id)} subtitle={`${r.job.surfaces ?? "Not given"} · ${timeAgo(r.updated_at) || "new"}`} right={<T v="sub">{total(r)}</T>} onPress={() => open(r)} />
                    ))}
                  </Group>
                )}
              </View>
            );
          })}
          <View style={{ width: 4 }} />
        </ScrollView>
      )}

      <View style={{ gap: 6 }}>
        <T v="label" style={{ paddingHorizontal: 16, color: C.ink3 }}>Recent activity</T>
        {activity.data ? <AuditList entries={activity.data} showCustomer /> : <T v="sub" style={{ paddingHorizontal: 16 }}>Loading…</T>}
      </View>
    </Screen>
  );
}
