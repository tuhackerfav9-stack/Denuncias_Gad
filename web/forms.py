# web/forms.py
from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin as DjangoPermissionRequiredMixin
from django.contrib.auth.models import Group, Permission, User
from django.shortcuts import render
from django.utils import timezone
from django_select2.forms import ModelSelect2MultipleWidget, ModelSelect2Widget

from db.models import (
    DenunciaAsignaciones,
    DenunciaRespuestas,
    Denuncias,
    Departamentos,
    Faq,
    Funcionarios,
    TipoDenunciaDepartamento,
    TiposDenuncia,
)
from .models import Menus

# =========================
# Choices (alineado a tu ENUM denuncia_estado)
# =========================
ESTADO_CHOICES = [
    ("pendiente", "Pendiente"),
    ("en_revision", "En revisión"),
    ("asignada", "Asignada"),
    ("en_proceso", "En proceso"),
    ("resuelta", "Resuelta"),
    ("rechazada", "Rechazada"),
]

# =========================
# Mixins
# =========================
class PermissionRequiredMixin(DjangoPermissionRequiredMixin):
    """Renderiza template 403 en vez de lanzar excepción"""

    def handle_no_permission(self):
        return render(self.request, "errors/403.html", status=403)


class CrudMessageMixin:
    """Mensajes automáticos en Create/Update/Delete (para iziToast con messages)"""

    def get_create_message(self, obj):
        return f"{self.model._meta.verbose_name} creado correctamente"

    def get_update_message(self, obj):
        return f"{self.model._meta.verbose_name} actualizado correctamente"

    def get_delete_message(self, obj):
        return f"{self.model._meta.verbose_name} eliminado correctamente"

    def form_valid(self, form):
        response = super().form_valid(form)

        # OJO: CreateView/UpdateView están en views.py, pero aquí solo usamos isinstance por el MRO.
        from django.views.generic.edit import CreateView, UpdateView

        if isinstance(self, CreateView):
            messages.success(self.request, self.get_create_message(self.object))
        elif isinstance(self, UpdateView):
            messages.success(self.request, self.get_update_message(self.object))

        return response

    def delete(self, request, *args, **kwargs):
        obj = self.get_object()
        messages.success(request, self.get_delete_message(obj))
        return super().delete(request, *args, **kwargs)

# =========================
# Menús
# =========================
#class MenuForm(forms.ModelForm):
#    class Meta:
#        model = Menus
#        fields = ["nombre", "url", "icono", "padre", "orden", "permisos"]
#        widgets = {
#            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre del menú"}),
#            "url": forms.TextInput(
#                attrs={"class": "form-control", "placeholder": "URL o nombre de la ruta (e.g. web:home)"}
#            ),
#            "icono": forms.TextInput(attrs={"class": "form-control", "placeholder": "Clase de icono (bi bi-house)"}),
#            "padre": ModelSelect2Widget(
#                model=Menus,
#                search_fields=["nombre__icontains"],
#                attrs={"class": "form-control"},
#            ),
#            "orden": forms.NumberInput(attrs={"class": "form-control"}),
#            "permisos": ModelSelect2MultipleWidget(
#                model=Permission,
#                search_fields=["name__icontains"],
#                attrs={"class": "form-control"},
#            ),
#        }
from django import forms
from django.contrib.auth.models import Group
from django_select2.forms import ModelSelect2MultipleWidget, ModelSelect2Widget
from .models import Menus

