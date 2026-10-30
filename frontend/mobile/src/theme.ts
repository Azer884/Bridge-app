import { createContext, createElement, useContext, useEffect, useState, type ReactNode } from "react";
import { Appearance, Platform } from "react-native";
import AsyncStorage from "@react-native-async-storage/async-storage";

export type Mode = "light" | "dark";
export type Pref = "system" | Mode;

const LIGHT = {
  wall: "#EAF1F1",
  paper: "#FFFFFF",
  field: "#F3F7F7",
  ink: "#041B2D",
  ink2: "#3B5566",
  ink3: "#5F7685",
  line: "#D2DFDF",
  blue: "#0E7C73",
  blueWash: "#D3EBE7",
  tape: "#E9B949",
  tapeWash: "#FAEFCB",
  danger: "#C93A24",
  dangerWash: "#F6DCD6",
  ok: "#1C8F63",
  okWash: "#D5F0E2",
  chip: "#DCE8E8",
  okInk: "#0F5C3B",
  dangerInk: "#8E2412",
  side: "#0A3550",
  white: "#FFFFFF",
};

const DARK: typeof LIGHT = {
  wall: "#061621",
  paper: "#0C2233",
  field: "#0A1C2A",
  ink: "#E7F1F1",
  ink2: "#AAC3CB",
  ink3: "#86A1AD",
  line: "#183A4E",
  blue: "#14A090",
  blueWash: "#0F3A40",
  tape: "#E9B949",
  tapeWash: "#3A3217",
  danger: "#E5604B",
  dangerWash: "#3A1D19",
  ok: "#3FBF8A",
  okWash: "#12372B",
  chip: "#0F2B3D",
  okInk: "#7BE0B2",
  dangerInk: "#F2A698",
  side: "#030D14",
  white: "#FFFFFF",
};

/** Mutated in place when the theme changes. Screens call useTheme() so they re-render and read the new values. */
export const C = { ...LIGHT };



/** Figtree for text and controls, Bricolage Grotesque for large titles and amounts. */
export const F = {
  sys: "Figtree_400Regular",
  medium: "Figtree_500Medium",
  semi: "Figtree_600SemiBold",
  bold: "Figtree_700Bold",
  display: "BricolageGrotesque_700Bold",
};

export const BREAKDOWN = ["#129A8D", "#59C793", "#083C57", "#3FB5C8", "#E9B949", "#6B8290"];

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
  pref: "system",
  setPref: () => {},
  toggle: () => {},
});
export const useTheme = () => useContext(Ctx);

const systemMode = (): Mode => (Appearance.getColorScheme() === "dark" ? "dark" : "light");

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [pref, setPrefState] = useState<Pref>("system");
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
