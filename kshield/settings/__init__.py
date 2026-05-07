"""KAYDAN SHIELD — settings package.

Le module à importer est sélectionné via la variable d'environnement
`DJANGO_SETTINGS_MODULE` :

    - Développement : `DJANGO_SETTINGS_MODULE=kshield.settings.dev`   (par défaut)
    - Production    : `DJANGO_SETTINGS_MODULE=kshield.settings.prod`
    - Tests         : `DJANGO_SETTINGS_MODULE=kshield.settings.test` (à créer si besoin)

Si on importe directement `kshield.settings` (sans suffixe), on retombe sur dev.
"""
from .dev import *  # noqa: F401,F403
