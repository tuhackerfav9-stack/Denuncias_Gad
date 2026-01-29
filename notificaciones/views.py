from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import DeviceToken
from denuncias_api.utils import get_claim

class RegisterDeviceTokenView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        uid = get_claim(request, "uid")
        tipo = get_claim(request, "tipo")

        if not uid or tipo != "ciudadano":
            return Response({"detail": "Solo ciudadanos"}, status=403)

        token = (request.data.get("fcm_token") or "").strip()
        platform = (request.data.get("platform") or "android").strip().lower()

        if not token:
            return Response({"detail": "fcm_token es obligatorio"}, status=400)

        obj, _ = DeviceToken.objects.update_or_create(
            fcm_token=token,
            defaults={"usuario_id": uid, "platform": platform, "updated_at": timezone.now()},
        )

        return Response({"detail": "Token guardado", "id": str(obj.id)}, status=200)
