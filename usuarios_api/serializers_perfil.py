from rest_framework import serializers


class PerfilResponseSerializer(serializers.Serializer):
    # Usuario
    uid = serializers.CharField()
    correo = serializers.EmailField()
    nombres = serializers.CharField(allow_blank=True, required=False)
    apellidos = serializers.CharField(allow_blank=True, required=False)
    telefono = serializers.CharField(allow_blank=True, required=False)

    # Ciudadano (extras)
    direccion = serializers.CharField(allow_blank=True, required=False)
    fecha_nacimiento = serializers.DateField(required=False, allow_null=True)


class PerfilUpdateSerializer(serializers.Serializer):
    # Campos editables (MVP)
    nombres = serializers.CharField(required=False, allow_blank=True)
    apellidos = serializers.CharField(required=False, allow_blank=True)
    telefono = serializers.CharField(required=False, allow_blank=True)

    direccion = serializers.CharField(required=False, allow_blank=True)
    fecha_nacimiento = serializers.DateField(required=False, allow_null=True)

    # Si quieres permitir editar correo, descomenta:
    # correo = serializers.EmailField(required=False)
