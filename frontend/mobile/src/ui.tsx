import { Children, Fragment, isValidElement, type ReactNode } from "react";
import {
  ActivityIndicator,
  Modal,
  Platform,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextInputProps,
  type TextStyle,
  type ViewStyle,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import * as Haptics from "expo-haptics";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { C, F, onThemeApplied, useTheme } from "./theme";

export type IconName = keyof typeof Ionicons.glyphMap;

type Variant = "large" | "title" | "headline" | "body" | "sub" | "foot" | "label" | "money";
const buildText = (): Record<Variant, TextStyle> => ({
  large: { fontFamily: F.display, fontSize: 40, lineHeight: 42, color: C.ink },
  title: { fontFamily: F.display, fontSize: 26, lineHeight: 30, color: C.ink },
  headline: { fontFamily: F.semi, fontSize: 17, lineHeight: 22, color: C.ink },
  body: { fontFamily: F.sys, fontSize: 17, lineHeight: 22, color: C.ink },
  sub: { fontFamily: F.sys, fontSize: 15, lineHeight: 20, color: C.ink2 },
  foot: { fontFamily: F.sys, fontSize: 13, lineHeight: 18, color: C.ink3 },
  label: { fontFamily: F.semi, fontSize: 13, lineHeight: 18, color: C.ink3 },
  money: { fontFamily: F.display, fontSize: 22, lineHeight: 26, color: C.ink },
});
let TEXT = buildText();

export function T({ v = "body", style, children, ...rest }: { v?: Variant; style?: StyleProp<TextStyle>; children: ReactNode } & React.ComponentProps<typeof Text>) {
  return (
    <Text {...rest} style={[TEXT[v], style]}>
      {children}
    </Text>
  );
}

export const tap = () => Haptics.selectionAsync().catch(() => {});
export const success = () => Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});

/** Scrolling grouped screen. The native stack header supplies the large title. */
export function Screen({ children, onRefresh, refreshing, footer, gap = 22 }: { children: ReactNode; onRefresh?: () => void; refreshing?: boolean; footer?: ReactNode; gap?: number }) {
  useTheme();
  const inset = useSafeAreaInsets();
  return (
    <View style={{ flex: 1, backgroundColor: C.wall }}>
      <ScrollView
        contentInsetAdjustmentBehavior="automatic"
        keyboardShouldPersistTaps="handled"
        contentContainerStyle={{ padding: 16, gap, paddingBottom: footer ? 24 : inset.bottom + 24 }}
        refreshControl={onRefresh ? <RefreshControl refreshing={!!refreshing} onRefresh={onRefresh} tintColor={C.ink3} /> : undefined}
      >
        {children}
      </ScrollView>
      {footer ? <View style={[s.footer, { paddingBottom: Math.max(inset.bottom, 12) }]}>{footer}</View> : null}
    </View>
  );
}

/** Inset grouped section: rounded card of rows with hairline separators. */
export function Group({ title, footer, children, style }: { title?: string; footer?: string; children: ReactNode; style?: StyleProp<ViewStyle> }) {
  const kids = Children.toArray(children).filter(Boolean);
  return (
    <View style={{ gap: 6 }}>
      {title ? <T v="label" style={{ paddingHorizontal: 16 }}>{title}</T> : null}
      <View style={[s.group, style]}>
        {kids.map((k, i) => (
          <Fragment key={isValidElement(k) && k.key != null ? String(k.key) : i}>
            {i > 0 ? <View style={s.sep} /> : null}
            {k}
          </Fragment>
        ))}
      </View>
      {footer ? <T v="foot" style={{ paddingHorizontal: 16 }}>{footer}</T> : null}
    </View>
  );
}

export function Row({ title, subtitle, value, onPress, chevron, left, right, destructive, tint }: {
  title: ReactNode; subtitle?: ReactNode; value?: string; onPress?: () => void; chevron?: boolean; left?: ReactNode; right?: ReactNode; destructive?: boolean; tint?: string;
}) {
  const inner = (
    <View style={s.row}>
      {left}
      <View style={{ flex: 1, gap: 2 }}>
        {typeof title === "string" ? <T style={destructive ? { color: C.danger } : tint ? { color: tint } : undefined}>{title}</T> : title}
        {subtitle ? (typeof subtitle === "string" ? <T v="foot">{subtitle}</T> : subtitle) : null}
      </View>
      {value ? <T v="sub" numberOfLines={2} style={{ maxWidth: "55%", textAlign: "right" }}>{value}</T> : null}
      {right}
      {chevron || (onPress && chevron !== false) ? <Ionicons name="chevron-forward" size={18} color={C.ink3} /> : null}
    </View>
  );
  if (!onPress) return inner;
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => ({ backgroundColor: pressed ? C.field : "transparent" })}>
      {inner}
    </Pressable>
  );
}

export function Icon({ name, color, size = 22 }: { name: IconName; color?: string; size?: number }) {
  return <Ionicons name={name} size={size} color={color ?? C.blue} />;
}

