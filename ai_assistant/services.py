"""Service IA — orchestration RAG + function calling."""
from __future__ import annotations

from django.conf import settings


class AIChatService:
    """Stub minimal — branchez votre provider (OpenAI, Anthropic, etc.) ici."""

    @classmethod
    def ask(cls, user, message: str, conversation=None, history: list | None = None) -> str:
        api_key = settings.KAYDAN_SHIELD.get("OPENAI_API_KEY")
        if not api_key:
            return (
                "Assistant en mode démo : connectez `OPENAI_API_KEY` "
                "dans settings.KAYDAN_SHIELD pour activer les réponses live."
            )
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            sys_prompt = (
                "Tu es l'assistant KAYDAN SHIELD, expert en contrôle d'accès, "
                "pointage et anti-fraude. Réponds en français, concis et actionnable."
            )
            messages = [{"role": "system", "content": sys_prompt}]
            for m in (history or [])[-10:]:
                if m.get("role") in ("user", "assistant"):
                    messages.append({"role": m["role"], "content": m["content"]})
            messages.append({"role": "user", "content": message})
            resp = client.chat.completions.create(
                model=settings.KAYDAN_SHIELD.get("AI_MODEL", "gpt-4o-mini"),
                messages=messages,
                max_tokens=600,
            )
            return resp.choices[0].message.content or ""
        except Exception as exc:  # pragma: no cover
            return f"Erreur IA: {exc}"
