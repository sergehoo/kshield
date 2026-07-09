"""Management command : lance le listener MQTT en foreground.

Usage :
    python manage.py mqtt_listen --host localhost --port 1883

En prod : lancer via systemd ou docker-compose.
"""
from __future__ import annotations

import signal
import time

from django.conf import settings
from django.core.management.base import BaseCommand

from devices.services.mqtt_listener import MqttListener


class Command(BaseCommand):
    help = "Écoute les topics MQTT rfid/ble et injecte les scans dans Kaydan Shield."

    def add_arguments(self, parser):
        parser.add_argument("--host", default=getattr(settings, "MQTT_HOST", "localhost"))
        parser.add_argument("--port", type=int,
                            default=getattr(settings, "MQTT_PORT", 1883))
        parser.add_argument("--username", default=getattr(settings, "MQTT_USERNAME", None))
        parser.add_argument("--password", default=getattr(settings, "MQTT_PASSWORD", None))
        parser.add_argument("--topic", default="kshield/#")
        parser.add_argument("--tls", action="store_true",
                             default=getattr(settings, "MQTT_TLS", False))
        parser.add_argument("--ca-file",
                             default=getattr(settings, "MQTT_CA_FILE", None))

    def handle(self, *args, **opts):
        listener = MqttListener(
            host=opts["host"], port=opts["port"],
            username=opts["username"], password=opts["password"],
            topic_prefix=opts["topic"],
            tls=opts["tls"], ca_file=opts["ca_file"],
        )
        self.stdout.write(self.style.NOTICE(
            f"MQTT listen {opts['host']}:{opts['port']} topic={opts['topic']}",
        ))
        listener.start()

        def _shutdown(*_):
            self.stdout.write(self.style.WARNING("Shutdown MQTT…"))
            listener.stop()
            raise SystemExit(0)

        signal.signal(signal.SIGINT, _shutdown)
        signal.signal(signal.SIGTERM, _shutdown)

        while True:
            time.sleep(60)
