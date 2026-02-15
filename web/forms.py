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
    ("mdi mdi-view-grid", "Panel"),
    ("mdi mdi-menu", "Menú"),
    ("mdi mdi-view-list", "Listado"),
    ("mdi mdi-format-list-bulleted", "Lista"),
    ("mdi mdi-chart-bar", "Estadísticas"),
    ("mdi mdi-chart-line", "Gráfico"),
    ("mdi mdi-table", "Tabla"),
    ("mdi mdi-timeline", "Tendencias"),

    # Denuncias / Reportes
    ("mdi mdi-megaphone", "Denuncias"),
    ("mdi mdi-file-document", "Reporte"),
    ("mdi mdi-file-document-edit", "Editar reporte"),
    ("mdi mdi-file-document-multiple", "Reportes"),
    ("mdi mdi-clipboard-text", "Formulario"),
    ("mdi mdi-clipboard-check", "Validación"),
    ("mdi mdi-clipboard-alert", "Incidencias"),
    ("mdi mdi-note-text", "Detalle"),
    ("mdi mdi-text-box", "Descripción"),
    ("mdi mdi-text-box-check", "Confirmación"),

    # Estados / Flujo
    ("mdi mdi-progress-clock", "Pendiente"),
    ("mdi mdi-timer-sand", "En proceso"),
    ("mdi mdi-checkbox-marked-circle", "Resuelto"),
    ("mdi mdi-close-circle", "Rechazado"),
    ("mdi mdi-check-circle", "Aprobado"),
    ("mdi mdi-alert-circle", "Observado"),
    ("mdi mdi-sync", "Actualización"),
    ("mdi mdi-refresh", "Recargar"),
    ("mdi mdi-history", "Historial"),
    ("mdi mdi-history-clock", "Bitácora"),

    # Usuarios / Roles / Seguridad
    ("mdi mdi-account", "Usuario"),
    ("mdi mdi-account-multiple", "Usuarios"),
    ("mdi mdi-account-check", "Usuario verificado"),
    ("mdi mdi-account-badge", "Funcionario"),
    ("mdi mdi-account-tie", "Administrador"),
    ("mdi mdi-shield-account", "Rol"),
    ("mdi mdi-account-group", "Grupos"),
    ("mdi mdi-shield-lock", "Permisos"),
    ("mdi mdi-lock", "Bloqueo"),
    ("mdi mdi-key", "Acceso"),

    # Comunicación / Notificaciones
    ("mdi mdi-bell", "Notificaciones"),
    ("mdi mdi-bell-alert", "Alerta de notificación"),
    ("mdi mdi-email", "Correo"),
    ("mdi mdi-email-outline", "Bandeja"),
    ("mdi mdi-send", "Enviar"),
    ("mdi mdi-chat", "Chat"),
    ("mdi mdi-message-text", "Mensaje"),
    ("mdi mdi-comment-text", "Comentario"),
    ("mdi mdi-phone", "Teléfono"),
    ("mdi mdi-bullhorn", "Avisos"),

    # Ubicación / Mapa / Zonas
    ("mdi mdi-map", "Mapa"),
    ("mdi mdi-map-marker", "Ubicación"),
    ("mdi mdi-map-marker-radius", "Zona"),
    ("mdi mdi-map-marker-alert", "Zona de riesgo"),
    ("mdi mdi-map-marker-check", "Zona segura"),
    ("mdi mdi-crosshairs-gps", "GPS"),
    ("mdi mdi-routes", "Rutas"),
    ("mdi mdi-navigation", "Navegación"),
    ("mdi mdi-compass", "Brújula"),
    ("mdi mdi-earth", "Geolocalización"),

    # Evidencias (fotos, archivos, multimedia)
    ("mdi mdi-camera", "Cámara"),
    ("mdi mdi-image", "Imagen"),
    ("mdi mdi-image-multiple", "Galería"),
    ("mdi mdi-video", "Video"),
    ("mdi mdi-microphone", "Audio"),
    ("mdi mdi-paperclip", "Adjunto"),
    ("mdi mdi-file", "Archivo"),
    ("mdi mdi-file-pdf-box", "PDF"),
    ("mdi mdi-file-excel-box", "Excel"),
    ("mdi mdi-folder", "Carpeta"),

    # Catálogos / Configuración / Administración
    ("mdi mdi-cog", "Configuración"),
    ("mdi mdi-cogs", "Ajustes avanzados"),
    ("mdi mdi-tools", "Herramientas"),
    ("mdi mdi-tune", "Parámetros"),
    ("mdi mdi-database", "Base de datos"),
    ("mdi mdi-server", "Servidor"),
    ("mdi mdi-shield", "Seguridad"),
    ("mdi mdi-wrench", "Mantenimiento"),
    ("mdi mdi-calendar", "Calendario"),
    ("mdi mdi-clock", "Horario"),

    # Acciones comunes
    ("mdi mdi-plus-circle", "Crear"),
    ("mdi mdi-pencil", "Editar"),
    ("mdi mdi-content-save", "Guardar"),
    ("mdi mdi-delete", "Eliminar"),
    ("mdi mdi-eye", "Ver"),
    ("mdi mdi-eye-off", "Ocultar"),
    ("mdi mdi-magnify", "Buscar"),
    ("mdi mdi-filter", "Filtrar"),
    ("mdi mdi-sort", "Ordenar"),
    ("mdi mdi-download", "Descargar"),

    # Riesgo / Prioridad
    ("mdi mdi-alert", "Alerta"),
    ("mdi mdi-alert-octagon", "Urgente"),
    ("mdi mdi-alert-outline", "Advertencia"),
    ("mdi mdi-fire", "Incendio"),
    ("mdi mdi-traffic-cone", "Tránsito"),
    ("mdi mdi-hospital-box", "Salud"),
    ("mdi mdi-police-badge", "Seguridad ciudadana"),
    ("mdi mdi-water", "Agua"),
    ("mdi mdi-lightbulb", "Alumbrado"),
    ("mdi mdi-trash-can", "Basura"),
    ("mdi mdi-road-variant", "Vía pública"),
]



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

# =========================
# Grupos
# =========================
class GrupoForm(forms.ModelForm):
    class Meta:
        model = Group
        fields = ["name", "permissions"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Nombre del grupo"}),
            "permissions": ModelSelect2MultipleWidget(
                model=Permission,
                search_fields=["name__icontains"],
                attrs={"class": "form-control"},
            ),
        }

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