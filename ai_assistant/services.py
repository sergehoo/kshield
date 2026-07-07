"""Service IA — orchestration multi-provider (DeepSeek / OpenAI / Anthropic).

DeepSeek expose une API 100% compatible OpenAI, il suffit de changer :
- ``base_url`` : ``https://api.deepseek.com/v1``
- ``api_key``  : ta clé DeepSeek
- ``model``    : ``deepseek-chat`` ou ``deepseek-reasoner``

Configuration via ``settings.KAYDAN_SHIELD`` ou variables d'env :
    AI_PROVIDER      : "deepseek" (default) | "openai" | "anthropic"
    AI_MODEL         : override le modèle par défaut du provider
    DEEPSEEK_API_KEY : clé DeepSeek (obtenue sur https://platform.deepseek.com)
    OPENAI_API_KEY   : clé OpenAI si AI_PROVIDER=openai
    ANTHROPIC_API_KEY: clé Anthropic si AI_PROVIDER=anthropic
    AI_BASE_URL      : override manuel du base_url (utile pour proxies)
"""
from __future__ import annotations

import logging

from django.conf import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Config par provider
# ─────────────────────────────────────────────────────────────────────────────
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
    "azure": {
        # OpenAI Azure — override base_url via AI_BASE_URL
        "base_url":  None,
        "model":     "gpt-4o-mini",
        "key_name":  "AZURE_OPENAI_API_KEY",
    },
    # Anthropic n'utilise pas le SDK OpenAI — handling séparé
    "anthropic": {
        "base_url":  None,
        "model":     "claude-3-5-sonnet-20241022",
        "key_name":  "ANTHROPIC_API_KEY",
    },
}


def _get_ai_config():
    """Résolution : lit KAYDAN_SHIELD + variables d'env, applique defaults."""
    cfg = settings.KAYDAN_SHIELD or {}
    provider = (cfg.get("AI_PROVIDER") or "deepseek").lower()
    if provider not in _PROVIDER_DEFAULTS:
        provider = "deepseek"
    p = _PROVIDER_DEFAULTS[provider]

    # Clé API : cherche dans KAYDAN_SHIELD sous plusieurs noms possibles
    api_key = (
        cfg.get(p["key_name"])
        or cfg.get("AI_API_KEY")
        or cfg.get("OPENAI_API_KEY")   # legacy fallback
    )
    base_url = cfg.get("AI_BASE_URL") or p["base_url"]
    model = cfg.get("AI_MODEL") or p["model"]

    return {
        "provider": provider,
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
    }


class AIChatService:
    """Service IA multi-provider (DeepSeek, OpenAI, Anthropic)."""

    _SYSTEM_PROMPT = (
        "Tu es l'assistant KAYDAN SHIELD, expert en contrôle d'accès, pointage "
        "biométrique, anti-fraude et gestion de sites (BTP, tertiaire, sûreté). "
        "Tu connais les workflows : enrôlement de badges NFC/RFID/BLE, "
        "reconnaissance faciale, portiques UHF, terminaux ZKTeco/Hikvision/AiFace. "
        "Réponds en FRANÇAIS, de manière concise, actionnable, avec des étapes "
        "numérotées quand c'est pertinent. Si tu ne sais pas, dis-le et propose "
        "des pistes de diagnostic."
    )

    @classmethod
    def ask(cls, user, message: str, conversation=None,
            history: list | None = None) -> str:
        cfg = _get_ai_config()

        if not cfg["api_key"]:
            # Message adapté au provider configuré pour guider l'admin
            key_name = _PROVIDER_DEFAULTS[cfg["provider"]]["key_name"]
            return (
                f"Assistant en mode démo. Pour activer les réponses live : "
                f"définissez la variable d'environnement `{key_name}` "
                f"avec votre clé {cfg['provider'].capitalize()}. "
                f"(Provider actuel : {cfg['provider']}, modèle : {cfg['model']})"
            )

        # Provider "anthropic" : utilise le SDK anthropic natif
        if cfg["provider"] == "anthropic":
            return cls._ask_anthropic(cfg, message, history)

        # Providers OpenAI-compatibles (DeepSeek, OpenAI, Azure, autres)
        return cls._ask_openai_compat(cfg, message, history)

    @classmethod
    def _ask_openai_compat(cls, cfg, message, history):
        try:
            from openai import OpenAI
        except ImportError:
            return "Erreur : `openai` non installé (pip install openai)."

        try:
            client = OpenAI(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                timeout=30.0,
            )
        except Exception as exc:
            return f"Erreur d'initialisation client IA : {exc}"

        messages = [{"role": "system", "content": cls._SYSTEM_PROMPT}]
        for m in (history or [])[-10:]:
            if m.get("role") in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": message})

        try:
            resp = client.chat.completions.create(
                model=cfg["model"],
                messages=messages,
                max_tokens=800,
                temperature=0.4,   # DeepSeek recommande 0.4-0.7 pour tâches conv
                stream=False,
            )
            reply = (resp.choices[0].message.content or "").strip()
            if not reply:
                return "(Réponse vide de l'IA — réessayez.)"
            return reply
        except Exception as exc:
            logger.exception("AI chat failed (provider=%s)", cfg["provider"])
            # Message d'erreur user-friendly
            err_str = str(exc)
            if "401" in err_str or "authentication" in err_str.lower():
                return (
                    f"Clé API {cfg['provider']} invalide ou expirée. "
                    "Vérifiez la variable d'environnement."
                )
            if "429" in err_str or "rate" in err_str.lower():
                return (
                    "Quota IA dépassé ou rate-limit atteint. Réessayez dans "
                    "quelques secondes ou upgradez le plan côté provider."
                )
            if "timeout" in err_str.lower():
                return "Timeout côté provider IA — réessayez."
            return f"Erreur IA ({cfg['provider']}) : {err_str[:200]}"

    @classmethod
    def _ask_anthropic(cls, cfg, message, history):
        try:
            import anthropic
        except ImportError:
            return "Erreur : `anthropic` non installé (pip install anthropic)."
        try:
            client = anthropic.Anthropic(api_key=cfg["api_key"], timeout=30.0)
        except Exception as exc:
            return f"Erreur init client Anthropic : {exc}"

        messages = []
        for m in (history or [])[-10:]:
            if m.get("role") in ("user", "assistant"):
                messages.append({"role": m["role"], "content": m["content"]})
        messages.append({"role": "user", "content": message})

        try:
            resp = client.messages.create(
                model=cfg["model"],
                system=cls._SYSTEM_PROMPT,
                messages=messages,
                max_tokens=800,
            )
            # Anthropic renvoie une liste de content blocks
            parts = [b.text for b in resp.content if hasattr(b, "text")]
            return ("".join(parts) or "").strip() or "(Réponse vide.)"
        except Exception as exc:
            logger.exception("Anthropic chat failed")
            return f"Erreur IA (anthropic) : {str(exc)[:200]}"
