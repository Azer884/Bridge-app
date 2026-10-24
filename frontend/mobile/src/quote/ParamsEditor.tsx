import { useState } from "react";
import { Pressable, TextInput, View } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { showValue } from "../../../shared/params";
import type { ExtractedParams, ParamField, ParamValue } from "../../../shared/types";
import { C, F } from "../theme";
import { Group, Row, Sheet, T, tap } from "../ui";

const LOW = 0.7;

interface Props {
  params: ExtractedParams;
  values: Record<string, ParamValue>;
  errors: Record<string, string>;
  readOnly: boolean;
  onChange: (key: string, value: ParamValue) => void;
  onReset: (key: string) => void;
}

/** Fields come from the backend schema, so any trade works. Gesir's value stays visible next to yours. */
export function ParamsEditor({ params, values, errors, readOnly, onChange, onReset }: Props) {
  const [raw, setRaw] = useState<Record<string, string>>(() =>
    Object.fromEntries(params.schema.filter((f) => f.type === "number").map((f) => [f.key, values[f.key] == null ? "" : String(values[f.key])])),
  );
  const [pick, setPick] = useState<ParamField | null>(null);

  return (
    <>
      <Group>
        {params.schema.map((f) => {
          const v = values[f.key];
          const ai = params.ai[f.key];
          const changed = v !== ai && !(ai == null && v == null);
          const waiting = ai == null && v == null;
          const conf = params.confidence[f.key];
          const low = conf != null && conf < LOW && !changed;
          const err = errors[f.key];

          const notes = (
            <View style={{ gap: 4 }}>
              {err ? <T v="foot" style={{ color: C.dangerInk, fontWeight: "600" }}>{err}</T> : null}
              {!err && f.help ? <T v="foot">{f.help}</T> : null}
              {!readOnly && low ? <T v="foot" style={{ color: C.ink2 }}>Gesir is not sure ({Math.round(conf * 100)}%). Check the photos.</T> : null}
              {!readOnly && changed && !waiting ? (
                <Pressable
                  accessibilityRole="button"
                  hitSlop={8}
                  onPress={() => {
                    tap();
                    onReset(f.key);
                    if (f.type === "number") setRaw((r) => ({ ...r, [f.key]: ai == null ? "" : String(ai) }));
                  }}
                >
                  <T v="foot" style={{ color: C.ink2 }}>Gesir read: {showValue(f, ai)}. <T v="foot" style={{ color: C.blue, fontWeight: "600" }}>Use Gesir's value</T></T>
                </Pressable>
              ) : null}
            </View>
          );

          const tint = err ? C.dangerWash : changed && !waiting && !readOnly ? C.tapeWash : undefined;
          const hasNotes = !!err || !!f.help || (!readOnly && low) || (!readOnly && changed && !waiting);
          const wrap = (node: React.ReactNode) => (
            <View key={f.key} style={{ backgroundColor: tint }}>
              {node}
              {hasNotes ? <View style={{ paddingHorizontal: 16, paddingBottom: 10, marginTop: -4 }}>{notes}</View> : null}
            </View>
          );

          if (readOnly) return wrap(<Row title={f.label} value={showValue(f, v)} />);

          if (f.type === "select") {
            return wrap(
              <Row
                title={f.label}
                value={v == null ? "Waiting for customer" : showValue(f, v)}
                onPress={() => setPick(f)}
              />,
            );
          }
          return wrap(
            <Row
              title={f.label}
              right={
                <View style={{ flexDirection: "row", alignItems: "center", gap: 6 }}>
                  <TextInput
                    accessibilityLabel={`${f.label}${f.unit ? ` in ${f.unit}` : ""}`}
                    keyboardType="decimal-pad"
                    placeholder={waiting ? "Waiting" : ""}
                    placeholderTextColor={C.ink3}
                    value={raw[f.key] ?? ""}
                    onChangeText={(t) => {
                      const c = t.replace(/[^0-9.]/g, "");
                      setRaw((r) => ({ ...r, [f.key]: c }));
                      onChange(f.key, c === "" || Number.isNaN(Number(c)) ? null : Number(c));
                    }}
                    style={{ width: 84, minHeight: 44, textAlign: "right", fontFamily: F.sys, fontSize: 17, color: C.ink }}
                  />
                  {f.unit ? <T v="sub" style={{ minWidth: 28 }}>{f.unit}</T> : null}
                </View>
              }
            />,
          );
        })}
      </Group>

      <Sheet visible={pick != null} title={pick?.label ?? ""} onClose={() => setPick(null)}>
        <Group>
          {(pick?.options ?? []).map((o) => (
            <Row
              key={o.value}
              title={o.label}
              chevron={false}
              right={values[pick!.key] === o.value ? <Ionicons name="checkmark" size={22} color={C.blue} /> : undefined}
              onPress={() => { onChange(pick!.key, o.value); setPick(null); }}
            />
          ))}
        </Group>
      </Sheet>
    </>
  );
}


