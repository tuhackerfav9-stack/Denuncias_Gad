from django.urls import path
from .views_chatbot_mejorado import (
    ChatbotStartV2View,
    ChatbotMessageV2View,
    ChatbotTiposDenunciaV2,
)

urlpatterns = [
    path("v2/start/", ChatbotStartV2View.as_view(), name="chatbot_start_v2"),
    path("v2/message/", ChatbotMessageV2View.as_view(), name="chatbot_message_v2"),
    path("v2/tipos/", ChatbotTiposDenunciaV2.as_view(), name="chatbot_tipos_v2"),
]
