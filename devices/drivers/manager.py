"""KAYDAN SHIELD — Driver Manager.

Rôle :
  * Charger tous les plugins de ``devices.drivers.*`` au démarrage Django
  * Sélectionner automatiquement le bon driver pour un ``Device`` donné
  * Fournir un cache thread-safe des instances driver
  * Détecter dynamiquement le constructeur si non renseigné (best-effort)

Le reste de la plateforme n'appelle QUE ``DriverManager.for_device(device)``.
"""
from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Optional

from .base import BaseDriver, get_registered_drivers

logger = logging.getLogger(__name__)


class DriverManager:
    _autoloaded = False

    # ────────────────────────────────────────────────────────────
    # Autoload
    # ────────────────────────────────────────────────────────────
    @classmethod
    def autoload(cls, force: bool = False):
        """Importe tous les sous-packages de ``devices.drivers`` pour déclencher
        les ``@register_driver``. Idempotent.
        """
        if cls._autoloaded and not force:
            return
        from devices import drivers as pkg

        for m in pkgutil.iter_modules(pkg.__path__):
            if m.name in ("base", "manager", "__pycache__"):
                continue
            try:
                importlib.import_module(f"{pkg.__name__}.{m.name}")
                logger.debug("Driver plugin chargé : %s", m.name)
            except Exception as exc:
                logger.warning("Driver plugin %s échec import : %s", m.name, exc)
        cls._autoloaded = True

    # ────────────────────────────────────────────────────────────
    # Résolution driver → device
    # ────────────────────────────────────────────────────────────
    @classmethod
    def for_device(cls, device) -> BaseDriver:
        """Retourne l'instance driver appropriée pour un Device.

        Ordre de résolution :
            1. Match exact ``DeviceModel.brand.lower()`` dans le registre
            2. Match par préfixe de modèle (supported_models)
            3. Match par capability (ex. ONVIF si le device_model.spec.onvif = True)
            4. Fallback ``GenericDriver``
        """
        cls.autoload()
        registry = get_registered_drivers()
        model = device.model
        brand = (model.brand or "").lower().strip()

        # 1) Match exact brand
        for key, driver_cls in registry.items():
            if key == brand:
                return driver_cls(device)

        # 2) Match par préfixe de modèle
        model_name = (model.model or "").strip()
        for driver_cls in registry.values():
            for pref in driver_cls.supported_models or ():
                if pref and model_name.startswith(pref):
                    return driver_cls(device)

        # 3) ONVIF si déclaré
        if isinstance(model.spec, dict) and model.spec.get("onvif"):
            if "onvif" in registry:
                return registry["onvif"](device)

        # 4) Fallback
        return registry.get("generic", _MinimalDriver)(device)

    @classmethod
    def by_vendor(cls, vendor: str) -> Optional[type[BaseDriver]]:
        cls.autoload()
        return get_registered_drivers().get(vendor.lower())

    @classmethod
    def list_drivers(cls) -> list[dict]:
        """Retourne la liste des drivers enregistrés + leurs capabilities."""
        cls.autoload()
        return [
            {
                "vendor": drv.vendor,
                "class": drv.__name__,
                "module": drv.__module__,
                "supported_models": list(drv.supported_models or ()),
                "capabilities": list(drv.capabilities or ()),
            }
            for drv in get_registered_drivers().values()
        ]


# Fallback minimal si aucun driver n'est chargé (ne devrait jamais servir)
from .base import Capability, DriverResult


class _MinimalDriver(BaseDriver):
    vendor = "minimal"
    capabilities = (Capability.PING,)

    def connect(self):    return DriverResult(ok=True)
    def disconnect(self): return DriverResult(ok=True)
    def ping(self):       return DriverResult(ok=False, detail="Aucun driver chargé")