ICON_CHOICES = [
    ("", "--- Sin icono ---"),

    # Navegación / Inicio
    ("mdi mdi-home", "Inicio"),
    ("mdi mdi-view-dashboard", "Dashboard"),
    ("mdi mdi-menu", "Menú"),
    ("mdi mdi-menu-open", "Menú abierto"),
    ("mdi mdi-sitemap", "Mapa del sitio"),
    ("mdi mdi-application", "Aplicación"),
    ("mdi mdi-apps", "Aplicaciones"),
    ("mdi mdi-tab", "Pestañas"),
    ("mdi mdi-tab-plus", "Nueva pestaña"),
    ("mdi mdi-book-open-page-variant", "Manual"),

    # Denuncias / Gestión
    ("mdi mdi-alert-octagon", "Denuncia"),
    ("mdi mdi-alert-circle", "Incidencia"),
    ("mdi mdi-file-document-alert", "Denuncias registradas"),
    ("mdi mdi-clipboard-text", "Formulario"),
    ("mdi mdi-clipboard-check", "Validación"),
    ("mdi mdi-clipboard-list", "Listado"),
    ("mdi mdi-check-circle", "Aprobado"),
    ("mdi mdi-close-circle", "Rechazado"),
    ("mdi mdi-progress-clock", "En proceso"),
    ("mdi mdi-timer-sand", "Pendiente"),

    # Acciones CRUD
    ("mdi mdi-plus-box", "Crear"),
    ("mdi mdi-pencil", "Editar"),
    ("mdi mdi-content-save", "Guardar"),
    ("mdi mdi-eye", "Ver"),
    ("mdi mdi-trash-can", "Eliminar"),
    ("mdi mdi-delete-forever", "Eliminar definitivo"),
    ("mdi mdi-refresh", "Actualizar"),
    ("mdi mdi-reload", "Recargar"),
    ("mdi mdi-backup-restore", "Restaurar"),
    ("mdi mdi-undo", "Deshacer"),

    # Usuarios / Seguridad
    ("mdi mdi-account", "Usuario"),
    ("mdi mdi-account-group", "Usuarios"),
    ("mdi mdi-account-cog", "Usuario y ajustes"),
    ("mdi mdi-shield-account", "Rol"),
    ("mdi mdi-shield-key", "Permisos"),
    ("mdi mdi-lock", "Bloqueado"),
    ("mdi mdi-lock-open-variant", "Desbloqueado"),
    ("mdi mdi-login", "Iniciar sesión"),
    ("mdi mdi-logout", "Cerrar sesión"),
    ("mdi mdi-key", "Clave"),

    # Comunicación / Notificaciones
    ("mdi mdi-bell", "Notificaciones"),
    ("mdi mdi-bell-alert", "Alerta"),
    ("mdi mdi-email", "Correo"),
    ("mdi mdi-email-outline", "Correo (bandeja)"),
    ("mdi mdi-message-text", "Mensajes"),
    ("mdi mdi-chat", "Chat"),
    ("mdi mdi-phone", "Teléfono"),
    ("mdi mdi-whatsapp", "WhatsApp"),
    ("mdi mdi-send", "Enviar"),
    ("mdi mdi-inbox", "Bandeja de entrada"),

    # Ubicación / Mapa
    ("mdi mdi-map-marker", "Ubicación"),
    ("mdi mdi-map", "Mapa"),
    ("mdi mdi-map-search", "Buscar en mapa"),
    ("mdi mdi-crosshairs-gps", "GPS"),
    ("mdi mdi-radar", "Zona"),
    ("mdi mdi-map-marker-radius", "Radio"),
    ("mdi mdi-home-map-marker", "Dirección"),
    ("mdi mdi-directions", "Rutas"),
    ("mdi mdi-compass", "Brújula"),
    ("mdi mdi-flag", "Bandera"),

    # Evidencias / Archivos
    ("mdi mdi-paperclip", "Adjuntos"),
    ("mdi mdi-file", "Archivo"),
    ("mdi mdi-file-document", "Documento"),
    ("mdi mdi-file-pdf-box", "PDF"),
    ("mdi mdi-image", "Imagen"),
    ("mdi mdi-camera", "Cámara"),
    ("mdi mdi-video", "Video"),
    ("mdi mdi-folder", "Carpeta"),
    ("mdi mdi-folder-open", "Carpeta abierta"),
    ("mdi mdi-cloud-upload", "Subir"),

    # Reportes / Estadística
    ("mdi mdi-chart-bar", "Reporte"),
    ("mdi mdi-chart-line", "Gráfico"),
    ("mdi mdi-chart-pie", "Estadísticas"),
    ("mdi mdi-finance", "Indicadores"),
    ("mdi mdi-counter", "Contador"),
    ("mdi mdi-trending-up", "Crecimiento"),
    ("mdi mdi-trending-down", "Disminución"),
    ("mdi mdi-calendar", "Calendario"),
    ("mdi mdi-calendar-month", "Mes"),
    ("mdi mdi-clock-outline", "Historial"),

    # Organización / Departamentos
    ("mdi mdi-domain", "Institución"),
    ("mdi mdi-office-building", "Edificio"),
    ("mdi mdi-briefcase", "Departamento"),
    ("mdi mdi-briefcase-check", "Gestión"),
    ("mdi mdi-account-tie", "Funcionario"),
    ("mdi mdi-account-badge", "Credenciales"),
    ("mdi mdi-badge-account", "Identificación"),
    ("mdi mdi-vector-combine", "Asignación"),
    ("mdi mdi-swap-horizontal", "Transferencia"),
    ("mdi mdi-timeline-text", "Seguimiento"),

    # Herramientas / Config
    ("mdi mdi-cog", "Configuración"),
    ("mdi mdi-tune", "Ajustes"),
    ("mdi mdi-wrench", "Herramientas"),
    ("mdi mdi-database", "Base de datos"),
    ("mdi mdi-server", "Servidor"),
    ("mdi mdi-lan", "Red"),
    ("mdi mdi-api", "API"),
    ("mdi mdi-shield-check", "Seguridad"),
    ("mdi mdi-bug", "Errores"),
    ("mdi mdi-help-circle", "Ayuda"),
]


