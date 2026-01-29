from django.urls import path
from .views import TiposDenunciaView

urlpatterns = [
    path("tipos-denuncia/", TiposDenunciaView.as_view(), name="tipos_denuncia"),
]