export function ThemeButton() {
  const { mode, toggle } = useTheme();
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`Switch to ${mode === "dark" ? "light" : "dark"} mode`}
      onPress={() => { tap(); toggle(); }}
      hitSlop={10}
      style={{ width: 44, height: 44, alignItems: "center", justifyContent: "center" }}
    >
      <Ionicons name={mode === "dark" ? "sunny-outline" : "moon-outline"} size={22} color={C.blue} />
    </Pressable>
  );
}

type BtnKind = "primary" | "tinted" | "plain" | "danger";
export function Btn({ label, onPress, kind = "primary", disabled, busy, small, icon }: { label: string; onPress: () => void; kind?: BtnKind; disabled?: boolean; busy?: boolean; small?: boolean; icon?: IconName }) {
  const bg = kind === "primary" ? C.blue : kind === "tinted" ? C.blueWash : kind === "danger" ? C.dangerWash : "transparent";
  const fg = kind === "primary" ? C.white : kind === "danger" ? C.dangerInk : C.blue;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !!(disabled || busy), busy: !!busy }}
      disabled={disabled || busy}
      onPress={() => { tap(); onPress(); }}
      style={({ pressed }) => [s.btn, { backgroundColor: bg, minHeight: small ? 40 : 52, opacity: disabled ? 0.4 : pressed ? 0.75 : 1 }]}
    >
      {busy ? <ActivityIndicator color={fg} /> : (
        <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
          {icon ? <Ionicons name={icon} size={small ? 18 : 20} color={fg} /> : null}
          <Text style={{ fontFamily: F.semi, fontSize: small ? 15 : 17, color: fg }}>{label}</Text>
        </View>
      )}
    </Pressable>
  );
}

export function Chip({ label, on, onPress, count }: { label: string; on?: boolean; onPress: () => void; count?: number }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected: !!on }}
      onPress={() => { tap(); onPress(); }}
      style={[s.chip, on && { backgroundColor: C.ink, borderColor: C.ink }]}
    >
      <Text style={{ fontFamily: F.semi, fontSize: 15, color: on ? C.wall : C.ink2 }}>
        {label}{count != null ? `  ${count}` : ""}
      </Text>
    </Pressable>
  );
}

export function Segmented<K extends string>({ value, options, onChange }: { value: K; options: { id: K; label: string }[]; onChange: (k: K) => void }) {
  return (
    <View style={s.seg} accessibilityRole="tablist">
      {options.map((o) => (
        <Pressable key={o.id} accessibilityRole="tab" accessibilityState={{ selected: value === o.id }} onPress={() => { tap(); onChange(o.id); }} style={[s.segItem, value === o.id && { backgroundColor: C.paper }]}>
          <Text numberOfLines={1} style={{ fontFamily: value === o.id ? F.semi : F.medium, fontSize: 14, color: value === o.id ? C.ink : C.ink2 }}>{o.label}</Text>
        </Pressable>
      ))}
    </View>
  );
}

export function Banner({ kind = "danger", text, action, onAction }: { kind?: "danger" | "info" | "warn"; text: string; action?: string; onAction?: () => void }) {
  const bg = kind === "danger" ? C.dangerWash : kind === "info" ? C.blueWash : C.tapeWash;
  const bar = kind === "danger" ? C.danger : kind === "info" ? C.blue : C.tape;
  return (
    <View accessibilityRole={kind === "danger" ? "alert" : undefined} style={{ backgroundColor: bg, borderLeftWidth: 4, borderLeftColor: bar, borderRadius: 12, padding: 12, gap: 8 }}>
      <T v="sub" style={{ color: C.ink }}>{text}</T>
      {action && onAction ? <Btn small kind="plain" label={action} onPress={onAction} /> : null}
    </View>
  );
}

const pills = (): Record<string, { bg: string; fg: string; label: string }> => ({
  collecting: { bg: C.chip, fg: C.ink2, label: "Collecting details" },
  pending_approval: { bg: C.tapeWash, fg: C.ink, label: "Needs your OK" },
  approved: { bg: C.okWash, fg: C.okInk, label: "Sent" },
  needs_inspection: { bg: C.dangerWash, fg: C.dangerInk, label: "Needs inspection" },
  completed: { bg: C.chip, fg: C.ink2, label: "Completed" },
  tentative: { bg: C.tapeWash, fg: C.ink, label: "Tentative" },
  confirmed: { bg: C.okWash, fg: C.okInk, label: "Confirmed" },
  cancelled: { bg: C.chip, fg: C.ink2, label: "Cancelled" },
  none: { bg: C.chip, fg: C.ink2, label: "No quote" },
  pending_extraction: { bg: C.chip, fg: C.ink2, label: "Pending AI extraction" },
  requires_approval: { bg: C.tapeWash, fg: C.ink, label: "Needs your approval" },
  quote_sent: { bg: C.blueWash, fg: C.ink, label: "Quote sent" },
  scheduled: { bg: C.okWash, fg: C.okInk, label: "Scheduled" },
});
export function Pill({ status, label }: { status: string; label?: string }) {
  const p = pills()[status] ?? { bg: C.chip, fg: C.ink2, label: status };
  return (
    <View style={{ backgroundColor: p.bg, borderRadius: 99, paddingHorizontal: 10, paddingVertical: 3, alignSelf: "flex-start" }}>
      <Text style={{ fontFamily: F.semi, fontSize: 12, color: p.fg }}>{label ?? p.label}</Text>
    </View>
  );
}