# =========================
# Grupos
# =========================

class MenuForm(forms.ModelForm):
    icono = forms.ChoiceField(
        choices=ICON_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    class Meta:
        model = Menus
        fields = ["nombre", "url", "icono", "padre", "orden", "permisos"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Denuncias"}),
            "url": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: web:denuncia_list"}),
            "padre": ModelSelect2Widget(
                model=Menus,
                search_fields=["nombre__icontains"],
                attrs={"class": "form-control"},
            ),
            "orden": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "permisos": ModelSelect2MultipleWidget(
                model=Group,
                search_fields=["name__icontains"],
                attrs={"class": "form-control"},
            ),
        }


class GrupoFuncionariosWidget(ModelSelect2MultipleWidget):
    model = User
    search_fields = [
        "username__icontains",
        "email__icontains",
        "first_name__icontains",
        "last_name__icontains",
    ]

class GrupoForm(forms.ModelForm):
    funcionarios = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        required=False,
        label="Funcionarios",
        widget=GrupoFuncionariosWidget(
            attrs={
                "class": "form-control",
                "data-placeholder": "Buscar funcionarios...",
                "style": "width: 100%;",
            }
        )
    )

    name = forms.CharField(
        required=True,
        label="Nombre",
        widget=forms.TextInput(attrs={"placeholder": "Ej: Seguridad Ciudadana"})
    )

    class Meta:
        model = Group
        fields =  ["name", "funcionarios"] # seguimos sin permissions

        widgets = {
            "name": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Ej: Seguridad Ciudadana",
                "autocomplete": "off",
            })
        }

    def __init__(self, *args, **kwargs):
        available_users_qs = kwargs.pop("available_users_qs", None)
        super().__init__(*args, **kwargs)

        # ✅ name requerido + mensaje bonito
        self.fields["name"].required = True
        self.fields["name"].error_messages["required"] = "Debes ingresar el nombre del grupo."

        if available_users_qs is not None:
            self.fields["funcionarios"].queryset = available_users_qs

        # ✅ En editar: precargar usuarios del grupo
        if self.instance.pk and not self.is_bound:
            self.fields["funcionarios"].initial = self.instance.user_set.all()

    def clean_name(self):
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError("Debes ingresar el nombre del grupo.")
        return name

    def save(self, commit=True):
        group = super().save(commit=commit)

        if commit:
            selected_users = self.cleaned_data.get("funcionarios")
            if selected_users is not None:
                current_ids = set(group.user_set.values_list("id", flat=True))
                new_ids = set(selected_users.values_list("id", flat=True))
                remove_ids = current_ids - new_ids
                if remove_ids:
                    group.user_set.remove(*User.objects.filter(id__in=remove_ids))

                for u in selected_users:
                    u.groups.clear()   # deja 1 solo grupo por funcionario (tu regla)
                    u.groups.add(group)

        return group


# =========================
# Funcionarios
# =========================
from django import forms
from django.contrib.auth.models import User
from django.utils import timezone
from django_select2.forms import ModelSelect2Widget

from db.models import Funcionarios, Departamentos, Usuarios
from web.models import FuncionarioWebUser  # <-- tu tabla puente


