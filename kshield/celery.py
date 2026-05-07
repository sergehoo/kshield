"""Celery app for KAYDAN SHIELD.

Le module settings est sélectionné via la variable d'environnement
`DJANGO_SETTINGS_MODULE`. Si elle n'est pas définie, on tombe sur dev
(par défaut sécurisé). En prod, le worker celery doit être lancé avec :

    DJANGO_SETTINGS_MODULE=kshield.settings.prod celery -A kshield worker
"""
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "kshield.settings.dev")

app = Celery("kshield")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):  # pragma: no cover
    print(f"Request: {self.request!r}")
