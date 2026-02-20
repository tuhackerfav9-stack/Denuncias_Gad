from django.urls import path
from .views import ChatbotMessageView, ChatbotStartView  # tu viejo

from django.urls import path, include

urlpatterns = [
    path("start/", ChatbotStartView.as_view(), name="chatbot_start"),
    path("message/", ChatbotMessageView.as_view(), name="chatbot_message"),

    # ✅ NUEVO (mejorado)
    path("", include("chatbot_api.urls_mejorado")),
]
