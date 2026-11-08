import { lazy } from "react";
import { kindOf } from "../auth/roles";
import { useAuth } from "../auth/useAuth";
import { Skeleton } from "../components/ui";
import AppShell from "./AppShell";

const BuyerHome = lazy(() => import("./BuyerHome"));
const Pending = lazy(() => import("./Pending"));

/** After sign-in, shows the right world for the role: buyers get only their contract chat; people with no role yet wait; staff get the app. */
export default function RoleSwitch() {
  const me = useAuth();
  if (me.isLoading) return <div style={{ padding: "6rem 1rem" }}><Skeleton h={240} /></div>; // never mount the staff app (and its contract-list request) before we know who this is
  const kind = kindOf(me.data);
  if (kind === "buyer") return <BuyerHome />;
  if (kind === "pending") return <Pending />;
  return <AppShell />;
}
