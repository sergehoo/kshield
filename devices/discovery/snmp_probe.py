"""KAYDAN SHIELD — Discovery SNMP (walk minimal OID sysDescr / sysName)."""
from __future__ import annotations

import logging
from typing import Optional

from .base import DiscoveredDevice, ProtocolProbe

logger = logging.getLogger(__name__)

# OIDs minimaux (MIB-II)
OID_SYSDESCR  = "1.3.6.1.2.1.1.1.0"
OID_SYSNAME   = "1.3.6.1.2.1.1.5.0"
OID_SYSOBJECT = "1.3.6.1.2.1.1.2.0"


class SnmpProbe(ProtocolProbe):
    name = "snmp"

    def scan(self, ip_range: Optional[list[str]] = None) -> list[DiscoveredDevice]:
        if not ip_range:
            return []
        try:
            from pysnmp.hlapi import (CommunityData, ContextData, ObjectIdentity,
                                        ObjectType, SnmpEngine, UdpTransportTarget,
                                        getCmd)
        except ImportError:
            logger.info("pysnmp non installé — skip SNMP discovery")
            return []

        found: list[DiscoveredDevice] = []
        community = "public"     # à passer en param plus tard
        engine = SnmpEngine()

        for ip in ip_range[:256]:   # cap sécurité
            try:
                err_ind, err_stat, err_idx, var_binds = next(getCmd(
                    engine, CommunityData(community, mpModel=1),
                    UdpTransportTarget((ip, 161), timeout=1, retries=0),
                    ContextData(),
                    ObjectType(ObjectIdentity(OID_SYSDESCR)),
                    ObjectType(ObjectIdentity(OID_SYSNAME)),
                ))
                if err_ind or err_stat:
                    continue
                sysdescr = str(var_binds[0][1]) if var_binds else ""
                sysname  = str(var_binds[1][1]) if len(var_binds) > 1 else ""

                d = DiscoveredDevice(
                    ip=ip, hostname=sysname, protocols_detected=["snmp"],
                )
                d.protocols_raw["snmp"] = {"sysDescr": sysdescr, "sysName": sysname}
                # Guess vendor par sysDescr
                low = sysdescr.lower()
                for vendor in ("hikvision", "dahua", "axis", "zkteco", "suprema",
                                "bosch", "hid", "cisco", "hp", "juniper"):
                    if vendor in low:
                        d.vendor = vendor
                        break
                found.append(d)
            except Exception:
                continue
        return found
