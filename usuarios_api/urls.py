from django.urls import path
from .views import (
    LoginView,
    RegisterPaso1View, RegisterEnviarCodigoView, RegisterVerificarCodigoView,
    RegisterFechaView, RegisterDocumentosView, RegisterFinalizarView
)
from .views_password_reset import (ResetEnviarCodigoView,ResetVerificarCodigoView,ResetCambiarPasswordView)
from .views_perfil import PerfilView
from .views_password_change import PasswordChangeView

urlpatterns = [
    path("login/", LoginView.as_view()),
    path("register/paso1/", RegisterPaso1View.as_view()),
    path("register/paso2/enviar-codigo/", RegisterEnviarCodigoView.as_view()),
    path("register/paso2/verificar-codigo/", RegisterVerificarCodigoView.as_view()),
    path("register/paso3/fecha/", RegisterFechaView.as_view()),
    path("register/paso4/documentos/", RegisterDocumentosView.as_view()),
    path("register/paso5/finalizar/", RegisterFinalizarView.as_view()),
    path("password-reset/paso1/enviar-codigo/", ResetEnviarCodigoView.as_view()),
    path("password-reset/paso2/verificar-codigo/", ResetVerificarCodigoView.as_view()),
    path("password-reset/paso3/cambiar-password/", ResetCambiarPasswordView.as_view()),
    path("perfil/", PerfilView.as_view(), name="perfil"),
    path("password/change/", PasswordChangeView.as_view()),

]
