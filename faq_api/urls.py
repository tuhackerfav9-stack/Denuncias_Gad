from django.urls import path
from .views import FaqListCreateView, FaqDetailView

urlpatterns = [
    path("", FaqListCreateView.as_view(), name="faq_list_create"),
    path("<int:faq_id>/", FaqDetailView.as_view(), name="faq_detail"),
]
