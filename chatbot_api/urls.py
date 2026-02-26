from django.urls import path, include
from .views import ChatbotMessageView, ChatbotStartView

urlpatterns = [
    path("start/", ChatbotStartView.as_view(), name="chatbot_start"),
    path("message/", ChatbotMessageView.as_view(), name="chatbot_message"),

    # V2
    path("", include("chatbot_api.urls_mejorado")),
]