from rest_framework import serializers

from .models import BLEStillnessSignal, FraudAlert, FraudInvestigation, FraudRule, FraudScoring


class FraudRuleSerializer(serializers.ModelSerializer):
    class Meta: model = FraudRule; fields = "__all__"


class FraudAlertSerializer(serializers.ModelSerializer):
    rule_code = serializers.CharField(source="rule.code", read_only=True)
    class Meta: model = FraudAlert; fields = "__all__"


class FraudInvestigationSerializer(serializers.ModelSerializer):
    class Meta: model = FraudInvestigation; fields = "__all__"


class FraudScoringSerializer(serializers.ModelSerializer):
    class Meta: model = FraudScoring; fields = "__all__"


class BLEStillnessSignalSerializer(serializers.ModelSerializer):
    class Meta: model = BLEStillnessSignal; fields = "__all__"
