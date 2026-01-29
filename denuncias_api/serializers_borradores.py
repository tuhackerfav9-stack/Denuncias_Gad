from rest_framework import serializers


class DenunciaBorradorCreateSerializer(serializers.Serializer):
    tipo_denuncia_id = serializers.IntegerField()
    descripcion = serializers.CharField(min_length=10)
    referencia = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    latitud = serializers.FloatField()
    longitud = serializers.FloatField()
    direccion_texto = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    # opcional
    origen = serializers.ChoiceField(choices=["formulario", "chat"], required=False, default="formulario")


class DenunciaBorradorUpdateSerializer(serializers.Serializer):
    # permitimos editar solo estos campos (y solo si no caducó)
    tipo_denuncia_id = serializers.IntegerField(required=False)
    descripcion = serializers.CharField(required=False, min_length=10)
    referencia = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    latitud = serializers.FloatField(required=False)
    longitud = serializers.FloatField(required=False)
    direccion_texto = serializers.CharField(required=False, allow_blank=True, allow_null=True)


class DenunciaBorradorFinalizarSerializer(serializers.Serializer):
    # en finalize puedes mandar firma y evidencias
    firma_base64 = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    firma_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    evidencias = serializers.ListField(
        required=False,
        child=serializers.DictField(),
        allow_empty=True
    )

    # opcional: si quieres forzar enviar antes de los 5 min
    force = serializers.BooleanField(required=False, default=False)


class BorradorSerializer(serializers.Serializer):
    tipo_denuncia_id = serializers.IntegerField()
    descripcion = serializers.CharField(min_length=10)
    referencia = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    latitud = serializers.FloatField()
    longitud = serializers.FloatField()
    direccion_texto = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    origen = serializers.ChoiceField(choices=["formulario", "chat"], required=False, default="formulario")

    # MVP: deja listo para luego
    # firma_base64 = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # evidencia_url = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    # evidencia_tipo = serializers.ChoiceField(choices=["foto","video","audio","documento"], required=False)
