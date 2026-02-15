# web/utils/menus.py
from django.db.models import Q
from web.models import Menus

def build_menus_for_user(user):
    qs = (
        Menus.objects
        .select_related("padre")
        .prefetch_related("permisos")
        .order_by("padre_id", "orden", "id")
    )

    if user.is_superuser:
        visibles = qs
    else:
        user_groups = user.groups.all()
        visibles = qs.filter(
            Q(permisos__isnull=True) | Q(permisos__in=user_groups)
        ).distinct()

    padres = [m for m in visibles if m.padre_id is None]

    hijos_por_padre = {}
    for m in visibles:
        if m.padre_id:
            hijos_por_padre.setdefault(m.padre_id, []).append(m)

    #  atributo permitido en templates: children
    for p in padres:
        p.children = hijos_por_padre.get(p.id, [])

    return padres
