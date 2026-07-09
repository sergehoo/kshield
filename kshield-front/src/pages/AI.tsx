import { useState, useEffect, useRef, useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { aiService, systemService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtRelative } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  Sparkles, Send, User as UserIcon, Search, ShieldAlert, Users as UsersIcon,
  Calendar, CheckCheck, Zap, Plus, Building2, HardHat, CreditCard, Cpu,
  UserPlus, Camera, Trash2, RefreshCw, ChevronRight, Wand2, Wrench,
  BarChart3, TrendingUp,
} from "lucide-react";
import toast from "react-hot-toast";

type ChatMsg = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  tool_name?: string;
  tool_args?: any;
  tool_result?: any;
  created_at: string;
};

type Suggestion = {
  label: string;
  prompt: string;
  icon: React.ComponentType<{ className?: string }>;
  category: "analyze" | "create" | "action" | "search";
};

const SUGGESTIONS: Suggestion[] = [
  // Analyses
  { category: "analyze", label: "Détecter les doublons d'ouvriers",
    prompt: "Peux-tu chercher les ouvriers en doublon dans la base ? Utilise tous les critères (téléphone, nom, pièce d'identité).",
    icon: UsersIcon },
  { category: "analyze", label: "Absences répétées (>5 en 30j)",
    prompt: "Identifie les ouvriers avec plus de 5 absences sur les 30 derniers jours.",
    icon: Calendar },
  { category: "analyze", label: "Analyser les patterns de fraude",
    prompt: "Cherche des patterns suspects dans les événements d'accès des 48 dernières heures : multi-sites, refus multiples, hors horaires.",
    icon: ShieldAlert },
  { category: "analyze", label: "Snapshot plateforme",
    prompt: "Donne-moi un snapshot intelligent de la plateforme : couverture badges, terminaux offline, alertes en cours.",
    icon: BarChart3 },
  { category: "analyze", label: "Retards répétés",
    prompt: "Quels ouvriers arrivent systématiquement en retard sur les 30 derniers jours ?",
    icon: TrendingUp },

  // Créer
  { category: "create", label: "Créer un site",
    prompt: "Crée le site 'RIVIERA 4' à Abidjan pour KAYDAN BTP.",
    icon: Building2 },
  { category: "create", label: "Créer plusieurs sites",
    prompt: "Crée les sites suivants : AHOUE, KRE SIEGE, KAYDAN TECHNOLOGIE, CALISTO, DATARIUM.",
    icon: Building2 },
  { category: "create", label: "Ajouter un employé",
    prompt: "Crée un nouvel employé : Jean Kouassi, matricule EMP-100, poste Chef de chantier, société KAYDAN BTP.",
    icon: UserPlus },
  { category: "create", label: "Ajouter un ouvrier",
    prompt: "Crée un ouvrier : Adama Traoré, matricule OV-100, métier maçon.",
    icon: HardHat },

  // Actions
  { category: "action", label: "Sync ZKTeco",
    prompt: "Lance une synchronisation ZKTeco sur tous les terminaux actifs.",
    icon: Zap },
  { category: "action", label: "Push face templates",
    prompt: "Pousse tous les templates faciaux vers les terminaux de reconnaissance faciale.",
    icon: Zap },
  { category: "action", label: "Test connectivité terminaux",
    prompt: "Teste la connectivité de tous les terminaux et donne-moi la liste de ceux offline.",
    icon: Wrench },

  // Search
  { category: "search", label: "Rechercher une personne",
    prompt: "Recherche 'Kouassi' dans toute la plateforme (employés, ouvriers, badges).",
    icon: Search },
  { category: "search", label: "Lister équipements offline",
    prompt: "Liste tous les équipements actuellement hors ligne avec leur dernier heartbeat.",
    icon: Cpu },
];

