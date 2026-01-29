from rest_framework import serializers
from db.models import Denuncias

class DenunciaCreateSerializer(serializers.Serializer):
    tipo_denuncia_id = serializers.IntegerField()
    descripcion = serializers.CharField()
    referencia = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    latitud = serializers.FloatField()
    longitud = serializers.FloatField()
    direccion_texto = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    origen = serializers.ChoiceField(choices=["formulario", "chat"], required=False, default="formulario")
