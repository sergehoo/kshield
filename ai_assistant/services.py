"""Service IA multi-provider (DeepSeek / OpenAI / Anthropic) avec function-calling.

Architecture "agent" :

  User posts message
      │
      ▼
  AIChatService.ask()
      │
      ▼
  LLM (avec tools schema)
      │
      ├── Décide d'appeler tools (ex: list_offline_devices, count_present_now)
      │       │
      │       ▼
      │   execute_tool() interroge Django ORM → renvoie dict JSON
      │       │
      │       └──> réinjecté au LLM
      │
      ▼
  LLM formule la réponse finale en Markdown (tableaux, listes, liens)
      │
      ▼
  Retour au user
"""
from __future__ import annotations

import json
import logging

from django.conf import settings

from .tools import execute_tool, get_tool_schemas_for_llm

logger = logging.getLogger(__name__)


_PROVIDER_DEFAULTS = {
    "deepseek": {
        "base_url":  "https://api.deepseek.com/v1",
        "model":     "deepseek-chat",
        "key_name":  "DEEPSEEK_API_KEY",
    },
    "openai": {
        "base_url":  "https://api.openai.com/v1",
        "model":     "gpt-4o-mini",
        "key_name":  "OPENAI_API_KEY",
    },
    "anthropic": {
        "base_url":  None,
        "model":     "claude-3-5-sonnet-20241022",
        "key_name":  "ANTHROPIC_API_KEY",
    },
}


