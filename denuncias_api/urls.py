# denuncias_api/urls.py

from django.urls import path

from .views import CrearDenunciaView, MisDenunciasView, MapaDenunciasView
from .views_detalle import DenunciaDetalleView
from .views_respuestas import DenunciaRespuestasView
from .views_historial import DenunciaHistorialView

from .views_borradores import (
    BorradoresCreateView,
    BorradoresMiosView,
    BorradoresUpdateDeleteView,
    BorradoresFinalizarManualView,
)

# Subida BINARIA (guardado en BD)
from .views_borradores_media_bin import (
    BorradorSubirEvidenciaBinView,
    BorradorSubirFirmaBinView,
)

# Servir archivos BINARIOS (JWT)
from .views_archivos import (
    BorradorArchivoVerView,
    DenunciaArchivoVerView,
)

app_name = "denuncias_api"

urlpatterns = [
    # =========================================================
    # DENUNCIAS (FINAL)
    # =========================================================
    path("", CrearDenunciaView.as_view(), name="crear_denuncia"),
    path("mias/", MisDenunciasView.as_view(), name="mis_denuncias"),
    path("mapa/", MapaDenunciasView.as_view(), name="denuncias_mapa"),
    path("<uuid:denuncia_id>/detalle/", DenunciaDetalleView.as_view(), name="denuncia_detalle"),
    path("<uuid:denuncia_id>/respuestas/", DenunciaRespuestasView.as_view(), name="denuncia_respuestas"),
    path("<uuid:denuncia_id>/historial/", DenunciaHistorialView.as_view(), name="denuncia_historial"),

    # =========================================================
    # BORRADORES
    # =========================================================
    path("borradores/", BorradoresCreateView.as_view(), name="borrador_create"),
    path("borradores/mios/", BorradoresMiosView.as_view(), name="borrador_mios"),
    path("borradores/<uuid:borrador_id>/", BorradoresUpdateDeleteView.as_view(), name="borrador_put_delete"),
    path("borradores/<uuid:borrador_id>/finalizar/", BorradoresFinalizarManualView.as_view(), name="borrador_finalizar"),

    # =========================================================
    # SUBIDA DE ARCHIVOS (BINARIO) - MISMAS RUTAS PARA FLUTTER
    # =========================================================
    path(
        "borradores/<uuid:borrador_id>/evidencias/",
        BorradorSubirEvidenciaBinView.as_view(),
        name="borrador_subir_evidencia",
    ),
    path(
        "borradores/<uuid:borrador_id>/firma/",
        BorradorSubirFirmaBinView.as_view(),
        name="borrador_subir_firma",
    ),

    # =========================================================
    # VER ARCHIVOS BINARIOS (JWT)
    # =========================================================
    path(
        "borradores/archivos/<uuid:archivo_id>/",
        BorradorArchivoVerView.as_view(),
        name="borrador_archivo_ver",
    ),
    path(
        "archivos/denuncia/<uuid:archivo_id>/",
        DenunciaArchivoVerView.as_view(),
        name="denuncia_archivo_ver",
    ),
]
