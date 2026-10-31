import { createContext, createElement, useContext, useEffect, useState, type ReactNode } from "react";
import { Appearance, Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

export type Mode = "light" | "dark";
export type Pref = "system" | Mode;

const LIGHT = {
  wall: "#F4F8FF",
  paper: "#FFFFFF",
  field: "#EDF2FA",
  ink: "#1C3153",
  ink2: "#3D5073",
  ink3: "#6B7A93",
  line: "#DBE2EE",
  blue: "#0767E8",
  blueWash: "#E5F0FF",
  tape: "#E9B949",
  tapeWash: "#FAEFCB",
  danger: "#C93A24",
  dangerWash: "#F6DCD6",
  ok: "#1C8F63",
  okWash: "#D5F0E2",
  chip: "#E8EEF8",
  okInk: "#0F5C3B",
  dangerInk: "#8E2412",
  side: "#1C3153",
  white: "#FFFFFF",
};

const DARK: typeof LIGHT = {
  wall: "#0B1426",
  paper: "#131F36",
  field: "#0F1A2F",
  ink: "#E8EEF9",
  ink2: "#B5C3DB",
  ink3: "#8A9BB8",
  line: "#243553",
  blue: "#4C9BFF",
  blueWash: "#14305C",
  tape: "#E9B949",
  tapeWash: "#3A3217",
  danger: "#E5604B",
  dangerWash: "#3A1D19",
  ok: "#3FBF8A",
  okWash: "#12372B",
  chip: "#1A2A47",
  okInk: "#7BE0B2",
  dangerInk: "#F2A698",
  side: "#060D1B",
  white: "#FFFFFF",
};

/** Mutated in place when the theme changes. Screens call useTheme() so they re-render and read the new values. */
export const C = { ...LIGHT };



/** Public Sans throughout, like the Orbyte web dashboard. Heavier weight for titles and amounts. */
export const F = {
  sys: "PublicSans_400Regular",
  medium: "PublicSans_500Medium",
  semi: "PublicSans_600SemiBold",
  bold: "PublicSans_700Bold",
  display: "PublicSans_800ExtraBold",
};

export const BREAKDOWN = ["#0767E8", "#1C8F63", "#1C3153", "#4C9BFF", "#E9B949", "#6B7A93"];

export const STATUS_COLOR: Record<string, string> = {
  pending_approval: "#E9B949",
  approved: "#1C8F63",
  needs_inspection: "#C93A24",
  rejected: "#C93A24",
  collecting: "#6B8290",
  completed: "#6B8290",
};

const listeners = new Set<() => void>();
export const onThemeApplied = (f: () => void) => void listeners.add(f);

export function applyTheme(mode: Mode) {
  Object.assign(C, mode === "dark" ? DARK : LIGHT);
  listeners.forEach((f) => f());
}

const KEY = "gesir.theme";
const Ctx = createContext<{ mode: Mode; pref: Pref; setPref: (p: Pref) => void; toggle: () => void }>({
  mode: "light",
  pref: "light",
  setPref: () => {},
  toggle: () => {},
});
export const useTheme = () => useContext(Ctx);

const systemMode = (): Mode => (Appearance.getColorScheme() === "dark" ? "dark" : "light");

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<Pref>("light"); // Orbyte is a light interface
  const [sys, setSys] = useState<Mode>(systemMode());
  const mode: Mode = pref === "system" ? sys : pref;
  applyTheme(mode); // before children render, so they read the right values

  useEffect(() => {
    AsyncStorage.getItem(KEY)
      .then((v) => {
        if (v === "light" || v === "dark" || v === "system") setPrefState(v);
      })
      .catch(() => {});
    const sub = Appearance.addChangeListener(() => setSys(systemMode()));
    return () => sub.remove();
  }, []);

  const setPref = (p: Pref) => {
    setPrefState(p);
    AsyncStorage.setItem(KEY, p).catch(() => {});
  };
  const toggle = () => setPref(mode === "dark" ? "light" : "dark");

  return createElement(Ctx.Provider, { value: { mode, pref, setPref, toggle } }, children);
}
