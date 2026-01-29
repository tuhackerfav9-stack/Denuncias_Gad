# web/context_processors.py
from .utils.menus import build_menus_for_user

def menu_context(request):
    if not request.user.is_authenticated:
        return {"menus_principales": []}

    return {"menus_principales": build_menus_for_user(request.user)}