def _get_ai_config():
    cfg = settings.KAYDAN_SHIELD or {}
    provider = (cfg.get("AI_PROVIDER") or "deepseek").lower()
    if provider not in _PROVIDER_DEFAULTS:
        provider = "deepseek"
    p = _PROVIDER_DEFAULTS[provider]
    api_key = (
        cfg.get(p["key_name"]) or cfg.get("AI_API_KEY") or cfg.get("OPENAI_API_KEY")
    )
    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": cfg.get("AI_BASE_URL") or p["base_url"],
        "model": cfg.get("AI_MODEL") or p["model"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Prompt système : contexte KAYDAN SHIELD complet
# ─────────────────────────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """Tu es le **copilote intelligent KAYDAN SHIELD** — un assistant expert en \
contrôle d'accès, pointage biométrique, anti-fraude et supervision de sites (BTP, tertiaire, sûreté).

## 🎯 Ta mission
Aider l'admin à superviser sa plateforme, générer des rapports, exécuter des actions, \
répondre à toute question sur l'état actuel du système.

## 🗺️ Écosystème KAYDAN SHIELD
La plateforme comporte les modules suivants (chaque module est une app Django) :
- **employees** : employés bureau (matricule, contrat, département, badge NFC)
- **ouvriers** (workers) : ouvriers chantier (casque UHF+BLE obligatoire, sous-traitant)
- **visitors** : visiteurs (badge QR temporaire, VisitRequest)
- **sites** : sites physiques (usine, chantier, bureau) + zones + checkpoints
- **devices** : équipements (badges, casques, lecteurs, portiques, terminaux face, gateways BLE)
- **access_control** : événements d'accès (AccessEvent), règles, décisions granted/denied
- **attendance** : pointage (Punch, AttendanceDay), heures sup (OvertimeCalculation)
- **antifraud** : détection anomalies (FraudAlert), règles configurables
- **notifications** : email/SMS/webhook/websocket
- **audit** : journal d'audit
- **reports** : digests exécutifs hebdo/mensuel
- **sso** : Keycloak OIDC
- **ai_assistant** : c'est toi

## 🔌 Équipements supportés
- **Terminaux face** : ZKTeco SpeedFace, Hikvision DS-K1T, Dahua ASI7213, AiFace AI810 (ADMS)
- **Terminaux pointage** : ZKTeco K14/K20 (SDK ZKAccess port 4370)
- **Portiques RFID UHF** : FOCUS ST-G8 (LLRP port 5084)
- **Beacons BLE casques** : MOKO H7 Lite (via gateways BLE HTTP)
- **Lecteurs NFC/RFID** : Impinj, Zebra, HID OMNIKEY
- **Caméras IP** : ONVIF + RTSP + face recognition YOLOv8/InsightFace
- **Contrôleurs**, **serrures**, **passerelles IoT**

## 📊 Sources de données (via tes tools)
Tu as accès en LECTURE à :
- Tous les équipements, sites, entreprises, employés, ouvriers, visiteurs
- Événements d'accès temps réel, pointages du jour, incidents anti-fraude
- KPIs plateforme, heartbeat devices, statistiques
Et en ACTIONS (avec RBAC + audit) :
- Suspendre / révoquer un badge
- Synchroniser un terminal ZKTeco à la demande
- Pousser un employé vers les terminaux
- Lancer un test de connectivité device

## ⚡ Règles impératives

1. **AUCUNE réponse générique** quand les données existent dans Shield. Toujours appeler \
un tool pour récupérer l'état RÉEL avant de répondre.
   - "Quels équipements sont connectés ?" → appelle `list_devices` ou `platform_snapshot`
   - "Combien de personnes présentes ?" → appelle `count_present_now`
   - "Derniers incidents ?" → appelle `recent_incidents`

2. **Format Markdown riche** dans tes réponses :
   - Tableaux avec `|` pour lister des équipements / employés / events
   - Titres `##` / `###` pour structurer un rapport
   - Listes `-` ou `1.` numérotées pour étapes actionnables
   - Liens `[texte](/url)` vers les fiches détaillées (utilise `url` renvoyé par les tools)
   - Blocs de code ` ``` ` pour les commandes shell / snippets JSON

3. **Toujours proposer des ACTIONS suivantes** pertinentes au contexte :
   - "→ [Ouvrir la fiche](url)" · "→ Redémarrer" · "→ Consulter les logs"

4. **Confirmer avant toute action** modifiante (suspend, revoke, restart). \
Ne pas exécuter directement — demande "Confirmez-vous ?" et attends la réponse user.

5. **Si un tool renvoie une erreur** (`{"error": "..."}`), explique-la clairement à l'user \
avec des pistes de résolution.

6. **Réponses en FRANÇAIS**, concises, actionnables, avec chiffres précis.

## 📝 Rapports professionnels
Si l'user demande un **rapport** (pointage, activité, incidents, présence…), \
structure la réponse en Markdown avec :
- Titre H1
- Section "Contexte" (période, filtres)
- Section "Chiffres clés" (KPIs en tableau)
- Section "Détails" (liste ou tableau des lignes)
- Section "Constats & recommandations" (analyse actionnable)
- Fin : lien vers export XLSX ou PDF si dispo

## 🚦 Exemples d'interactions

**User** : *"Quels équipements sont hors ligne ?"*
**Toi** : Tu appelles `list_offline_devices` puis réponds :
```
## 🔴 Équipements hors ligne (3)

Aucun heartbeat depuis > 5 minutes :

| ID | Modèle | Site | Dernier vu |
|----|--------|------|-----------|
| #12 | ZKTeco K14/ID | HQ | il y a 34 min |
| #7 | FOCUS ST-G8 | Chantier Ouest | jamais |
...
```

**User** : *"Fais un état des lieux"*
**Toi** : `platform_snapshot` puis rapport synthétique avec KPIs + alertes.

Prêt à assister. Que faisons-nous ?
"""


# ─────────────────────────────────────────────────────────────────────────────
# Service principal
# ─────────────────────────────────────────────────────────────────────────────
class AIChatService:
    """Chat IA multi-provider avec function-calling.

    Boucle d'agent : LLM → tool call → tool exec → réinjection → réponse finale.
    Limite le nombre d'itérations pour éviter les runaway loops.
    """

    MAX_TOOL_ITERATIONS = 5

    @classmethod
    def ask(cls, user, message: str, conversation=None,
            history: list | None = None) -> str:
        cfg = _get_ai_config()
        if not cfg["api_key"]:
            key_name = _PROVIDER_DEFAULTS[cfg["provider"]]["key_name"]
            return (
                f"Assistant en mode démo. Configure `{key_name}` dans les variables "
                f"d'environnement Dokploy pour activer les réponses live "
                f"(provider={cfg['provider']}, model={cfg['model']})."
            )

        # Anthropic — SDK différent, on ne supporte pas function-calling ici pour l'instant
        if cfg["provider"] == "anthropic":
            return cls._ask_anthropic_simple(cfg, message, history)

        # OpenAI-compatible (DeepSeek, OpenAI) — function calling activé
        return cls._ask_with_tools(cfg, user, message, history)

    # ─────────────────────────────────────────────────────────────────────
    # OpenAI / DeepSeek — avec function calling
    # ─────────────────────────────────────────────────────────────────────
    @classmethod
    def _ask_with_tools(cls, cfg, user, message, history):
        try:
            from openai import OpenAI
        except ImportError:
            return "Erreur : SDK `openai` non installé (pip install openai)."

        try:
            client = OpenAI(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                timeout=45.0,
            )
        except Exception as exc:
            return f"Erreur init client IA : {exc}"

        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        for m in (history or [])[-10:]:
            role = m.get("role")
            if role in ("user", "assistant"):
                # Normaliser : le widget UI envoie parfois "bot" au lieu de "assistant"
                role = "assistant" if role in ("bot", "assistant") else "user"
                content = m.get("content") or ""
                # Sanitize simple — retire les tags HTML du historique
                import re as _re
                content = _re.sub(r"<[^>]+>", "", content)
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        tools = get_tool_schemas_for_llm()

        # Boucle d'agent : max N itérations
        for iteration in range(cls.MAX_TOOL_ITERATIONS):
            try:
                resp = client.chat.completions.create(
                    model=cfg["model"],
                    messages=messages,
                    tools=tools,
                    tool_choice="auto",
                    max_tokens=1500,
                    temperature=0.3,
                )
            except Exception as exc:
                logger.exception("LLM call failed")
                return cls._format_error(cfg["provider"], exc)

            choice = resp.choices[0]
            msg = choice.message

            # Cas 1 : le LLM a demandé un ou plusieurs tool calls
            if getattr(msg, "tool_calls", None):
                # Ajoute la réponse assistant (avec tool_calls) à l'historique
                messages.append({
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments,
                            },
                        }
                        for tc in msg.tool_calls
                    ],
                })
                # Exécute chaque tool et pousse le résultat
                for tc in msg.tool_calls:
                    tool_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    logger.info("AI tool call : %s(%s)", tool_name, args)
                    result = execute_tool(tool_name, args, user=user)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, default=str, ensure_ascii=False),
                    })
                continue    # boucle : le LLM va maintenant formuler la réponse

            # Cas 2 : le LLM a produit une réponse finale (texte)
            reply = (msg.content or "").strip()
            return reply or "(Réponse vide de l'IA)"

        return (
            "⚠️ L'assistant a atteint le nombre max de tool calls "
            f"({cls.MAX_TOOL_ITERATIONS}). Reformule ta question plus précisément."
        )

    # ─────────────────────────────────────────────────────────────────────
    # Anthropic — sans function calling (fallback simple)
    # ─────────────────────────────────────────────────────────────────────
    @classmethod
    def _ask_anthropic_simple(cls, cfg, message, history):
        try:
            import anthropic
        except ImportError:
            return "SDK `anthropic` non installé."
        try:
            client = anthropic.Anthropic(api_key=cfg["api_key"], timeout=30.0)
        except Exception as exc:
            return f"Erreur init Anthropic : {exc}"
        messages = []
        for m in (history or [])[-10:]:
            role = m.get("role")
            if role in ("user", "assistant"):
                role = "assistant" if role in ("bot", "assistant") else "user"
                messages.append({"role": role, "content": m.get("content", "")})
        messages.append({"role": "user", "content": message})
        try:
            resp = client.messages.create(
                model=cfg["model"],
                system=_SYSTEM_PROMPT,
                messages=messages,
                max_tokens=1500,
            )
            parts = [b.text for b in resp.content if hasattr(b, "text")]
            return "".join(parts) or "(vide)"
        except Exception as exc:
            return cls._format_error("anthropic", exc)

    @staticmethod
    def _format_error(provider, exc):
        err = str(exc)
        if "401" in err or "authentication" in err.lower():
            return (f"🔑 Clé API {provider} invalide ou expirée. "
                    "Vérifie la variable d'environnement.")
        if "429" in err or "rate" in err.lower():
            return "⏱️ Quota IA dépassé. Réessaye dans quelques secondes."
        if "timeout" in err.lower():
            return "⌛ Timeout provider IA."
        return f"❌ Erreur IA ({provider}) : {err[:200]}"
