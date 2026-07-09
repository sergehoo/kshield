"""KAYDAN SHIELD — Driver ONVIF générique.

Ce driver s'applique par défaut aux caméras qui déclarent supporter ONVIF
mais dont on ne connaît pas la marque. Utilise onvif-zeep.
"""
from __future__ import annotations

import time

from ..base import (BaseDriver, Capability, DeviceInfo, DriverResult,
                     register_driver)


@register_driver
class OnvifDriver(BaseDriver):
    vendor = "onvif"
    supported_models = ()  # fallback générique
    capabilities = (Capability.PING, Capability.GET_INFO)

    def _client(self):
        try:
            from onvif import ONVIFCamera
        except ImportError:
            return None
        try:
            return ONVIFCamera(
                self.device.ip_address,
                self.device.model.spec.get("onvif_port", 80),
                self.device.model.spec.get("username", "admin"),
                self.device.model.spec.get("password", ""),
            )
        except Exception:
            return None

    def connect(self):    return DriverResult(ok=bool(self.device.ip_address))
    def disconnect(self): return DriverResult(ok=True)

    def ping(self) -> DriverResult:
        cam = self._client()
        if cam is None:
            return DriverResult(ok=False, detail="onvif-zeep non dispo")
        t0 = time.perf_counter()
        try:
            info = cam.devicemgmt.GetDeviceInformation()
            return DriverResult(ok=True, detail=f"{info.Manufacturer} {info.Model}",
                                 data={"latency_ms": int((time.perf_counter() - t0) * 1000)})
        except Exception as exc:
            return DriverResult(ok=False, detail=str(exc))

    def get_info(self) -> DeviceInfo:
        info = super().get_info()
        cam = self._client()
        if cam is None:
            return info
        try:
            d = cam.devicemgmt.GetDeviceInformation()
            info.brand = d.Manufacturer or info.brand
            info.model = d.Model or info.model
            info.firmware = d.FirmwareVersion or info.firmware
            info.serial = d.SerialNumber or info.serial
            info.hardware = d.HardwareId or info.hardware
            info.raw = {"raw": str(d)}
        except Exception:
            pass
        return info
