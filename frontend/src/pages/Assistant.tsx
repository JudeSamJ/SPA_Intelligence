import { useEffect, useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ApiError, type ChatTurn, type Citation } from "../api/client";
import { useChat } from "../api/hooks";
import { Alert, Loader } from "../components/ui";
import { useFmt } from "../i18n/format";
import { TypeText } from "../motion/TypeText";
import { useContractCtx } from "./ctx";

interface Msg {
  id: number;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  refused?: boolean;
  animate?: boolean;
}
const SUGGESTIONS = ["s1", "s2", "s3", "s4", "s5"] as const;

export default function Assistant() {
  const { t } = useTranslation();
  const fmt = useFmt();
  const { id, openEvidence } = useContractCtx();
  const chat = useChat(id);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const log = useRef<HTMLDivElement>(null);
  const seq = useRef(0);

  useEffect(() => {
    setMsgs([]);
    setError(null);
  }, [id]);
  useEffect(() => {
    log.current?.lastElementChild?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [msgs.length, chat.isPending]);

  const send = (message: string) => {
    const m = message.trim();
    if (!m || chat.isPending) return;
    setError(null);
    const history: ChatTurn[] = msgs.slice(-12).map((x) => ({ role: x.role, content: x.content }));
    setMsgs((p) => [
      ...p.map((x) => ({ ...x, animate: false })),
      { id: ++seq.current, role: "user", content: m },
    ]);
    setText("");
    chat.mutate(
      { message: m, history },
      {
        onSuccess: (r) =>
          setMsgs((p) => [
            ...p,
            {
              id: ++seq.current,
              role: "assistant",
              content: r.answer,
              citations: r.citations,
              refused: r.refused,
              animate: true,
            },
          ]),
        onError: (e) => setError(e instanceof ApiError ? e.message : t("errors.generic")),
      },
    );
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    send(text);
  };

  return (
    <div className="data-layer" style={{ display: "grid", gap: "0.9rem" }}>
      <p style={{ margin: 0, color: "var(--muted)", maxWidth: "70ch" }}>{t("chat.intro")}</p>
      <div
        ref={log}
        role="log"
        aria-live="polite"
        aria-label={t("chat.title")}
        className="card"
        data-testid="chat-log"
        style={{
          padding: "1rem",
          minHeight: 280,
          maxHeight: "55dvh",
          overflowY: "auto",
          display: "grid",
          gap: 12,
          alignContent: "start",
        }}
      >
        {msgs.length === 0 && (
          <div style={{ display: "grid", gap: 8 }}>
            <strong>{t("chat.suggestions")}</strong>
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {SUGGESTIONS.map((s) => (
                <button key={s} className="chip" onClick={() => send(t(`chat.${s}`))}>
                  {t(`chat.${s}`)}
                </button>
              ))}
            </div>
          </div>
        )}
        {msgs.map((m) => (
          <div
            key={m.id}
            data-testid={m.role === "user" ? "msg-user" : m.refused ? "msg-refused" : "msg-assistant"}
            style={{
              justifySelf: m.role === "user" ? "end" : "start",
              maxWidth: "min(92%, 62ch)",
              padding: "0.7rem 0.95rem",
              borderRadius: 14,
              background:
                m.role === "user"
                  ? "var(--accent-fill)"
                  : m.refused
                    ? "var(--danger-bg)"
                    : "var(--surface-2)",
              color: m.role === "user" ? "var(--on-accent)" : "var(--fg)",
              border: m.refused ? "1px solid var(--danger)" : "1px solid transparent",
            }}
          >
            <div style={{ fontSize: "0.78rem", fontWeight: 700, opacity: 0.85, marginBlockEnd: 4 }}>
              {m.role === "user" ? t("chat.you") : m.refused ? `⚖ ${t("chat.refused")}` : t("chat.assistant")}
            </div>
            <div dir="auto">
              {m.role === "assistant" ? <TypeText text={m.content} animate={!!m.animate} /> : m.content}
            </div>
            {!!m.citations?.length && (
              <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBlockStart: 8 }}>
                {m.citations.map((c, i) => (
                  <button
                    key={i}
                    className="chip"
                    data-testid="citation"
                    onClick={() => openEvidence({ page: c.page, quote: c.quote })}
                    aria-label={t("chat.openCitation", { page: fmt.num(c.page) })}
                    title={c.quote}
                    style={{ maxWidth: "100%" }}
                  >
                    📎 <span className="num">{t("chat.citation", { page: fmt.num(c.page) })}</span>{" "}
                    <span
                      dir="auto"
                      style={{
                        color: "var(--muted)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        maxWidth: 240,
                      }}
                    >
                      “{c.quote}”
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
        {chat.isPending && (
          <div
            role="status"
            style={{ display: "flex", gap: 10, alignItems: "center", color: "var(--muted)" }}
          >
            <Loader size={34} label={t("chat.thinking")} />
            {t("chat.thinking")}
          </div>
        )}
      </div>
      {error && (
        <Alert tone="danger">
          {t("chat.error")}: {error}
        </Alert>
      )}
      {msgs.length > 0 && (
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {SUGGESTIONS.map((s) => (
            <button key={s} className="chip" onClick={() => send(t(`chat.${s}`))}>
              {t(`chat.${s}`)}
            </button>
          ))}
        </div>
      )}
      <form onSubmit={submit} style={{ display: "flex", gap: 8 }}>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("chat.placeholder")}
          aria-label={t("chat.placeholder")}
          maxLength={2000}
          dir="auto"
          style={{
            flex: 1,
            padding: "0.75rem 1rem",
            borderRadius: 999,
            border: "1px solid var(--line)",
            background: "var(--surface)",
            color: "var(--fg)",
            font: "inherit",
          }}
        />
        <button className="btn" type="submit" disabled={chat.isPending || !text.trim()}>
          {t("chat.send")}
        </button>
      </form>
    </div>
  );
}
