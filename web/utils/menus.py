# web/utils/menus.py
from ..models import Menus
from django.db.models import Prefetch


def build_menus_for_user(user):
    """
    Retorna lista de menús principales (padres) con atributo dinámico:
    - menu.submenus_list = [submenus visibles]

    Reglas:
    - Superuser ve todo.
    - Si un menú/submenú no tiene permisos asignados => visible.
    - Si tiene permisos => visible solo si el user pertenece a alguno de esos grupos.
    - Si un padre no tiene url y se queda sin submenus visibles => no se muestra.
    """
    if not user.is_authenticated:
        return []

    is_superuser = user.is_superuser
    user_group_ids = set(user.groups.values_list("id", flat=True)) if not is_superuser else set()

    # Prefetch submenus + permisos (evita N+1)
    qs = (
        Menus.objects.filter(padre__isnull=True)
        .prefetch_related(
            "permisos",
            Prefetch("submenus", queryset=Menus.objects.order_by("orden").prefetch_related("permisos")),
        )
        .order_by("orden")
    )

    visibles = []

    for menu in qs:
        # --- evaluar acceso al padre
        if is_superuser:
            acceso_menu = True
        else:
            perms = list(menu.permisos.all())
            if not perms:
                acceso_menu = True
            else:
                acceso_menu = any(g.id in user_group_ids for g in perms)

        if not acceso_menu:
            continue

        # --- evaluar submenus
        submenus_visibles = []
        for sm in menu.submenus.all():
            if is_superuser:
                acceso_sm = True
            else:
                perms_sm = list(sm.permisos.all())
                if not perms_sm:
                    acceso_sm = True
                else:
                    acceso_sm = any(g.id in user_group_ids for g in perms_sm)

            if acceso_sm:
                submenus_visibles.append(sm)

        # attach para el template
        menu.submenus_list = submenus_visibles

        # si el menú padre no tiene url y no tiene submenus visibles => no mostrar
        if (not getattr(menu, "url", None)) and len(submenus_visibles) == 0:
            continue

        visibles.append(menu)

    return visibles
