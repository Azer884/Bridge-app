import { createContext, useContext } from "react";
import type { HubUser } from "@shared/api";

/** The person acting in the dashboard. Their role is sent with every request and enforced by the backend. */
export interface ActorState {
  users: HubUser[];
  me: HubUser | null;
  choose: (id: string) => void;
}

export const ActorContext = createContext<ActorState>({ users: [], me: null, choose: () => {} });
export const useActor = () => useContext(ActorContext);

export const canDecide = (me: HubUser | null) => !me || me.module_role === "admin" || me.module_role === "approver";
