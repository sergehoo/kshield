"""KAYDAN SHIELD — Communication temps réel avec les équipements.

Cette couche isole toute la logique métier de :
  * DeviceCommandQueue     : file de commandes serveur → équipement (Redis + DB)
  * RFIDEnrollmentService  : cycle de vie des sessions d'enrôlement
  * EventBus               : diffusion Channels vers front + agents
  * EquipmentHealthMonitor : ping périodique + statut connectivité

Les vues DRF n'appellent QUE ces services — pas de modèles ni Redis en direct.
"""
from .alert_service import AlertService
from .command_queue import DeviceCommandQueue
from .enrollment import RFIDEnrollmentService
from .event_bus import EventBus
from .health_monitor import EquipmentHealthMonitor
from .maintenance import PredictiveMaintenanceEngine
from .twin_service import TwinService

__all__ = [
    "AlertService",
    "DeviceCommandQueue",
    "RFIDEnrollmentService",
    "EventBus",
    "EquipmentHealthMonitor",
    "PredictiveMaintenanceEngine",
    "TwinService",
]
