import { useState, useEffect, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { aiService } from "@/services";
import { toApiError } from "@/lib/api";
import { Sparkles, Send, User } from "lucide-react";
import { cn } from "@/lib/cn";
import toast from "react-hot-toast";

type ChatMsg = { role: "user" | "assistant"; content: string };

export function AIPage() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const sendMut = useMutation({
    mutationFn: async (text: string) => {
      const r = await aiService.sendMessage(conversationId, text);
      return r.data;
    },
    onSuccess: (r) => {
      if (r?.conversation_id) setConversationId(r.conversation_id);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: r?.reply || r?.content || r?.message || "…" },
      ]);
    },
    onError: (err) => {
      const e = toApiError(err);
      toast.error(e.message);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: `⚠️ Erreur : ${e.message}`,
        },
      ]);
    },
  });

  const send = () => {
    const text = input.trim();
    if (!text || sendMut.isPending) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    sendMut.mutate(text);
  };

  const suggestions = [
    "Combien d'ouvriers présents aujourd'hui ?",
    "Liste les équipements offline",
    "Résumé des incidents des dernières 24h",
    "Snapshot de la plateforme",
  ];

  return (
    <div>
      <PageHeader
        title="Assistant IA"
        subtitle="Votre copilote KAYDAN SHIELD — pilote la plateforme en langage naturel"
      />

      <Card padded={false} className="flex flex-col h-[calc(100vh-220px)]">
        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.length === 0 && (
            <div className="h-full flex flex-col items-center justify-center gap-4 text-center">
              <div className="w-14 h-14 rounded-2xl bg-brand-500/10 text-brand-400 grid place-items-center">
                <Sparkles className="w-7 h-7" />
              </div>
              <div>
                <div className="text-lg font-semibold text-ink">Assistant KAYDAN SHIELD</div>
                <p className="mt-1 text-sm text-ink-muted max-w-md">
                  Posez une question sur vos chantiers, badges, terminaux, ou demandez de créer
                  des sites, employés, ouvriers…
                </p>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-4 w-full max-w-lg">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    onClick={() => {
                      setInput(s);
                    }}
                    className="text-left text-xs p-3 rounded-lg border border-surface-border bg-surface-soft/40 hover:bg-surface-soft hover:border-brand-500/40 transition-all"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div
              key={i}
              className={cn(
                "flex gap-3",
                m.role === "user" ? "flex-row-reverse" : "flex-row",
              )}
            >
              <div
                className={cn(
                  "w-8 h-8 rounded-lg grid place-items-center shrink-0",
                  m.role === "user"
                    ? "bg-info/10 text-info"
                    : "bg-brand-500/10 text-brand-400",
                )}
              >
                {m.role === "user" ? <User className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
              </div>
              <div
                className={cn(
                  "max-w-[80%] rounded-2xl px-4 py-2.5 text-sm whitespace-pre-wrap",
                  m.role === "user"
                    ? "bg-info/10 text-ink"
                    : "bg-surface-soft/60 border border-surface-border text-ink",
                )}
              >
                {m.content}
              </div>
            </div>
          ))}

          {sendMut.isPending && (
            <div className="flex gap-3">
              <div className="w-8 h-8 rounded-lg bg-brand-500/10 text-brand-400 grid place-items-center">
                <Sparkles className="w-4 h-4 animate-pulse" />
              </div>
              <div className="bg-surface-soft/60 border border-surface-border rounded-2xl px-4 py-3 text-sm text-ink-muted">
                <span className="inline-flex gap-1">
                  <span className="w-1.5 h-1.5 rounded-full bg-ink-muted animate-bounce" />
                  <span className="w-1.5 h-1.5 rounded-full bg-ink-muted animate-bounce" style={{ animationDelay: "0.15s" }} />
                  <span className="w-1.5 h-1.5 rounded-full bg-ink-muted animate-bounce" style={{ animationDelay: "0.3s" }} />
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Input */}
        <div className="border-t border-surface-border p-4">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
            className="flex gap-2"
          >
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Poser une question à l'assistant…"
              className="field flex-1"
              disabled={sendMut.isPending}
              autoFocus
            />
            <Button
              type="submit"
              disabled={!input.trim() || sendMut.isPending}
              leftIcon={<Send className="w-4 h-4" />}
            >
              Envoyer
            </Button>
          </form>
        </div>
      </Card>
    </div>
  );
}