export function AIPage() {
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeCategory, setActiveCategory] = useState<Suggestion["category"] | "all">("all");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // Contexte plateforme (rafraîchi toutes les 30s)
  const { data: snapshot } = useQuery({
    queryKey: ["ai-snapshot"],
    queryFn: async () => (await systemService.status()).data,
    refetchInterval: 30_000,
    retry: false,
  });

  // Historique conversations
  const { data: convos } = useQuery({
    queryKey: ["ai-conversations"],
    queryFn: async () => (await aiService.conversations()).data,
    retry: false,
  });

  const sendMut = useMutation({
    mutationFn: async (text: string) => {
      const r = await aiService.sendMessage(conversationId, text);
      return r.data;
    },
    onSuccess: (r: any) => {
      if (r?.conversation_id) setConversationId(r.conversation_id);
      const msg: ChatMsg = {
        id: `${Date.now()}-a`,
        role: "assistant",
        content: r?.reply || r?.content || r?.message || "…",
        created_at: new Date().toISOString(),
        tool_result: r?.tool_calls || r?.tools_used,
      };
      setMessages((m) => [...m, msg]);
    },
    onError: (err) => {
      const e = toApiError(err);
      toast.error(e.message);
      setMessages((m) => [...m, {
        id: `${Date.now()}-e`,
        role: "assistant",
        content: `⚠️ **Erreur** : ${e.message}`,
        created_at: new Date().toISOString(),
      }]);
    },
  });

  const send = (text?: string) => {
    const value = (text ?? input).trim();
    if (!value || sendMut.isPending) return;
    setMessages((m) => [...m, {
      id: `${Date.now()}-u`,
      role: "user",
      content: value,
      created_at: new Date().toISOString(),
    }]);
    setInput("");
    sendMut.mutate(value);
  };

  const newConversation = () => {
    setMessages([]);
    setConversationId(null);
    setInput("");
  };

  const filteredSuggestions = useMemo(() =>
    activeCategory === "all"
      ? SUGGESTIONS
      : SUGGESTIONS.filter((s) => s.category === activeCategory),
    [activeCategory],
  );

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-[calc(100vh-160px)] -mx-4 md:-mx-6 px-4 md:px-6">
      {/* ═══ Colonne gauche : Quick actions + historique ═══ */}
      <aside className={cn(
        "shrink-0 flex flex-col gap-3 transition-all",
        sidebarCollapsed ? "w-14" : "w-full lg:w-72",
      )}>
        <Card padded={false} className="flex-1 overflow-hidden flex flex-col">
          {/* Header avec toggle collapse */}
          <div className="flex items-center justify-between p-3 border-b border-surface-border">
            {!sidebarCollapsed && (
              <div className="text-xs font-semibold text-ink uppercase tracking-wider">
                Actions rapides
              </div>
            )}
            <button
              onClick={() => setSidebarCollapsed((s) => !s)}
              className="p-1 rounded-md hover:bg-surface-soft text-ink-muted"
              title={sidebarCollapsed ? "Déployer" : "Réduire"}
            >
              <ChevronRight className={cn("w-4 h-4 transition-transform", !sidebarCollapsed && "rotate-180")} />
            </button>
          </div>

          {!sidebarCollapsed && (
            <>
              {/* Nouvelle conversation */}
              <div className="p-3">
                <Button
                  className="w-full justify-center"
                  size="sm"
                  leftIcon={<Plus className="w-3.5 h-3.5" />}
                  onClick={newConversation}
                >
                  Nouvelle discussion
                </Button>
              </div>

              {/* Filtres catégories */}
              <div className="px-3 pb-2 flex gap-1 flex-wrap">
                {[
                  { key: "all",     label: "Tous",      icon: Sparkles },
                  { key: "analyze", label: "Analyser",  icon: BarChart3 },
                  { key: "create",  label: "Créer",     icon: Plus },
                  { key: "action",  label: "Actions",   icon: Zap },
                  { key: "search",  label: "Chercher",  icon: Search },
                ].map((c) => (
                  <button
                    key={c.key}
                    onClick={() => setActiveCategory(c.key as any)}
                    className={cn(
                      "flex items-center gap-1 px-2 py-1 rounded-md text-[10px] font-medium",
                      activeCategory === c.key
                        ? "bg-brand-500 text-white"
                        : "bg-surface-soft text-ink-muted hover:text-ink",
                    )}
                  >
                    <c.icon className="w-3 h-3" />
                    {c.label}
                  </button>
                ))}
              </div>

              {/* Liste suggestions */}
              <div className="flex-1 overflow-y-auto p-2 space-y-1">
                {filteredSuggestions.map((s, i) => (
                  <button
                    key={i}
                    onClick={() => send(s.prompt)}
                    disabled={sendMut.isPending}
                    className="w-full text-left flex items-start gap-2 p-2 rounded-lg hover:bg-surface-soft transition group"
                  >
                    <div className={cn(
                      "w-7 h-7 rounded-md grid place-items-center shrink-0",
                      s.category === "analyze" ? "bg-info/10 text-info" :
                      s.category === "create"  ? "bg-ok/10 text-ok" :
                      s.category === "action"  ? "bg-warn/10 text-warn" :
                      "bg-brand-500/10 text-brand-400",
                    )}>
                      <s.icon className="w-3.5 h-3.5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="text-xs font-medium text-ink group-hover:text-brand-400 truncate">
                        {s.label}
                      </div>
                    </div>
                  </button>
                ))}
              </div>

              {/* Historique récent */}
              {(convos?.results?.length ?? 0) > 0 && (
                <div className="border-t border-surface-border p-2 max-h-40 overflow-y-auto">
                  <div className="text-[10px] uppercase tracking-wider text-ink-soft font-semibold px-2 py-1">
                    Discussions récentes
                  </div>
                  {convos?.results?.slice(0, 5).map((c: any) => (
                    <button
                      key={c.id}
                      onClick={() => {
                        setConversationId(c.id);
                        setMessages(c.messages || []);
                      }}
                      className="w-full text-left px-2 py-1 rounded hover:bg-surface-soft text-xs text-ink-muted hover:text-ink truncate"
                    >
                      {c.title || `Discussion #${c.id}`}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
        </Card>
      </aside>

      {/* ═══ Colonne centre : Chat ═══ */}
      <Card padded={false} className="flex-1 flex flex-col min-w-0">
        {/* Header chat */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-surface-border">
          <div className="w-9 h-9 rounded-xl bg-brand-500/10 text-brand-400 grid place-items-center">
            <Sparkles className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-ink">Shield IA</div>
            <div className="text-[11px] text-ink-soft">
              Assistant intelligent · Actions CRUD · Analyses & détection
            </div>
          </div>
          {messages.length > 0 && (
            <button
              onClick={newConversation}
              className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink"
              title="Effacer et recommencer"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto p-5 space-y-4">
          {messages.length === 0 && <WelcomeScreen onPick={(p) => send(p)} />}

          {messages.map((m) => (
            <MessageBubble key={m.id} msg={m} />
          ))}

          {sendMut.isPending && <ThinkingBubble />}
        </div>

        {/* Input */}
        <div className="border-t border-surface-border p-3">
          <form
            onSubmit={(e) => { e.preventDefault(); send(); }}
            className="flex gap-2"
          >
            <div className="flex-1 relative">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Pose une question, demande une analyse, ou lance une action…"
                className="field w-full pr-24"
                disabled={sendMut.isPending}
                autoFocus
              />
              <div className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-ink-soft">
                <kbd className="px-1.5 py-0.5 rounded bg-surface font-mono">Entrée</kbd>
              </div>
            </div>
            <Button
              type="submit"
              disabled={!input.trim() || sendMut.isPending}
              leftIcon={<Send className="w-4 h-4" />}
            >
              Envoyer
            </Button>
          </form>
          <p className="mt-2 text-[10px] text-ink-soft text-center">
            Shield IA peut créer, modifier, analyser. Les actions sensibles sont audit-loggées.
          </p>
        </div>
      </Card>

      {/* ═══ Colonne droite : Contexte plateforme ═══ */}
      <aside className="hidden xl:flex w-64 shrink-0 flex-col gap-3">
        <Card title="📊 Plateforme" padded={true}>
          {snapshot ? (
            <div className="space-y-2 text-xs">
              <PlatformStat label="Sites" value={snapshot?.env?.sites_count} />
              <PlatformStat label="Ouvriers" value={snapshot?.env?.workers_count} />
              <PlatformStat label="Terminaux" value={snapshot?.env?.devices_count} />
              <PlatformStat label="Badges actifs" value={snapshot?.env?.active_badges} />
              <PlatformStat label="Alertes ouvertes"
                value={snapshot?.env?.open_alerts}
                tone={snapshot?.env?.open_alerts > 0 ? "danger" : "muted"}
              />
              <div className="pt-2 border-t border-surface-border/60 text-[10px] text-ink-soft">
                Actualisé toutes les 30s
              </div>
            </div>
          ) : (
            <div className="text-xs text-ink-soft text-center py-3">
              Chargement contexte…
            </div>
          )}
        </Card>

        <Card title="💡 Suggestions IA" padded={true}>
          <div className="space-y-2 text-xs">
            <SuggestionChip
              onClick={() => send("Fais un audit complet de conformité HSE : ouvriers sans casque, sans certif valide, sans affectation.")}
              text="Audit conformité HSE"
              icon={<HardHat className="w-3 h-3" />}
            />
            <SuggestionChip
              onClick={() => send("Détecte les 5 sites avec le plus d'événements d'accès refusés cette semaine.")}
              text="Top 5 sites refus"
              icon={<Camera className="w-3 h-3" />}
            />
            <SuggestionChip
              onClick={() => send("Analyse l'attribution des badges : combien d'ouvriers actifs n'ont pas de badge ?")}
              text="Badges manquants"
              icon={<CreditCard className="w-3 h-3" />}
            />
            <SuggestionChip
              onClick={() => send("Résume l'activité de la journée : présents, retards, incidents, événements notables.")}
              text="Résumé de la journée"
              icon={<CheckCheck className="w-3 h-3" />}
            />
          </div>
        </Card>

        <div className="text-[10px] text-ink-soft text-center px-2">
          Shield IA utilise DeepSeek + tools KAYDAN.
        </div>
      </aside>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────
// Sous-composants
// ─────────────────────────────────────────────────────────────────────

function WelcomeScreen({ onPick }: { onPick: (prompt: string) => void }) {
  const quickPrompts = [
    "Combien d'ouvriers présents aujourd'hui ?",
    "Détecte les doublons d'ouvriers dans la base",
    "Analyse les patterns de fraude des dernières 48h",
    "Snapshot intelligent de la plateforme",
  ];

  return (
    <div className="h-full flex flex-col items-center justify-center gap-4 text-center py-8">
      <div className="w-16 h-16 rounded-2xl bg-brand-500/10 text-brand-400 grid place-items-center">
        <Wand2 className="w-8 h-8" />
      </div>
      <div>
        <div className="text-xl font-bold text-ink">Shield IA à votre écoute</div>
        <p className="mt-2 text-sm text-ink-muted max-w-md">
          Posez une question métier, demandez une analyse (fraudes, doublons, absences),
          ou déclenchez une action (créer un site, sync ZK, push face…). Shield IA
          connaît toute votre plateforme.
        </p>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-4 w-full max-w-2xl">
        {quickPrompts.map((p) => (
          <button
            key={p}
            onClick={() => onPick(p)}
            className="text-left text-xs p-3 rounded-lg border border-surface-border bg-surface-soft/40 hover:bg-surface-soft hover:border-brand-500/40 transition-all"
          >
            {p}
          </button>
        ))}
      </div>
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMsg }) {
  const isUser = msg.role === "user";
  return (
    <div className={cn("flex gap-3", isUser ? "flex-row-reverse" : "flex-row")}>
      <div className={cn(
        "w-8 h-8 rounded-lg grid place-items-center shrink-0",
        isUser ? "bg-info/10 text-info" : "bg-brand-500/10 text-brand-400",
      )}>
        {isUser ? <UserIcon className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
      </div>
      <div className={cn(
        "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm",
        isUser
          ? "bg-info/10 text-ink"
          : "bg-surface-soft/60 border border-surface-border text-ink",
      )}>
        <div className="whitespace-pre-wrap leading-relaxed"
             dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }} />
        {msg.tool_result && Array.isArray(msg.tool_result) && msg.tool_result.length > 0 && (
          <div className="mt-2 space-y-1">
            {msg.tool_result.map((t: any, i: number) => (
              <div key={i} className="text-[11px] text-ink-soft bg-surface p-2 rounded border border-surface-border">
                <div className="flex items-center gap-1.5 mb-1">
                  <Zap className="w-3 h-3 text-brand-500" />
                  <code className="font-mono text-brand-400">{t.name || t.tool_name}</code>
                </div>
                {t.result && (
                  <pre className="text-[10px] overflow-x-auto text-ink-muted">
                    {JSON.stringify(t.result, null, 2).slice(0, 400)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="mt-1 text-[10px] text-ink-soft">{fmtRelative(msg.created_at)}</div>
      </div>
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex gap-3">
      <div className="w-8 h-8 rounded-lg bg-brand-500/10 text-brand-400 grid place-items-center">
        <Sparkles className="w-4 h-4 animate-pulse" />
      </div>
      <div className="bg-surface-soft/60 border border-surface-border rounded-2xl px-4 py-3">
        <span className="inline-flex gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-ink-muted animate-bounce" />
          <span className="w-1.5 h-1.5 rounded-full bg-ink-muted animate-bounce" style={{ animationDelay: "0.15s" }} />
          <span className="w-1.5 h-1.5 rounded-full bg-ink-muted animate-bounce" style={{ animationDelay: "0.3s" }} />
        </span>
      </div>
    </div>
  );
}

function PlatformStat({ label, value, tone }: { label: string; value: any; tone?: "danger" | "muted" }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-ink-muted">{label}</span>
      <Badge tone={tone || "info"}>{value ?? "—"}</Badge>
    </div>
  );
}

function SuggestionChip({ onClick, text, icon }: { onClick: () => void; text: string; icon: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left flex items-center gap-2 p-2 rounded-lg bg-surface-soft/40 hover:bg-surface-soft border border-transparent hover:border-brand-500/40 transition"
    >
      <span className="text-brand-500">{icon}</span>
      <span className="text-ink">{text}</span>
    </button>
  );
}

// Mini renderer Markdown (bold, italic, code, list, headers) sans dépendance
function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`([^`]+)`/g, "<code class=\"px-1.5 py-0.5 rounded bg-surface text-xs font-mono\">$1</code>")
    .replace(/^### (.+)$/gm, "<h3 class=\"text-sm font-semibold mt-2\">$1</h3>")
    .replace(/^## (.+)$/gm, "<h2 class=\"text-base font-semibold mt-2\">$1</h2>")
    .replace(/^\* (.+)$/gm, "<li class=\"ml-4 list-disc\">$1</li>")
    .replace(/\n\n/g, "<br/><br/>")
    .replace(/\n/g, "<br/>");
}
