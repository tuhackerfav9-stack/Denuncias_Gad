from rest_framework.permissions import BasePermission

def get_claim(request, key: str, default=None):
    token = getattr(request, "auth", None)
    if token is None:
        return default
    try:
        return token.get(key, default)
    except Exception:
        return default

class IsAdminTIC(BasePermission):
    def has_permission(self, request, view):
        tipo = get_claim(request, "tipo")
        # ajusta este string a como lo tengas en tus tokens:
        # ej: "admin", "tic", "admin_tic"
        return tipo in ["admin_tic", "tic", "admin"]
