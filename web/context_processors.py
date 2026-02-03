from web.utils.menus import build_menus_for_user

def menus_principales(request):
    if request.user.is_authenticated:
        return {"menus_principales": build_menus_for_user(request.user)}
    return {"menus_principales": []}
