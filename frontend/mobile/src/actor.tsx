import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import AsyncStorage from "@react-native-async-storage/async-storage";
import { api, setActor, type HubUser } from "../../shared/api";

const KEY = "gesir_actor";

interface ActorState {
  users: HubUser[];
  me: HubUser | null;
  choose: (id: string) => void;
  /** Approvers and admins decide. Reviewers can only read. The backend enforces it too. */
  canDecide: boolean;
}

const Ctx = createContext<ActorState>({ users: [], me: null, choose: () => {}, canDecide: true });
export const useActor = () => useContext(Ctx);

/** The person using the app. Their role goes with every request (x-orbyte-role), like the web dashboard's role picker. */
export function ActorProvider({ children }: { children: ReactNode }) {
  const [users, setUsers] = useState<HubUser[]>([]);
  const [chosen, setChosen] = useState<string | null>(null);

  useEffect(() => {
    AsyncStorage.getItem(KEY).then((v) => v && setChosen(v)).catch(() => {});
    api.hubUsers().then(setUsers).catch(() => {});
  }, []);

  const me = users.find((u) => u.id === chosen) ?? users.find((u) => u.module_role === "approver") ?? users[0] ?? null;
  setActor(me ? { role: me.module_role, name: me.name } : null);

  const value = useMemo<ActorState>(
    () => ({
      users,
      me,
      choose: (id) => {
        setChosen(id);
        AsyncStorage.setItem(KEY, id).catch(() => {});
      },
      canDecide: !me || me.module_role === "admin" || me.module_role === "approver",
    }),
    [users, me],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}