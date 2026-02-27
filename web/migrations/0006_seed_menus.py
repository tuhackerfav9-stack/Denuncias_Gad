from django.db import migrations


def seed_data(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Menus = apps.get_model("web", "Menus")

    # =========================
    # 1) Grupos
    # =========================
    g_admin, _ = Group.objects.update_or_create(name="TICS_ADMIN")
    g_func, _ = Group.objects.update_or_create(name="FUNCIONARIO")

    # =========================
    # 2) Menús raíz
    # =========================
    menus_data = [
        (1,  "Denuncias", None, "mdi mdi-clipboard-text", 1, None),
        (4,  "Catalogos", None, "mdi mdi-apps", 2, None),
        (8,  "FAQ", None, "mdi mdi-help-circle", 3, None),
        (10, "Funcionarios", None, "mdi mdi-account-group", 4, None),
        (12, "Administracion", None, "mdi mdi-shield-key", 98, None),
        (26, "Página Web", "web:public_home", "mdi mdi-application", 99, None),
    ]

    menu_objs = {}

    for mid, nombre, url, icono, orden, padre_id in menus_data:
        obj, _ = Menus.objects.update_or_create(
            id=mid,
            defaults={
                "nombre": nombre,
                "url": url,
                "icono": icono,
                "orden": orden,
                "padre": None,
            },
        )
        menu_objs[mid] = obj

    # =========================
    # 3) Submenús
    # =========================
    submenus_data = [
        (2,  "Listado", "web:denuncia_list", None, 1, 1),
        (3,  "Mis denuncias", "web:mis_denuncias", None, 2, 1),
        (5,  "Departamentos", "web:departamento_list", "bi bi-building", 1, 4),
        (6,  "Tipos de denuncia", "web:tipos_denuncia_list", "bi bi-tags", 2, 4),
        (7,  "Tipo <-> Departamento", "web:tipo_denuncia_departamento_list", "bi bi-diagram-3", 3, 4),
        (9,  "Preguntas frecuentes", "web:faq_list", None, 1, 8),
        (11, "Listado", "web:unified_user_list", None, 1, 10),
        (14, "Grupos", "web:grupo_list", "bi bi-people", 2, 12),
    ]

    for mid, nombre, url, icono, orden, padre_id in submenus_data:
        padre = menu_objs.get(padre_id)
        obj, _ = Menus.objects.update_or_create(
            id=mid,
            defaults={
                "nombre": nombre,
                "url": url,
                "icono": icono,
                "orden": orden,
                "padre": padre,
            },
        )
        menu_objs[mid] = obj

    # =========================
    # 4) Permisos (ManyToMany)
    # =========================

    # TICS_ADMIN ve todo
    for menu in Menus.objects.all():
        menu.permisos.add(g_admin)

    # FUNCIONARIO ve solo algunos
    funcionario_menus_ids = [1, 2, 3, 26]

    for mid in funcionario_menus_ids:
        if mid in menu_objs:
            menu_objs[mid].permisos.add(g_func)


class Migration(migrations.Migration):

    dependencies = [
        ("web", "0005_alter_menus_options_alter_menus_icono_and_more"),  # cambia por tu última real
        ("auth", "0012_alter_user_first_name_max_length"),
    ]

    operations = [
        migrations.RunPython(seed_data, migrations.RunPython.noop),
    ]