import { useMutation, useQuery } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { json, request, type Citation } from "../api/client";
import { Alert, EmptyState, Skeleton } from "../components/ui";

interface Reply {
  answer: string;
  refused: boolean;
  citations: Citation[];
  disclaimer?: string;
}
interface Turn {
  role: "user" | "assistant";
  content: string;
  refused?: boolean;
  citations?: Citation[];
}

/** The buyer's only page: ask questions about their own contract. The server decides which contract; nothing here can change that. */
export default function BuyerHome() {
  const { t } = useTranslation();
  const mine = useQuery({ queryKey: ["buyer-me"], queryFn: () => request<{ linked: boolean; contract_name: string | null }>("/buyer/me"), retry: false });
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const end = useRef<HTMLDivElement>(null);
  const ask = useMutation({
    mutationFn: (message: string) =>
      request<Reply>("/buyer/chat", json({ message, channel: "web", history: turns.slice(-6).map((x) => ({ role: x.role, content: x.content })) })),
    onSuccess: (r) => {
      setTurns((x) => [...x, { role: "assistant", content: r.answer, refused: r.refused, citations: r.citations }]);
      setTimeout(() => end.current?.scrollIntoView?.({ block: "end" }), 0);
    },
  });
  const send = (e: FormEvent) => {
    e.preventDefault();
    const m = text.trim();
    if (!m || ask.isPending) return;
    setTurns((x) => [...x, { role: "user", content: m }]);
    setText("");
    ask.mutate(m);
  };
  if (mine.isLoading) return <div style={{ padding: "6rem 1rem" }}><Skeleton h={240} /></div>;
  if (mine.error) return <div style={{ padding: "6rem 1rem" }}><Alert tone="warn">{(mine.error as Error).message}</Alert></div>;
  if (!mine.data?.linked) {
    return <div style={{ padding: "6rem 1rem", maxWidth: 640, margin: "0 auto" }}><EmptyState title={t("buyerHome.notLinkedTitle")} body={t("buyerHome.notLinkedBody")} /></div>;
  }
  return (
    <div className="data-layer" style={{ maxWidth: 820, margin: "0 auto", padding: "5.2rem 1rem 2rem", display: "grid", gap: "1rem" }} data-testid="buyer-home">
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 6 }}>
        <h1 className="display" style={{ margin: 0, fontSize: "1.5rem" }}>{t("buyerHome.title")}</h1>
        <p style={{ margin: 0, color: "var(--muted)" }}>{t("buyerHome.intro", { name: mine.data.contract_name ?? "" })}</p>
      </section>
      <section className="card" style={{ padding: "1rem", display: "grid", gap: 10 }} aria-live="polite">
        {turns.length === 0 && <p style={{ margin: 0, color: "var(--muted)" }}>{t("buyerHome.examples")}</p>}
        {turns.map((m, i) => (
          <div
            key={i}
            data-testid={m.role === "user" ? "msg-user" : m.refused ? "msg-refused" : "msg-assistant"}
            style={{ justifySelf: m.role === "user" ? "end" : "start", maxWidth: "92%", padding: "0.6rem 0.9rem", borderRadius: 14, background: m.role === "user" ? "var(--surface-2)" : "transparent", border: m.refused ? "1px solid var(--warn)" : "1px solid var(--line)", display: "grid", gap: 6 }}
          >
            <span dir="auto" style={{ whiteSpace: "pre-wrap" }}>{m.content}</span>
            {m.refused && <small style={{ color: "var(--warn)" }}>{t("buyerHome.referred")}</small>}
            {m.citations?.slice(0, 3).map((c, j) => (
              <blockquote key={j} style={{ margin: 0, paddingInlineStart: 10, borderInlineStart: "3px solid var(--line)", color: "var(--muted)" }} dir="auto">
                {c.quote} <span className="num">({t("common.pageShort")} {c.page})</span>
              </blockquote>
            ))}
          </div>
        ))}
        {ask.isPending && <Skeleton h={36} />}
        {ask.error && <Alert tone="danger">{(ask.error as Error).message}</Alert>}
        <div ref={end} />
      </section>
      <form onSubmit={send} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <input aria-label={t("buyerHome.ask")} placeholder={t("buyerHome.ask")} value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} style={{ flex: "1 1 260px", minHeight: 48 }} />
        <button className="btn" type="submit" disabled={!text.trim() || ask.isPending} style={{ minHeight: 48 }}>{t("buyerHome.send")}</button>
      </form>
    </div>
  );
}