export function Empty({ title, text, icon = "file-tray-outline" }: { title: string; text?: string; icon?: IconName }) {
  return (
    <View style={{ alignItems: "center", paddingVertical: 40, paddingHorizontal: 24, gap: 8 }}>
      <Ionicons name={icon} size={36} color={C.ink3} />
      <T v="headline">{title}</T>
      {text ? <T v="sub" style={{ textAlign: "center" }}>{text}</T> : null}
    </View>
  );
}

export function Field({ label, hint, counter, ...input }: { label: string; hint?: string; counter?: { len: number; max: number } } & TextInputProps) {
  const over = counter && counter.len > counter.max;
  return (
    <View style={{ gap: 6 }}>
      <T v="label" style={{ color: C.ink }}>{label}</T>
      <TextInput
        accessibilityLabel={label}
        placeholderTextColor={C.ink3}
        {...input}
        style={[s.input, input.multiline && { minHeight: 96, textAlignVertical: "top", paddingTop: 12 }, over && { borderColor: C.danger }]}
      />
      {hint ? <T v="foot">{hint}</T> : null}
      {counter ? <T v="foot" style={{ textAlign: "right", color: over ? C.danger : C.ink3 }}>{counter.len} / {counter.max}</T> : null}
    </View>
  );
}

/** iOS: a native page sheet with grabber and swipe to dismiss. Elsewhere: a bottom sheet. */
export function Sheet({ visible, title, onClose, children, action }: { visible: boolean; title: string; onClose: () => void; children: ReactNode; action?: ReactNode }) {
  useTheme();
  const inset = useSafeAreaInsets();
  const body = (
    <>
      <View style={s.sheetHead}>
        <Pressable accessibilityRole="button" onPress={onClose} hitSlop={10} style={{ minWidth: 60 }}>
          <T style={{ color: C.blue }}>Close</T>
        </Pressable>
        <T v="headline" numberOfLines={1} style={{ flex: 1, textAlign: "center" }}>{title}</T>
        <View style={{ minWidth: 60, alignItems: "flex-end" }}>{action}</View>
      </View>
      <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 16, gap: 18, paddingBottom: inset.bottom + 24 }}>{children}</ScrollView>
    </>
  );
  if (Platform.OS === "ios") {
    return (
      <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}>
        <View style={{ flex: 1, backgroundColor: C.wall }}>{body}</View>
      </Modal>
    );
  }
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel="Close" />
      <View style={[s.sheet, { backgroundColor: C.wall }]}>
        <View style={s.grabber} />
        {body}
      </View>
    </Modal>
  );
}

const buildStyles = () =>
  StyleSheet.create({
    group: { backgroundColor: C.paper, borderRadius: 16, overflow: "hidden" },
    sep: { height: StyleSheet.hairlineWidth, backgroundColor: C.line, marginLeft: 16 },
    row: { minHeight: 48, paddingVertical: 11, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 12 },
    btn: { borderRadius: 999, paddingHorizontal: 22, alignItems: "center", justifyContent: "center" },
    chip: { borderWidth: 1, borderColor: C.line, borderRadius: 99, paddingHorizontal: 14, minHeight: 40, justifyContent: "center", backgroundColor: C.paper },
    seg: { flexDirection: "row", backgroundColor: C.chip, borderRadius: 10, padding: 2 },
    segItem: { flex: 1, minHeight: 36, alignItems: "center", justifyContent: "center", borderRadius: 8, paddingHorizontal: 8 },
    input: { backgroundColor: C.paper, borderWidth: 1, borderColor: C.line, borderRadius: 12, paddingHorizontal: 14, paddingVertical: 10, minHeight: 48, fontFamily: F.sys, fontSize: 17, color: C.ink },
    scrim: { flex: 1, backgroundColor: "rgba(4,27,45,0.5)" },
    sheet: { borderTopLeftRadius: 22, borderTopRightRadius: 22, maxHeight: "90%", paddingTop: 8 },
    grabber: { alignSelf: "center", width: 36, height: 5, borderRadius: 3, backgroundColor: C.line, marginBottom: 4 },
    sheetHead: { flexDirection: "row", alignItems: "center", paddingHorizontal: 16, paddingVertical: 12, gap: 8 },
    footer: { paddingHorizontal: 16, paddingTop: 12, backgroundColor: C.paper, borderTopWidth: StyleSheet.hairlineWidth, borderTopColor: C.line },
  });
export let s = buildStyles();
onThemeApplied(() => {
  TEXT = buildText();
  s = buildStyles();
});