class FuncionarioForm(forms.ModelForm):
    #  Usuario REAL (tabla usuarios UUID)
    usuario = forms.ModelChoiceField(
        queryset=Usuarios.objects.all(),
        label="Usuario (App móvil - UUID)",
        widget=ModelSelect2Widget(
            model=Usuarios,
            search_fields=["correo__icontains"],
            attrs={"id": "id_usuario", "data-placeholder": "Buscar por correo...", "class": "form-control"},
        ),
    )

    #   WebUser (auth_user int) - se guarda en tabla puente
    web_user = forms.ModelChoiceField(
        queryset=User.objects.all(),
        label="Usuario Web (Login - auth_user)",
        required=False,
        widget=ModelSelect2Widget(
            model=User,
            search_fields=["username__icontains", "email__icontains"],
            attrs={"id": "id_web_user", "data-placeholder": "Buscar usuario web...", "class": "form-control"},
        ),
    )

    departamento = forms.ModelChoiceField(
        queryset=Departamentos.objects.filter(activo=True),
        label="Departamento",
        required=False,
        widget=ModelSelect2Widget(
            model=Departamentos,
            search_fields=["nombre__icontains"],
            attrs={"data-placeholder": "Buscar departamento...", "class": "form-control"},
        ),
    )

    class Meta:
        model = Funcionarios
        fields = ["usuario", "web_user", "cedula", "nombres", "apellidos", "telefono", "departamento", "cargo", "activo"]
        widgets = {
            "cedula": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ingrese la cédula"}),
            "nombres": forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}),
            "apellidos": forms.TextInput(attrs={"class": "form-control", "readonly": "readonly"}),
            "telefono": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ingrese el teléfono"}),
            "cargo": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ingrese el cargo"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        #   WebUsers disponibles: solo los que NO están vinculados en la tabla puente
        users_sin_funcionario = User.objects.exclude(funcionario_link__isnull=False).order_by("username")

        #   En edición: permitir el actual y bloquear cambio de usuario UUID
        if self.instance and getattr(self.instance, "pk", None):
            # Mantener el web_user ya vinculado (si existe)
            link = FuncionarioWebUser.objects.filter(funcionario=self.instance).select_related("web_user").first()
            self.fields["web_user"].disabled = True
            self.fields["web_user"].help_text = "No se puede cambiar el usuario web una vez vinculado."
            
            if link and link.web_user:
                self.fields["web_user"].initial = link.web_user
                users_sin_funcionario = users_sin_funcionario | User.objects.filter(pk=link.web_user.pk)

            self.fields["usuario"].disabled = True
            self.fields["usuario"].help_text = "No se puede cambiar el usuario UUID una vez creado el funcionario."

        self.fields["web_user"].queryset = users_sin_funcionario.order_by("username")
        self.fields["departamento"].queryset = Departamentos.objects.filter(activo=True).order_by("nombre")

    def save(self, commit=True):
        instance = super().save(commit=False)

        now = timezone.now()
        if not instance.pk:
            instance.created_at = now
        instance.updated_at = now

        if commit:
            instance.save()

            #   Guardar/actualizar tabla puente con auth_user (si se seleccionó)
            web_user = self.cleaned_data.get("web_user")

            if web_user:
                FuncionarioWebUser.objects.update_or_create(
                    funcionario=instance,
                    defaults={"web_user": web_user}
                )
            else:
                # si lo dejas vacío, opcional: borrar vínculo
                FuncionarioWebUser.objects.filter(funcionario=instance).delete()

        return instance

# =========================
# Departamentos
# =========================
class DepartamentoForm(forms.ModelForm):
    class Meta:
        model = Departamentos
        fields = ["nombre", "activo", "color_hex"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre del departamento"}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "color_hex": forms.TextInput(attrs={"class": "form-control", "type": "color"}),
        }

    def save(self, commit=True):
        instance = super().save(commit=False)
        now = timezone.now()
        if not instance.pk:
            instance.created_at = now
        instance.updated_at = now
        if commit:
            instance.save()
        return instance

# =========================
# Web Users
# =========================


