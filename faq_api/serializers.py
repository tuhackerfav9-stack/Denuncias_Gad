from rest_framework import serializers
from db.models import Faq

class FaqListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Faq
        fields = ["id", "pregunta", "respuesta", "visible", "created_at", "updated_at"]

class FaqCreateUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Faq
        fields = ["pregunta", "respuesta", "visible"]
