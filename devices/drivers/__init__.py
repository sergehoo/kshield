"""KAYDAN SHIELD — Driver Framework.

Chaque constructeur est isolé dans un sous-package (ex. ``devices/drivers/zkteco/``).
Le ``DriverManager`` (voir ``.manager``) charge tous les plugins au démarrage et
sélectionne le bon selon le ``DeviceModel.brand`` du ``Device``.

Le reste de la plateforme NE DOIT JAMAIS importer directement un module vendor —
uniquement ``from devices.drivers import DriverManager, BaseDriver``.
"""
from .base import (BaseDriver, Capability, DeviceEvent, DeviceInfo, DeviceStatus,
                    DriverResult, get_registered_drivers, register_driver)
from .manager import DriverManager

__all__ = [
    "BaseDriver", "Capability",
    "DeviceEvent", "DeviceInfo", "DeviceStatus", "DriverResult",
    "DriverManager",
    "get_registered_drivers", "register_driver",
]
