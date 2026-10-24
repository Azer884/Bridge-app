import { useEffect, useState } from "react";
import { Switch, View } from "react-native";
import { api, apiMode, explainError } from "../../../shared/api";
import { timeAgo } from "../../../shared/format";
import { useAsync } from "../hooks";
import { C, useTheme } from "../theme";
import { Banner, Empty, Group, Row, Screen, T } from "../ui";

const ORB = { ready: "#59C793", waking: "#E9B949", down: "#EF6B55" } as const;

export default function StatusScreen() {
  useTheme();
  const health = useAsync(() => api.modelHealth(), [], 5_000);
  const events = useAsync(() => api.listEvents(50), [], 10_000);
  const [onlyFailed, setOnlyFailed] = useState(false);
  const [waited, setWaited] = useState(0);
  const state = health.data?.state;

  useEffect(() => {
    if (state !== "waking") { setWaited(0); return; }
    const id = setInterval(() => setWaited((w) => w + 1), 1000);
    return () => clearInterval(id);
  }, [state]);

  const mm = `${Math.floor(waited / 60)}:${String(waited % 60).padStart(2, "0")}`;
  const list = (events.data ?? []).filter((e) => !onlyFailed || !e.ok);

  return (
    <Screen onRefresh={async () => { await Promise.all([health.reload(), events.reload()]); }}>
      <T v="sub">{apiMode() === "mock" ? "Showing sample data." : "Connected to the live backend."} Check this when a customer says nothing came back.</T>

      <Group title="Models">
        <Row
          left={<View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: state ? ORB[state] : C.ink3 }} />}
          title={state === "waking" ? "Waking up" : state === "ready" ? "Ready" : state === "down" ? "Not responding" : "Checking"}
          subtitle={
            health.error != null && !health.data
              ? explainError(health.error)
              : state === "waking"
                ? `Normal after a quiet spell, takes 2 to 5 minutes. Waiting ${mm}. Replies are slow until it finishes.`
                : health.data?.detail
          }
          chevron={false}
        />
      </Group>

      <Group title="Recent events">
        <Row title="Failures only" chevron={false} right={<Switch accessibilityLabel="Failures only" value={onlyFailed} onValueChange={setOnlyFailed} trackColor={{ true: C.blue, false: C.line }} />} />
        {list.map((e, i) => (
          <Row
            key={i}
            left={<View style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: e.ok ? C.ok : C.danger, alignSelf: "flex-start", marginTop: 6 }} />}
            title={e.detail}
            subtitle={`${e.kind} · ${timeAgo(e.ts)}`}
            chevron={false}
          />
        ))}
      </Group>
      {events.error != null && !events.data && <Banner text={explainError(events.error)} />}
      {events.data && list.length === 0 ? <Empty icon="checkmark-circle-outline" title={onlyFailed ? "No failures" : "No events yet"} /> : null}
    </Screen>
  );
}
