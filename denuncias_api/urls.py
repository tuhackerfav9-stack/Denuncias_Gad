# denuncias_api/urls.py
from django.urls import path

# Denuncias (ciudadano)
from .views import CrearDenunciaView, MisDenunciasView, MapaDenunciasView
from .views_detalle import DenunciaDetalleView
from .views_respuestas import DenunciaRespuestasView
from .views_historial import DenunciaHistorialView

# Borradores (MVP)
from .views_borradores import (
    BorradoresCreateView,
    BorradoresMiosView,
    BorradoresUpdateDeleteView,
    BorradoresFinalizarManualView,
)

# Media de borradores
from .views_borradores_media import (
    BorradorSubirEvidenciaView,
    BorradorSubirFirmaView,
)

app_name = "denuncias_api"

urlpatterns = [
    # =========================
    # Denuncias finales
    # Base: /api/denuncias/
    # =========================
    path("", CrearDenunciaView.as_view(), name="crear_denuncia"),
    path("mias/", MisDenunciasView.as_view(), name="mis_denuncias"),
    path("mapa/", MapaDenunciasView.as_view(), name="denuncias_mapa"),

    # Detalle / respuestas / historial
    path("<uuid:denuncia_id>/detalle/", DenunciaDetalleView.as_view(), name="denuncia_detalle"),
    path("<uuid:denuncia_id>/respuestas/", DenunciaRespuestasView.as_view(), name="denuncia_respuestas"),
    path("<uuid:denuncia_id>/historial/", DenunciaHistorialView.as_view(), name="denuncia_historial"),

    # =========================
    # Borradores
    # =========================
    path("borradores/", BorradoresCreateView.as_view(), name="borrador_create"),
    path("borradores/mios/", BorradoresMiosView.as_view(), name="borrador_mios"),
    path("borradores/<uuid:borrador_id>/", BorradoresUpdateDeleteView.as_view(), name="borrador_put_delete"),
    path("borradores/<uuid:borrador_id>/finalizar/", BorradoresFinalizarManualView.as_view(), name="borrador_finalizar"),

    # Media (borradores)
    path("borradores/<uuid:borrador_id>/evidencias/", BorradorSubirEvidenciaView.as_view(), name="borrador_subir_evidencia"),
    path("borradores/<uuid:borrador_id>/firma/", BorradorSubirFirmaView.as_view(), name="borrador_subir_firma"),
]
