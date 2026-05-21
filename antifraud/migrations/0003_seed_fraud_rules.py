"""Data migration : seed des FraudRule par défaut pour KAYDAN.

Crée les 6 règles canoniques (BADGE_LOAN, BADGE_TWICE_IN, OUT_OF_HOURS,
GHOST_HELMET, BADGE_WITHOUT_HELMET, OUTSIDE_GEOFENCE) pour le tenant KAYDAN
s'il existe. Idempotent — get_or_create par (tenant, code).
"""
from django.db import migrations


DEFAULT_RULES = [
    {
        "code": "BADGE_LOAN", "severity": "critical",
        "name": "Prêt de badge",
        "description": ("Le même badge a été utilisé par 2 holders distincts "
                          "sur la même journée — suspicion forte de prêt."),
        "parameters": {},
    },
    {
        "code": "BADGE_TWICE_IN", "severity": "warning",
        "name": "Badge utilisé 2x à l'entrée",
        "description": ("Plusieurs scans 'in' consécutifs sans 'out' sur le "
                          "même site dans les 60 minutes."),
        "parameters": {"window_minutes": 60},
    },
    {
        "code": "OUT_OF_HOURS", "severity": "warning",
        "name": "Accès hors heures",
        "description": "Scan hors des plages horaires autorisées du site.",
        "parameters": {"start": "06:00", "end": "20:00"},
    },
    {
        "code": "GHOST_HELMET", "severity": "warning",
        "name": "Casque sans badge",
        "description": ("Un casque BLE a été détecté sur site sans badge UHF "
                          "associé — casque perdu, prêté, ou anomalie."),
        "parameters": {},
    },
    {
        "code": "BADGE_WITHOUT_HELMET", "severity": "critical",
        "name": "Ouvrier sans casque",
        "description": ("Badge ouvrier scanné sans casque BLE couplé — "
                          "risque sécurité BTP (non traçable en cas de chute "
                          "ou de malaise). Le superviseur doit acquitter."),
        "parameters": {},
    },
    {
        "code": "OUTSIDE_GEOFENCE", "severity": "critical",
        "name": "Scan hors zone géographique",
        "description": ("Le scan a été géolocalisé hors du polygone du site "
                          "— terminal probablement déplacé ou GPS spoofé."),
        "parameters": {},
    },
]


def seed_rules(apps, schema_editor):
    Tenant = apps.get_model("core", "Tenant")
    FraudRule = apps.get_model("antifraud", "FraudRule")

    for tenant in Tenant.objects.filter(is_active=True):
        for rule_data in DEFAULT_RULES:
            FraudRule.objects.get_or_create(
                tenant=tenant,
                code=rule_data["code"],
                defaults={
                    "name": rule_data["name"],
                    "severity": rule_data["severity"],
                    "description": rule_data["description"],
                    "parameters": rule_data["parameters"],
                    "is_active": True,
                },
            )


def remove_rules(apps, schema_editor):
    """Reverse migration — supprime uniquement les rules KAYDAN par défaut."""
    FraudRule = apps.get_model("antifraud", "FraudRule")
    FraudRule.objects.filter(code__in=[r["code"] for r in DEFAULT_RULES]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("antifraud", "0002_initial"),
        ("core", "0001_initial"),
    ]
    operations = [
        migrations.RunPython(seed_rules, remove_rules),
    ]