class WebUserForm(forms.ModelForm):
    groups = forms.ModelMultipleChoiceField(
        queryset=Group.objects.all(),
        required=False,
        widget=ModelSelect2MultipleWidget(
            model=Group,
            search_fields=["name__icontains"],
            attrs={"class": "form-control", "multiple": "multiple", "data-placeholder": "Buscar grupos..."},
        ),
    )

    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control", "placeholder": "Dejar en blanco para no cambiar"}),
        help_text="Dejar en blanco para mantener la contraseña actual",
    )

    class Meta:
        model = User
        fields = [
            "username",
            "email",
            "first_name",
            "last_name",
            "is_staff",
            "is_active",
            "is_superuser",
            "groups",
            #"user_permissions",
            "last_login",
            "date_joined",
        ]
        widgets = {
            "username": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "is_superuser": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            #"user_permissions": forms.CheckboxSelectMultiple(attrs={"class": "form-check-input"}),
            "last_login": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
            "date_joined": forms.DateTimeInput(attrs={"class": "form-control", "type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["groups"].queryset = Group.objects.all()
        #self.fields["user_permissions"].queryset = Permission.objects.all()

        if "last_login" in self.fields:
            self.fields["last_login"].disabled = True
        if "date_joined" in self.fields:
            self.fields["date_joined"].disabled = True

        if self.instance and self.instance.pk:
            self.fields["password"].initial = ""

# =========================
# FAQ
# =========================
class FaqForm(forms.ModelForm):
    class Meta:
        model = Faq
        fields = ["pregunta", "respuesta", "visible"]
        widgets = {
            "pregunta": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "respuesta": forms.Textarea(attrs={"class": "form-control", "rows": 5}),
            "visible": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

# =========================
# Denuncias
# =========================
class DenunciaForm(forms.ModelForm):
    class Meta:
        model = Denuncias
        fields = [
            "estado",
            "asignado_departamento",
            "asignado_funcionario",
            "descripcion",
            "tipo_denuncia",
            "referencia",
            "direccion_texto",
        ]
        widgets = {
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "referencia": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "direccion_texto": forms.Textarea(attrs={"class": "form-control", "rows": 2}),
            "estado": forms.Select(attrs={"class": "form-select"}),
            "asignado_departamento": ModelSelect2Widget(model=Departamentos, search_fields=["nombre__icontains"], attrs={"class": "form-control"}),
            "asignado_funcionario": ModelSelect2Widget(model=Funcionarios, search_fields=["nombres__icontains", "apellidos__icontains", "cedula__icontains"], attrs={"class": "form-control"}),
            "tipo_denuncia": ModelSelect2Widget(model=TiposDenuncia, search_fields=["nombre__icontains"], attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "estado" in self.fields:
            self.fields["estado"].choices = ESTADO_CHOICES

        if "asignado_departamento" in self.fields:
            self.fields["asignado_departamento"].queryset = Departamentos.objects.filter(activo=True).order_by("nombre")

        if "tipo_denuncia" in self.fields:
            self.fields["tipo_denuncia"].queryset = TiposDenuncia.objects.filter(activo=True).order_by("nombre")

        if "asignado_funcionario" in self.fields:
            try:
                self.fields["asignado_funcionario"].queryset = Funcionarios.objects.filter(activo=True).order_by("apellidos", "nombres")
            except Exception:
                self.fields["asignado_funcionario"].queryset = Funcionarios.objects.all().order_by("apellidos", "nombres")


class DenunciaRespuestaForm(forms.ModelForm):
    class Meta:
        model = DenunciaRespuestas
        fields = ["mensaje"]
        widgets = {"mensaje": forms.Textarea(attrs={"class": "form-control", "rows": 3})}


class DenunciaAsignacionForm(forms.ModelForm):
    class Meta:
        model = DenunciaAsignaciones
        fields = ["funcionario"]
        widgets = {
            "funcionario": ModelSelect2Widget(
                model=Funcionarios,
                search_fields=["nombres__icontains", "apellidos__icontains", "cedula__icontains"],
                attrs={"class": "form-control"},
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            self.fields["funcionario"].queryset = Funcionarios.objects.filter(activo=True).order_by("apellidos", "nombres")
        except Exception:
            self.fields["funcionario"].queryset = Funcionarios.objects.all().order_by("apellidos", "nombres")

# =========================
# TipoDenuncia ↔ Departamento
# =========================
class TipoDenunciaDepartamentoForm(forms.ModelForm):
    class Meta:
        model = TipoDenunciaDepartamento
        fields = ["tipo_denuncia", "departamento"]
        widgets = {
            "tipo_denuncia": forms.Select(attrs={"class": "form-select"}),
            "departamento": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 1) Solo activos
        qs_tipos = TiposDenuncia.objects.filter(activo=True).order_by("nombre")
        qs_deps  = Departamentos.objects.filter(activo=True).order_by("nombre")

        # 2) Tipos ya asignados (por ser OneToOne, no deben repetirse)
        asignados_ids = list(
            TipoDenunciaDepartamento.objects.values_list("tipo_denuncia_id", flat=True)
        )

        # 3) Si estoy editando, dejo el actual disponible (para que no desaparezca)
        if self.instance and self.instance.pk:
            actual_id = self.instance.tipo_denuncia_id
            if actual_id in asignados_ids:
                asignados_ids.remove(actual_id)

        # 4) En Create: excluye asignados. En Update: excluye asignados excepto el actual.
        qs_tipos = qs_tipos.exclude(id__in=asignados_ids)

        self.fields["tipo_denuncia"].queryset = qs_tipos
        self.fields["departamento"].queryset = qs_deps


# =========================
# Tipos de Denuncia
# =========================
class TiposDenunciaForm(forms.ModelForm):
    class Meta:
        model = TiposDenuncia
        fields = ["nombre", "descripcion", "activo"]
        widgets = {
            "nombre": forms.TextInput(attrs={"class": "form-control", "placeholder": "Ej: Baches en la vía"}),
            "descripcion": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "activo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Si es CREATE: activo por defecto True y oculto el campo
        if not self.instance or not self.instance.pk:
            self.fields["activo"].initial = True
            self.fields["activo"].required = False
            self.fields["activo"].widget = forms.HiddenInput()