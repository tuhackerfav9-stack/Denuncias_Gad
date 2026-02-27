# web/views.py
from __future__ import annotations

import json
import re
import uuid
from datetime import timedelta
from django.db import transaction

from django.db.models.functions import TruncDate, TruncWeek, TruncMonth
from django.conf import settings
from django.contrib.auth.decorators import login_required  #  QUITÉ permission_required (ya no lo usamos para db.xxx)
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin  #  QUITÉ PermissionRequiredMixin
from django.contrib.auth.models import Group, User
from django.contrib.auth.views import LoginView
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Count, Q
#from django.db.models.functions import TruncMonth, TruncWeek
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_POST
from django.views.generic.detail import DetailView
from django.views.generic.edit import CreateView, DeleteView, UpdateView
from django.views.generic.list import ListView
from django.urls import reverse

from chartkick.django import BarChart, ColumnChart, LineChart, PieChart

from openai import OpenAI

from db.models import (
    Ciudadanos,
    Denuncia,
    DenunciaAsignaciones,
    DenunciaEvidencias,
    DenunciaFirmas,
    DenunciaHistorial,
    DenunciaRespuestas,
    Denuncias,
    Departamentos,
    Faq,
    Funcionarios,
    TipoDenunciaDepartamento,
    TiposDenuncia,
)

from .forms import (
    CrudMessageMixin,
    DenunciaForm,
    DenunciaRespuestaForm,
    DepartamentoForm,
    FaqForm,
    FuncionarioForm,
    GrupoForm,
    MenuForm,
    PermissionRequiredMixin as CustomPermissionRequiredMixin,  #  lo dejamos para auth.* (grupos/users/menus)
    TipoDenunciaDepartamentoForm,
    TiposDenunciaForm,
    WebUserForm,
)
from .models import FuncionarioWebUser, Menus
from web.utils.menus import build_menus_for_user
from notificaciones.services import notificar_respuesta
from django.contrib import messages
from django.utils.http import url_has_allowed_host_and_scheme
from web.services.webuser_domain import soft_disable_web_user
from web.services.delete_rules import can_hard_delete_user

def mi_vista(request):
    context = {
        "menus_principales": build_menus_for_user(request.user),
    }
    return render(request, "x.html", context)


# =========================================
# web/views.py
# =========================================
from django.shortcuts import render
from db.models import Faq

def public_home_view(request):
    faqs = Faq.objects.filter(visible=True).order_by("-created_at")
    return render(request, "home.html", {"faqs": faqs})

# =========================================
# OpenAI client (safe if key missing)
# =========================================
api_key = getattr(settings, "OPENAI_API_KEY", None)
client = OpenAI(api_key=api_key) if api_key else None


# =========================================
# ponerle funcioanrio a denuncia
# =========================================

def tomar_denuncia_si_libre(denuncia, funcionario, motivo="Denuncia tomada para atención."):
    """
    Si la denuncia está libre -> la asigna al funcionario actual y registra historial/asignación.
    Si ya está asignada al mismo funcionario -> no hace nada.
    Si está asignada a otro -> bloquea.
    """
    if not funcionario:
        return False, "No autorizado"

    # Ya está tomada por otro
    if denuncia.asignado_funcionario_id and denuncia.asignado_funcionario_id != funcionario.pk:
        #nombre_otro = f"{denuncia.asignado_funcionario.nombres} {denuncia.asignado_funcionario.apellidos}"
        otro = Funcionarios.objects.filter(pk=denuncia.asignado_funcionario_id).first()
        nombre_otro = f"{getattr(otro,'nombres','')} {getattr(otro,'apellidos','')}".strip() or "otro funcionario"

        return False, f"Esta denuncia ya está siendo atendida por {nombre_otro}."

    # Si está libre, tomarla
    if not denuncia.asignado_funcionario_id:
        estado_anterior = denuncia.estado

        denuncia.asignado_funcionario = funcionario

        #   Cuando se toma por atención, pasa a en_proceso si aún no está resuelta/rechazada
        if denuncia.estado in ["pendiente", "asignada", "en_revision"]:
            denuncia.estado = "en_proceso"

        denuncia.updated_at = timezone.now()
        denuncia.save(update_fields=["asignado_funcionario", "estado", "updated_at"])

        # Historial (siempre)
        DenunciaHistorial.objects.create(
            id=get_uuid(),
            estado_anterior=estado_anterior,
            estado_nuevo=denuncia.estado,
            comentario=motivo,
            cambiado_por_funcionario=funcionario,
            created_at=timezone.now(),
            denuncia_id=denuncia.id,
        )

        # Asignaciones (si existe tu tabla)
        # (opcional) desactiva asignaciones anteriores activas
        DenunciaAsignaciones.objects.filter(denuncia=denuncia, activo=True).update(activo=False)

        DenunciaAsignaciones.objects.create(
            id=get_uuid(),
            denuncia=denuncia,
            funcionario=funcionario,
            asignado_en=timezone.now(),
            activo=True,  # ✅ CLAVE para que no mande NULL
        )


    return True, "OK"


@login_required
@require_POST
def tomar_denuncia(request, denuncia_id):
    funcionario = get_funcionario_from_web_user(request.user)
    if not (request.user.is_superuser or funcionario):
        return JsonResponse({"success": False, "error": "No autorizado"}, status=403)

    with transaction.atomic():
        denuncia = get_object_or_404(
            Denuncias.objects.select_for_update(),  # ✅ SIN select_related
            id=denuncia_id,
        )


        ok, msg = tomar_denuncia_si_libre(
            denuncia,
            funcionario,
            motivo="Denuncia tomada al iniciar atención (respuesta/IA/resolver/rechazar).",
        )
        if not ok:
            return JsonResponse({"success": False, "error": msg}, status=409)

    return JsonResponse({"success": True})

# =========================================
# Helpers
# =========================================
def get_uuid() -> str:
    return str(uuid.uuid4())


def get_funcionario_from_web_user(user):
    # 1) Si hay tabla puente
    link = FuncionarioWebUser.objects.select_related("funcionario").filter(web_user=user).first()
    if link and link.funcionario:
        return link.funcionario

    # 2) Fallback: si Funcionarios tiene FK web_user (por versiones antiguas)
    try:
        return Funcionarios.objects.filter(web_user=user).first()
    except Exception:
        return None


def get_web_user_name_from_funcionario(funcionario) -> str:
    """Devuelve el nombre (full_name o username) del web_user vinculado al funcionario."""
    if not funcionario:
        return "No asignado"
    link = FuncionarioWebUser.objects.select_related("web_user").filter(funcionario=funcionario).first()
    if link and link.web_user:
        return link.web_user.get_full_name() or link.web_user.username
    return "No asignado"


#  NUEVO: Mixin para permitir SOLO funcionarios (o superuser)
class FuncionarioRequiredMixin(LoginRequiredMixin):
    login_url = "web:login"

    def dispatch(self, request, *args, **kwargs):
        funcionario = get_funcionario_from_web_user(request.user)
        if not (request.user.is_superuser or funcionario):
            return render(request, "errors/403.html", status=403)
        return super().dispatch(request, *args, **kwargs)


# =========================================
# Error handlers
# =========================================
def permission_denied_view(request, exception=None):
    return render(request, "errors/403.html", status=403)


def page_not_found_view(request, exception=None):
    return render(request, "errors/404.html", status=404)


def server_error_view(request):
    return render(request, "errors/500.html", status=500)


# =========================================
# Auth / Home
# =========================================
class CustomLoginView(LoginView):
    template_name = "registration/login.html"

    def form_invalid(self, form):
        messages.error(self.request, "Usuario o contraseña incorrectos.")
        return super().form_invalid(form)
    
    def get(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if request.user.is_superuser:
                return redirect("web:dashboard")
            is_funcionario = get_funcionario_from_web_user(request.user) is not None
            return redirect("web:dashboard" if is_funcionario else "web:home")
        return super().get(request, *args, **kwargs)

    def get_success_url(self):
        if self.request.user.is_authenticated:
            if self.request.user.is_superuser:
                return reverse_lazy("web:dashboard")
            is_funcionario = get_funcionario_from_web_user(self.request.user) is not None
            return reverse_lazy("web:dashboard" if is_funcionario else "web:home")
        return reverse_lazy("web:home")


def home_view(request):
    if request.user.is_authenticated:
        return redirect("web:dashboard")
    faqs = Faq.objects.filter(visible=True).order_by("-created_at")
    return render(request, "home.html", {"faqs": faqs})


@login_required
def get_user_data_ajax(request, user_id: int):
    """Autocompleta nombres/apellidos/email al seleccionar web_user en FuncionarioForm."""
    try:
        user = User.objects.get(id=user_id)
        return JsonResponse(
            {
                "success": True,
                "first_name": user.first_name or "",
                "last_name": user.last_name or "",
                "email": user.email or "",
            }
        )
    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "Usuario no encontrado"}, status=404)

from django.views.decorators.http import require_GET

@login_required
@require_GET
def api_respuestas_denuncia(request, denuncia_id):
    #  Solo funcionarios/superuser (igual que tus otras protecciones)
    funcionario = get_funcionario_from_web_user(request.user)
    if not (request.user.is_superuser or funcionario):
        return JsonResponse({"success": False, "error": "No autorizado"}, status=403)

    denuncia = get_object_or_404(Denuncias, id=denuncia_id)

    #  Seguridad: si NO es admin, solo puede ver denuncias de su depto
    if not (request.user.is_superuser or request.user.groups.filter(name="TICS_ADMIN").exists()):
        if not funcionario or not funcionario.departamento_id:
            return JsonResponse({"success": False, "error": "No autorizado"}, status=403)
        if denuncia.asignado_departamento_id is None:
            return JsonResponse({"success": False, "error": "Denuncia sin departamento asignado"}, status=400)

        if denuncia.asignado_departamento_id != funcionario.departamento_id:
            return JsonResponse({"success": False, "error": "No autorizado"}, status=403)

    respuestas = (
        DenunciaRespuestas.objects.filter(denuncia=denuncia)
        .select_related("funcionario")
        .order_by("created_at")
    )

    data = []
    for r in respuestas:
        func = r.funcionario
        data.append({
            "id": str(r.id),
            "mensaje": r.mensaje,
            "fecha": r.created_at.isoformat() if r.created_at else None,
            "funcionario": {
                "id": str(func.pk) if func else None,   #  usar pk
                "nombre": getattr(func, "nombres", "") if func else "",
                "apellido": getattr(func, "apellidos", "") if func else "",
            }

        })

    return JsonResponse({"success": True, "respuestas": data})

@login_required
def dashboard_view(request):
    user = request.user

    def split_label_every_n_words(text, n=4):
        """
        Convierte un texto largo en varias líneas para Chart.js.
        Ej: 'Dirección de Gestión Ambiental y Desechos Sólidos'
        -> ['Dirección de Gestión Ambiental y', 'Desechos Sólidos']
        """
        if not text:
            return ["Sin nombre"]

        words = str(text).split()
        if len(words) <= n:
            return [str(text)]

        return [" ".join(words[i:i + n]) for i in range(0, len(words), n)]

    # =========================
    # 1) Querysets base
    # =========================
    denuncias_qs = Denuncias.objects.all()
    funcionarios_qs = Funcionarios.objects.all()
    departamentos_qs = Departamentos.objects.all()

    # =========================
    # 2) Control de acceso / filtro por rol
    # =========================
    if user.is_superuser:
        current_user_department = None
        map_scope_text = "Mostrando todas las denuncias con ubicación válida"
    else:
        funcionario = get_funcionario_from_web_user(user)
        if not funcionario:
            return render(request, "errors/403.html", status=403)

        current_user_department = getattr(funcionario, "departamento", None)

        if current_user_department:
            denuncias_qs = denuncias_qs.filter(asignado_departamento=current_user_department)
            funcionarios_qs = funcionarios_qs.filter(departamento=current_user_department)
            departamentos_qs = departamentos_qs.filter(pk=current_user_department.pk)
            map_scope_text = f"Mostrando denuncias con ubicación válida de tu departamento: {current_user_department.nombre}"
        else:
            denuncias_qs = denuncias_qs.none()
            funcionarios_qs = funcionarios_qs.none()
            departamentos_qs = departamentos_qs.none()
            map_scope_text = "No tienes un departamento asignado"

    # =========================
    # 3) Fechas
    # =========================
    fecha_hace_30_dias = timezone.now() - timedelta(days=30)

    # =========================
    # 4) KPIs
    # =========================
    total_denuncias = denuncias_qs.count()
    denuncias_este_mes = denuncias_qs.filter(created_at__gte=fecha_hace_30_dias).count()

    denuncias_pendientes = denuncias_qs.filter(estado="pendiente").count()
    denuncias_en_proceso = denuncias_qs.filter(estado="en_proceso").count()
    denuncias_resueltas = denuncias_qs.filter(estado="resuelta").count()

    # NUEVA tarjeta
    denuncias_asignadas = denuncias_qs.filter(asignado_departamento__isnull=False).count()

    # =========================
    # 5) Otros KPIs
    # =========================
    total_ciudadanos = Ciudadanos.objects.count()
    ciudadanos_este_mes = Ciudadanos.objects.filter(created_at__gte=fecha_hace_30_dias).count()

    total_funcionarios = funcionarios_qs.count()
    funcionarios_activos = funcionarios_qs.filter(activo=True).count()

    total_departamentos = departamentos_qs.count()
    departamentos_activos = departamentos_qs.filter(activo=True).count()

    promedio_denuncias_depto = total_denuncias / max(departamentos_activos, 1)
    tasa_resolucion = (denuncias_resueltas / total_denuncias) * 100 if total_denuncias > 0 else 0

    # =========================
    # 6) Charts Chartkick
    # =========================
    chart_estado_denuncias = PieChart(
        {
            "Resueltas": denuncias_resueltas,
            "Pendientes": denuncias_pendientes,
            "En Proceso": denuncias_en_proceso,
        },
        title="Estado de Denuncias",
        donut=True,
    )

    denuncias_por_tipo = (
        denuncias_qs.values("tipo_denuncia__nombre")
        .annotate(count=Count("pk"))
        .order_by("-count")[:5]
    )

    # Top ciudadanos
    ciudadanos_top_data = (
        denuncias_qs.values("ciudadano__nombres", "ciudadano__apellidos")
        .annotate(count=Count("pk"))
        .order_by("-count")[:10]
    )

    chart_ciudadanos_top = BarChart(
        {
            f"{i['ciudadano__nombres']} {i['ciudadano__apellidos']}": i["count"]
            for i in ciudadanos_top_data
        },
        title="Ciudadanos con más Denuncias (Top 10)",
        xtitle="Cantidad",
        ytitle="Ciudadano",
    )

    # Semana / Mes
    denuncias_semana_data = (
        denuncias_qs.filter(created_at__gte=fecha_hace_30_dias)
        .annotate(semana=TruncWeek("created_at"))
        .values("semana")
        .annotate(count=Count("pk"))
        .order_by("semana")
    )

    chart_denuncias_semana = LineChart(
        {
            i["semana"].strftime("%Y-%m-%d"): i["count"]
            for i in denuncias_semana_data if i["semana"]
        },
        title="Denuncias por Semana",
        xtitle="Semana",
        ytitle="Cantidad",
        download={"filename": "chart_denuncias_semana"},
    )

    denuncias_mes_data = (
        denuncias_qs.filter(created_at__gte=fecha_hace_30_dias)
        .annotate(mes=TruncMonth("created_at"))
        .values("mes")
        .annotate(count=Count("pk"))
        .order_by("mes")
    )

    chart_denuncias_mes = LineChart(
        {
            i["mes"].strftime("%Y-%m"): i["count"]
            for i in denuncias_mes_data if i["mes"]
        },
        title="Denuncias por Mes",
        xtitle="Mes",
        ytitle="Cantidad",
    )

    # =========================
    # 7) Datos para gráfico custom de departamentos
    # =========================
    denuncias_por_departamento_data = (
        denuncias_qs.filter(asignado_departamento__isnull=False)
        .values("asignado_departamento__nombre", "asignado_departamento__color_hex")
        .annotate(count=Count("pk"))
        .order_by("-count")
    )

    dept_chart_labels = []
    dept_chart_full_labels = []
    dept_chart_values = []
    dept_chart_colors = []

    for item in denuncias_por_departamento_data:
        nombre = item["asignado_departamento__nombre"] or "Sin departamento"
        dept_chart_labels.append(split_label_every_n_words(nombre, 4))
        dept_chart_full_labels.append(nombre)
        dept_chart_values.append(item["count"])
        dept_chart_colors.append(item["asignado_departamento__color_hex"] or "#4B49AC")

    # =========================
    # 8) Mapa - TODAS las denuncias válidas del queryset filtrado por rol
    # =========================
    denuncias_mapa_qs = (
        denuncias_qs.select_related("ciudadano", "tipo_denuncia", "asignado_departamento")
        .filter(latitud__isnull=False, longitud__isnull=False)
        .exclude(latitud=0)
        .exclude(longitud=0)
        .order_by("-created_at")
    )

    map_points = []
    for denuncia in denuncias_mapa_qs:
        try:
            lat = float(denuncia.latitud)
            lng = float(denuncia.longitud)
        except (TypeError, ValueError):
            continue

        # Validación básica
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            continue

        ciudadano_nombre = "Sin ciudadano"
        if getattr(denuncia, "ciudadano", None):
            ciudadano_nombre = (
                f"{getattr(denuncia.ciudadano, 'nombres', '')} "
                f"{getattr(denuncia.ciudadano, 'apellidos', '')}"
            ).strip() or "Sin ciudadano"

        tipo_nombre = "Sin tipo"
        if getattr(denuncia, "tipo_denuncia", None):
            tipo_nombre = getattr(denuncia.tipo_denuncia, "nombre", "Sin tipo")

        departamento_nombre = "Sin asignar"
        if getattr(denuncia, "asignado_departamento", None):
            departamento_nombre = getattr(denuncia.asignado_departamento, "nombre", "Sin asignar")

        map_points.append({
            "uuid": str(denuncia.pk),
            "lat": lat,
            "lng": lng,
            "descripcion": (denuncia.descripcion or "")[:120],
            "tipo": tipo_nombre,
            "estado": denuncia.estado,
            "ciudadano": ciudadano_nombre,
            "departamento": departamento_nombre,
            "fecha": denuncia.created_at.strftime("%d/%m/%Y %H:%M"),
            "detalle_url": f"/web/denuncias/{denuncia.pk}/",
        })

    context = {
        "total_denuncias": total_denuncias,
        "denuncias_este_mes": denuncias_este_mes,
        "denuncias_pendientes": denuncias_pendientes,
        "denuncias_en_proceso": denuncias_en_proceso,
        "denuncias_resueltas": denuncias_resueltas,
        "denuncias_asignadas": denuncias_asignadas,

        "total_ciudadanos": total_ciudadanos,
        "ciudadanos_este_mes": ciudadanos_este_mes,
        "total_funcionarios": total_funcionarios,
        "funcionarios_activos": funcionarios_activos,
        "total_departamentos": total_departamentos,
        "departamentos_activos": departamentos_activos,
        "promedio_denuncias_depto": round(promedio_denuncias_depto, 2),
        "tasa_resolucion": round(tasa_resolucion, 1),

        "denuncias_por_tipo": denuncias_por_tipo,
        "departamentos_con_denuncias": list(denuncias_por_departamento_data[:10]),

        "chart_estado_denuncias": chart_estado_denuncias,
        "chart_ciudadanos_top": chart_ciudadanos_top,
        "chart_denuncias_semana": chart_denuncias_semana,
        "chart_denuncias_mes": chart_denuncias_mes,

        # gráfico custom
        "dept_chart_labels": dept_chart_labels,
        "dept_chart_full_labels": dept_chart_full_labels,
        "dept_chart_values": dept_chart_values,
        "dept_chart_colors": dept_chart_colors,

        # mapa
        "map_points": map_points,
        "map_scope_text": map_scope_text,
    }

    return render(request, "dashboard.html", context)    

# =========================================
# Grupos
# =========================================
class GrupoListView(LoginRequiredMixin, CustomPermissionRequiredMixin, ListView):
    model = Group
    template_name = "grupos/grupo_list.html"
    context_object_name = "grupos"
    permission_required = "auth.view_group"
    login_url = "web:login"
    ordering = ["name"]
    paginate_by = 10
    
    def get_queryset(self):
        return Group.objects.order_by("name")


class GrupoCreateView(CrudMessageMixin, LoginRequiredMixin, CustomPermissionRequiredMixin, CreateView):
    model = Group
    form_class = GrupoForm
    template_name = "grupos/grupo_form.html"
    success_url = reverse_lazy("web:grupo_list")
    permission_required = "auth.add_group"
    login_url = "web:login"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        #   SOLO funcionarios (tabla puente) SIN grupo
        available = User.objects.filter(
            funcionario_link__isnull=False,   # <- viene de related_name en FuncionarioWebUser
            is_active=True,
            groups__isnull=True
        ).distinct().order_by("username")

        kwargs["available_users_qs"] = available
        return kwargs


class GrupoUpdateView(CrudMessageMixin, LoginRequiredMixin, CustomPermissionRequiredMixin, UpdateView):
    model = Group
    form_class = GrupoForm
    template_name = "grupos/grupo_form.html"
    success_url = reverse_lazy("web:grupo_list")
    permission_required = "auth.change_group"
    login_url = "web:login"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        #   EDITAR: todos los funcionarios (para poder moverlos)
        available = User.objects.filter(
            funcionario_link__isnull=False,
            is_active=True
        ).distinct().order_by("username")

        kwargs["available_users_qs"] = available
        return kwargs


class GrupoDetailView(LoginRequiredMixin, CustomPermissionRequiredMixin, DetailView):
    model = Group
    template_name = "grupos/grupo_detail.html"
    context_object_name = "grupo"
    permission_required = "auth.view_group"
    login_url = "web:login"


class GrupoDeleteView(CrudMessageMixin, LoginRequiredMixin, CustomPermissionRequiredMixin, DeleteView):
    model = Group
    template_name = "grupos/grupo_confirm_delete.html"
    success_url = reverse_lazy("web:grupo_list")
    permission_required = "auth.delete_group"
    login_url = "web:login"


# =========================================
# Menús (solo superuser)
# =========================================
class SuperUserRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_superuser

    def handle_no_permission(self):
        return render(self.request, "errors/403.html", status=403)


class MenuListView(LoginRequiredMixin, SuperUserRequiredMixin, ListView):
    model = Menus
    template_name = "menus/menu_list.html"
    context_object_name = "menus"
    ordering = ["padre", "orden"]
    login_url = "web:login"
    paginate_by = 10

    def get_queryset(self):
        return Menus.objects.all().order_by("padre__id", "orden")


class MenuCreateView(LoginRequiredMixin, SuperUserRequiredMixin, CreateView):
    model = Menus
    form_class = MenuForm
    template_name = "menus/menu_form.html"
    success_url = reverse_lazy("web:menu_list")
    login_url = "web:login"

    def form_valid(self, form):
        messages.success(self.request, "  Menú creado correctamente.")
        return super().form_valid(form)



class MenuUpdateView(LoginRequiredMixin, SuperUserRequiredMixin, UpdateView):
    model = Menus
    form_class = MenuForm
    template_name = "menus/menu_form.html"
    success_url = reverse_lazy("web:menu_list")
    login_url = "web:login"

    def form_valid(self, form):
        messages.success(self.request, "  Menú actualizado correctamente.")
        return super().form_valid(form)


class MenuDeleteView(LoginRequiredMixin, SuperUserRequiredMixin, DeleteView):
    model = Menus
    template_name = "menus/menu_confirm_delete.html"
    success_url = reverse_lazy("web:menu_list")
    login_url = "web:login"

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "🗑️ Menú eliminado.")
        return super().delete(request, *args, **kwargs)

# =========================================
# FAQ
# =========================================
#  Cambio: de "db.*" a control por funcionario (NO existe permiso db.*)
class FaqListView(FuncionarioRequiredMixin, ListView):
    model = Faq
    template_name = "faqs/faq_list.html"
    context_object_name = "faqs"
    login_url = "web:login"
    ordering = ["-created_at"]
    paginate_by = 10


class FaqCreateView(CrudMessageMixin, FuncionarioRequiredMixin, CreateView):
    model = Faq
    form_class = FaqForm
    template_name = "faqs/faq_form.html"
    success_url = reverse_lazy("web:faq_list")
    login_url = "web:login"

    def form_valid(self, form):
        if not form.instance.pk:
            form.instance.created_at = timezone.now()
        form.instance.updated_at = timezone.now()
        return super().form_valid(form)


class FaqUpdateView(CrudMessageMixin, FuncionarioRequiredMixin, UpdateView):
    model = Faq
    form_class = FaqForm
    template_name = "faqs/faq_form.html"
    success_url = reverse_lazy("web:faq_list")
    login_url = "web:login"

    def form_valid(self, form):
        form.instance.updated_at = timezone.now()
        return super().form_valid(form)


class FaqDeleteView(CrudMessageMixin, FuncionarioRequiredMixin, DeleteView):
    model = Faq
    template_name = "faqs/faq_confirm_delete.html"
    success_url = reverse_lazy("web:faq_list")
    login_url = "web:login"


class FaqDetailView(FuncionarioRequiredMixin, DetailView):
    model = Faq
    template_name = "faqs/faq_detail.html"
    context_object_name = "faq"
    login_url = "web:login"



class DenunciaListView(FuncionarioRequiredMixin, ListView):
    model = Denuncias
    template_name = "denuncias/denuncia_list.html"
    context_object_name = "denuncias"
    login_url = "web:login"
    ordering = ["-created_at"]
    paginate_by = 10

    def _is_admin(self, user):
        return user.is_superuser or user.groups.filter(name="TICS_ADMIN").exists()

    def get_queryset(self):
        qs = Denuncias.objects.select_related(
            "ciudadano", "tipo_denuncia", "asignado_departamento", "asignado_funcionario"
        )

        user = self.request.user
        funcionario = get_funcionario_from_web_user(user)

        #  base por rol
        if self._is_admin(user):
            base = qs
        elif funcionario and funcionario.departamento_id:
            base = qs.filter(asignado_departamento_id=funcionario.departamento_id)
        else:
            return qs.none()

        #  filtros
        estado = self.request.GET.get("estado", "").strip()
        if estado:
            base = base.filter(estado=estado)

        tipo = self.request.GET.get("tipo", "").strip()
        if tipo:
            base = base.filter(tipo_denuncia_id=tipo)

        departamento = self.request.GET.get("departamento", "").strip()
        if departamento:
            # admin puede filtrar cualquier depto
            if self._is_admin(user):
                base = base.filter(asignado_departamento_id=departamento)
            # funcionario normal no puede “ver otros”
            # (ignoramos el filtro si intenta otro)
        
        funcionario_get = self.request.GET.get("funcionario", "").strip()
        if funcionario_get:
            base = base.filter(asignado_funcionario_id=funcionario_get)

        q = self.request.GET.get("q", "").strip()
        if q:
            base = base.filter(
                Q(ciudadano__nombres__icontains=q)
                | Q(ciudadano__apellidos__icontains=q)
                | Q(ciudadano__cedula__icontains=q)
                | Q(descripcion__icontains=q)
                | Q(referencia__icontains=q)
            )

        return base.distinct().order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        user = self.request.user
        funcionario = get_funcionario_from_web_user(user)
        is_admin = self._is_admin(user)

        #  combos (limitados por rol)
        context["tipos_denuncia"] = TiposDenuncia.objects.filter(activo=True).order_by("nombre")

        if is_admin:
            context["departamentos"] = Departamentos.objects.filter(activo=True).order_by("nombre")
            context["funcionarios"] = Funcionarios.objects.filter(activo=True).order_by("nombres")
        else:
            if funcionario and funcionario.departamento_id:
                context["departamentos"] = Departamentos.objects.filter(id=funcionario.departamento_id, activo=True)
                context["funcionarios"] = Funcionarios.objects.filter(
                    departamento_id=funcionario.departamento_id, activo=True
                ).order_by("nombres")
            else:
                context["departamentos"] = Departamentos.objects.none()
                context["funcionarios"] = Funcionarios.objects.none()

        #  valores actuales (para que se mantengan al refrescar)
        context["estado_actual"] = self.request.GET.get("estado", "")
        context["tipo_actual"] = self.request.GET.get("tipo", "")
        context["departamento_actual"] = self.request.GET.get("departamento", "")
        context["funcionario_actual"] = self.request.GET.get("funcionario", "")
        context["q"] = self.request.GET.get("q", "")

        #  querystring seguro (SIN page) para paginación
        params = self.request.GET.copy()
        params.pop("page", None)
        context["querystring"] = params.urlencode()

        return context

            
from django.http import Http404
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator

class DenunciaDetailView(FuncionarioRequiredMixin, DetailView):
    model = Denuncias
    template_name = "denuncias/denuncia_detail.html"
    context_object_name = "denuncia"
    login_url = "web:login"

    def _is_admin(self, user):
        return user.is_superuser or user.groups.filter(name="TICS_ADMIN").exists()

    def get_object(self, queryset=None):
        obj = super().get_object(queryset)
        user = self.request.user

        # Admin ve todo
        if self._is_admin(user):
            return obj

        # Funcionario solo ve su departamento
        funcionario = get_funcionario_from_web_user(user)
        if not funcionario or not funcionario.departamento_id:
            raise Http404("No autorizado")

        if obj.asignado_departamento_id != funcionario.departamento_id:
            raise Http404("No autorizado")

        return obj

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        denuncia = self.object
        user = self.request.user

        # =========================
        # Asignaciones
        # =========================
        context["asignaciones"] = (
            DenunciaAsignaciones.objects.filter(denuncia=denuncia)
            .select_related("funcionario")
            .order_by("-asignado_en")
        )

        # =========================
        # Evidencias
        # =========================
        evidencias = list(
            DenunciaEvidencias.objects.filter(denuncia=denuncia).order_by("-created_at")
        )

        for e in evidencias:
            # usar la URL tal como viene en BD, pero convertir si es /api/denuncias/archivos/denuncia/<uuid>/
            e.url_archivo = _resolver_url_archivo_web(e.url_archivo)
            e.filename = e.nombre_archivo

            nombre = (e.nombre_archivo or "").lower()
            tipo = (e.tipo or "").lower()

            if tipo == "foto" or nombre.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif")):
                e.content_type = "image/jpeg"
            elif tipo == "video" or nombre.endswith((".mp4", ".mov", ".avi", ".webm", ".mkv")):
                e.content_type = "video/mp4"
            elif tipo == "audio" or nombre.endswith((".mp3", ".wav", ".ogg", ".m4a")):
                e.content_type = "audio/mpeg"
            else:
                e.content_type = "application/octet-stream"

        context["evidencias"] = evidencias

        # =========================
        # Historial (paginado)
        # =========================
        historial_queryset = (
            DenunciaHistorial.objects.filter(denuncia=denuncia)
            .select_related("cambiado_por_funcionario")
            .order_by("-created_at")
        )

        paginator = Paginator(historial_queryset, 3)
        page_number = self.request.GET.get("historial_page")

        try:
            historial_page = paginator.page(page_number)
        except (PageNotAnInteger, EmptyPage):
            historial_page = paginator.page(1)

        context["historial"] = historial_page
        context["historial_paginator"] = paginator

        # =========================
        # Respuestas
        # =========================
        context["respuestas"] = (
            DenunciaRespuestas.objects.filter(denuncia=denuncia)
            .select_related("funcionario")
            .order_by("-created_at")
        )

        # =========================
        # Lock: puede responder?
        # =========================
        funcionario = get_funcionario_from_web_user(user)

        if self._is_admin(user):
            puede_responder = True
        else:
            puede_responder = bool(
                funcionario and (
                    (not denuncia.asignado_funcionario_id)
                    or (denuncia.asignado_funcionario_id == funcionario.pk)
                )
            )

        context["puede_responder"] = puede_responder

        # =========================
        # Firma
        # =========================
        firma = DenunciaFirmas.objects.filter(denuncia_id=denuncia.id).first()
        if firma:
            firma.firma_url = _resolver_url_archivo_web(firma.firma_url)

        context["firma"] = firma

        return context
    
class DenunciaUpdateView(CrudMessageMixin, FuncionarioRequiredMixin, UpdateView):
    model = Denuncias
    form_class = DenunciaForm
    template_name = "denuncias/denuncia_form.html"
    context_object_name = "denuncia"
    success_url = reverse_lazy("web:denuncia_list")
    login_url = "web:login"

    def dispatch(self, request, *args, **kwargs):
        obj = self.get_object()
        user = request.user

        if user.is_superuser or user.groups.filter(name="TICS_ADMIN").exists():
            return super().dispatch(request, *args, **kwargs)

        funcionario = get_funcionario_from_web_user(request.user)
        if not (request.user.is_superuser or funcionario):
            return render(request, "errors/403.html", status=403)

        if obj.asignado_departamento_id != funcionario.departamento_id:
            return render(request, "errors/403.html", status=403)

        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        #   Para volver exacto a donde estabas (lista con filtros/página)
        next_url = self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
            context["return_url"] = next_url
        else:
            # si entraste con ?estado=...&page=... lo usamos como retorno a la lista
            if self.request.GET:
                params = self.request.GET.copy()
                params.pop("next", None)
                qs = params.urlencode()
                if qs:
                    context["return_url"] = f"{reverse_lazy('web:denuncia_list')}?{qs}"
                else:
                    context["return_url"] = reverse_lazy("web:denuncia_list")
            else:
                context["return_url"] = reverse_lazy("web:denuncia_list")

        return context

    def get_success_url(self):
        #   Al guardar, vuelve con filtros/página si venían
        next_url = self.request.GET.get("next")
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={self.request.get_host()}):
            return next_url

        if self.request.GET:
            params = self.request.GET.copy()
            params.pop("next", None)
            qs = params.urlencode()
            if qs:
                return f"{reverse_lazy('web:denuncia_list')}?{qs}"

        return str(self.success_url)

    def form_valid(self, form):
        form.instance.updated_at = timezone.now()

        estado_anterior = Denuncias.objects.get(pk=self.object.pk).estado
        if estado_anterior != form.instance.estado:
            DenunciaHistorial.objects.create(
                id=get_uuid(),
                estado_anterior=estado_anterior,
                estado_nuevo=form.instance.estado,
                comentario="Actualización",
                cambiado_por_funcionario=get_funcionario_from_web_user(self.request.user),
                created_at=timezone.now(),
                denuncia_id=self.object.id,
            )

        messages.success(self.request, "  Denuncia actualizada correctamente.")
        return super().form_valid(form)


class DenunciaDeleteView(CrudMessageMixin, FuncionarioRequiredMixin, DeleteView):
    model = Denuncias
    template_name = "denuncias/denuncia_confirm_delete.html"
    success_url = reverse_lazy("web:denuncia_list")
    login_url = "web:login"


#  Cambio: quitamos @permission_required("db....") y validamos funcionario
@login_required
def crear_respuesta_denuncia(request, pk):
    funcionario = get_funcionario_from_web_user(request.user)
    if not (request.user.is_superuser or funcionario):
        return render(request, "errors/403.html", status=403)

    if request.method != "POST":
        return redirect("web:denuncia_detail", pk=pk)

    form = DenunciaRespuestaForm(request.POST)
    if not form.is_valid():
        messages.error(request, "❌ Mensaje inválido.")
        return redirect("web:denuncia_detail", pk=pk)

    with transaction.atomic():
        # 🔒 bloquea la fila para que 2 funcionarios no la “tomen” al mismo tiempo
        denuncia = Denuncias.objects.select_for_update().get(pk=pk)
        estado_anterior = denuncia.estado  # <-- agrega esto aquí

        # (Opcional) seguridad por depto si no es admin
        if not (request.user.is_superuser or request.user.groups.filter(name="TICS_ADMIN").exists()):
            if not funcionario.departamento_id or denuncia.asignado_departamento_id != funcionario.departamento_id:
                return render(request, "errors/403.html", status=403)

        #   Si nadie la está tratando, el primero que responde la “toma”
        if denuncia.asignado_funcionario_id is None:
            denuncia.asignado_funcionario = funcionario
            DenunciaAsignaciones.objects.create(
                id=get_uuid(),
                denuncia=denuncia,
                funcionario=funcionario,
                asignado_en=timezone.now(),
                activo=True,
            )


        # ❌ Si ya la está tratando otro, bloquear respuesta
        elif denuncia.asignado_funcionario_id != funcionario.pk:
            messages.warning(
                request,
                f"⚠️ Esta denuncia ya está siendo atendida por {denuncia.asignado_funcionario.nombres} {denuncia.asignado_funcionario.apellidos}."
            )
            return redirect("web:denuncia_detail", pk=pk)

        #   Si responde, pasar a EN_PROCESO si estaba pendiente/en_revision/asignada
        if denuncia.estado in ["pendiente", "en_revision", "asignada"]:
            denuncia.estado = "en_proceso"

        denuncia.updated_at = timezone.now()
        denuncia.save(update_fields=["asignado_funcionario", "estado", "updated_at"])

        # historial
        DenunciaHistorial.objects.create(
            id=get_uuid(),
            estado_anterior=estado_anterior,
            estado_nuevo=denuncia.estado,
            comentario="Nueva respuesta añadida.",
            cambiado_por_funcionario=funcionario,
            created_at=timezone.now(),
            denuncia_id=denuncia.id,
        )

        # respuesta
        DenunciaRespuestas.objects.create(
            id=get_uuid(),
            denuncia=denuncia,
            funcionario=funcionario,
            mensaje=form.cleaned_data["mensaje"],
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
    import logging
    logger = logging.getLogger(__name__)

    try:
        notificar_respuesta(denuncia)
    except Exception as e:
        logger.exception("Fallo push Firebase: %s", e)

    messages.success(request, "  Respuesta enviada correctamente.")
    return redirect("web:denuncia_detail", pk=pk)




class MisDenunciasListView(LoginRequiredMixin, ListView):
    """
    Vista “Mis Denuncias” (para funcionario).
    Si quieres que sea para ciudadano, se cambia el filtro al ciudadano del usuario.
    """
    model = Denuncias
    template_name = "denuncias/mis_denuncias_list.html"
    context_object_name = "denuncias"
    paginate_by = 10
    login_url = "web:login"

    def get_queryset(self):
        funcionario = get_funcionario_from_web_user(self.request.user)
        if not funcionario:
            return Denuncias.objects.none()

        qs = (
            Denuncias.objects.filter(
                Q(asignado_funcionario=funcionario)
                | Q(denunciaasignaciones__funcionario=funcionario, denunciaasignaciones__activo=True)
            )
            .distinct()
            .select_related("ciudadano", "tipo_denuncia", "asignado_departamento", "asignado_funcionario")
            .order_by("-created_at")
        )

        estado = self.request.GET.get("estado")
        if estado:
            qs = qs.filter(estado=estado)

        tipo_denuncia = self.request.GET.get("tipo_denuncia")
        if tipo_denuncia:
            qs = qs.filter(tipo_denuncia_id=tipo_denuncia)

        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        funcionario = get_funcionario_from_web_user(self.request.user)
        context["funcionario"] = funcionario

        qs = self.get_queryset()
        context["total_denuncias"] = qs.count()
        context["denuncias_pendientes"] = qs.filter(estado="pendiente").count()
        context["denuncias_en_proceso"] = qs.filter(estado="en_proceso").count()
        context["denuncias_resueltas"] = qs.filter(estado="resuelta").count()

        context["tipos_denuncia"] = TiposDenuncia.objects.filter(activo=True)
        context["estado_actual"] = self.request.GET.get("estado", "")
        context["tipo_denuncia_actual"] = self.request.GET.get("tipo_denuncia", "")

        return context


# =========================================
# TipoDenuncia ↔ Departamento
# =========================================

class TipoDenunciaDepartamentoListView(FuncionarioRequiredMixin, ListView):
    model = TipoDenunciaDepartamento
    template_name = "tipo_denuncia_departamento/tipo_denuncia_departamento_list.html"
    context_object_name = "asignaciones"  #  CAMBIO
    login_url = "web:login"
    paginate_by = 10
    ordering = ["-created_at"]

    def get_queryset(self):
        return (TipoDenunciaDepartamento.objects
                .select_related("tipo_denuncia", "departamento")
                .order_by("-created_at"))


class TipoDenunciaDepartamentoCreateView(CrudMessageMixin, FuncionarioRequiredMixin, CreateView):
    model = TipoDenunciaDepartamento
    form_class = TipoDenunciaDepartamentoForm
    template_name = "tipo_denuncia_departamento/tipo_denuncia_departamento_form.html"
    success_url = reverse_lazy("web:tipo_denuncia_departamento_list")
    login_url = "web:login"

    def form_valid(self, form):
        obj = form.save(commit=False)
        now = timezone.now()
        obj.created_at = now
        obj.updated_at = now
        obj.save()
        return super().form_valid(form)


class TipoDenunciaDepartamentoDetailView(FuncionarioRequiredMixin, DetailView):
    model = TipoDenunciaDepartamento
    template_name = "tipo_denuncia_departamento/tipo_denuncia_departamento_detail.html"
    context_object_name = "asignacion"  # CAMBIO
    login_url = "web:login"


class TipoDenunciaDepartamentoUpdateView(CrudMessageMixin, FuncionarioRequiredMixin, UpdateView):
    model = TipoDenunciaDepartamento
    form_class = TipoDenunciaDepartamentoForm
    template_name = "tipo_denuncia_departamento/tipo_denuncia_departamento_form.html"
    success_url = reverse_lazy("web:tipo_denuncia_departamento_list")
    login_url = "web:login"

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.updated_at = timezone.now()
        obj.save()
        return super().form_valid(form)


class TipoDenunciaDepartamentoDeleteView(CrudMessageMixin, FuncionarioRequiredMixin, DeleteView):
    model = TipoDenunciaDepartamento
    template_name = "tipo_denuncia_departamento/tipo_denuncia_departamento_confirm_delete.html"
    context_object_name = "asignacion"  #  AGREGA
    success_url = reverse_lazy("web:tipo_denuncia_departamento_list")
    login_url = "web:login"

# =========================================
# Tipos de Denuncia
# =========================================

class TiposDenunciaListView(FuncionarioRequiredMixin, ListView):
    model = TiposDenuncia
    template_name = "tipos_denuncia/tipos_denuncia_list.html"
    context_object_name = "tipos"
    login_url = "web:login"
    ordering = ["-id"]
    paginate_by = 10


class TiposDenunciaCreateView(CrudMessageMixin, FuncionarioRequiredMixin, CreateView):
    model = TiposDenuncia
    form_class = TiposDenunciaForm
    template_name = "tipos_denuncia/tipos_denuncia_form.html"
    success_url = reverse_lazy("web:tipos_denuncia_list")
    login_url = "web:login"

    def form_valid(self, form):
        obj = form.save(commit=False)
        now = timezone.now()
        obj.created_at = now
        obj.updated_at = now
        obj.activo = True  #   por si acaso (regla del sistema)
        obj.save()
        return super().form_valid(form)

class TiposDenunciaDetailView(FuncionarioRequiredMixin, DetailView):
    model = TiposDenuncia
    template_name = "tipos_denuncia/tipos_denuncia_detail.html"
    context_object_name = "tipo_denuncia"
    login_url = "web:login"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tipo = self.object

        #   Relación correcta: TipoDenunciaDepartamento.tipo_denuncia
        rel = (TipoDenunciaDepartamento.objects
               .select_related("departamento")
               .filter(tipo_denuncia=tipo)
               .first())
        ctx["departamento_asignado"] = rel.departamento if rel else None

        #   Conteo correcto usando la tabla real Denuncias.tipo_denuncia
        ctx["total_denuncias"] = Denuncias.objects.filter(tipo_denuncia=tipo).count()

        return ctx


class TiposDenunciaUpdateView(CrudMessageMixin, FuncionarioRequiredMixin, UpdateView):
    model = TiposDenuncia
    form_class = TiposDenunciaForm
    template_name = "tipos_denuncia/tipos_denuncia_form.html"
    success_url = reverse_lazy("web:tipos_denuncia_list")
    login_url = "web:login"

    def form_valid(self, form):
        obj = form.save(commit=False)
        obj.updated_at = timezone.now()
        obj.save()
        return super().form_valid(form)

class TiposDenunciaDeleteView(CrudMessageMixin, FuncionarioRequiredMixin, DeleteView):
    model = TiposDenuncia
    template_name = "tipos_denuncia/tipos_denuncia_confirm_delete.html"
    success_url = reverse_lazy("web:tipos_denuncia_list")
    login_url = "web:login"
    context_object_name = "tipo_denuncia"  #   para que tu template lo reciba también

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tipo = self.object
        ctx["total_denuncias"] = Denuncias.objects.filter(tipo_denuncia=tipo).count()  #   modelo real
        return ctx

# =========================================
# IA (LLM)
# =========================================
def _extract_json_object(text: str):
    """Intenta sacar el primer objeto JSON de un texto (por si el modelo mete texto extra)."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return match.group(0) if match else None


@login_required
@require_POST
def llm_response(request, denuncia_id):
    if not client:
        return JsonResponse({"success": False, "error": "Servicio de IA no configurado (falta OPENAI_API_KEY)"}, status=503)

    #  proteger: solo funcionarios/superuser
    funcionario = get_funcionario_from_web_user(request.user)
    if not (request.user.is_superuser or funcionario):
        return JsonResponse({"success": False, "error": "No autorizado"}, status=403)

    try:
        denuncia = Denuncias.objects.select_related(
            "ciudadano", "tipo_denuncia", "asignado_departamento", "asignado_funcionario"
        ).get(id=denuncia_id)

        #   tomar denuncia (si está libre) o bloquear si ya la tomó otro
        if not request.user.is_superuser:
            ok, msg = tomar_denuncia_si_libre(
                denuncia,
                funcionario,
                motivo="Denuncia tomada al generar respuesta con IA.",
            )
            if not ok:
                return JsonResponse({"success": False, "error": msg}, status=409)

        func_name = get_web_user_name_from_funcionario(denuncia.asignado_funcionario)

        prompt = f"""
Eres un asistente especializado en gestión de denuncias ciudadanas para la Municipalidad de Salcedo, Cotopaxi, Ecuador.

Responde EXCLUSIVAMENTE en JSON válido, sin texto adicional.

Formato requerido:
{{
  "resumen": "string",
  "sugerencias_accion": "string"
}}

Datos de la denuncia:
- Ciudadano: {f"{denuncia.ciudadano.nombres} {denuncia.ciudadano.apellidos}" if denuncia.ciudadano else "Desconocido"}
- Descripción: {denuncia.descripcion}
- Referencia: {denuncia.referencia}
- Tipo: {denuncia.tipo_denuncia.nombre if denuncia.tipo_denuncia else "No especificado"}
- Estado: {denuncia.estado}
- Departamento: {denuncia.asignado_departamento.nombre if denuncia.asignado_departamento else "No asignado"}
- Funcionario: {func_name}

Responde en español con tono empático.
""".strip()

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Responde siempre en JSON válido."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
        )

        raw_text = (resp.choices[0].message.content or "").strip()
        json_text = _extract_json_object(raw_text)

        if not json_text:
            return JsonResponse({"success": True, "response": raw_text})

        data = json.loads(json_text)
        formatted = f"RESUMEN:\n{data.get('resumen','')}\n\nSUGERENCIAS DE ACCIÓN:\n{data.get('sugerencias_accion','')}"
        return JsonResponse({"success": True, "response": formatted})

    except Denuncias.DoesNotExist:
        return JsonResponse({"success": False, "error": "Denuncia no encontrada"}, status=404)
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "Error al decodificar JSON del modelo"}, status=500)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required
@require_POST
def resolver_denuncia(request, denuncia_id):
    # 1) proteger: solo funcionarios/superuser
    funcionario = get_funcionario_from_web_user(request.user)
    if not (request.user.is_superuser or funcionario):
        return render(request, "errors/403.html", status=403)

    denuncia = get_object_or_404(
        Denuncias.objects.select_related(
            "ciudadano", "tipo_denuncia", "asignado_departamento", "asignado_funcionario"
        ),
        id=denuncia_id,
    )

    # 2) tomar denuncia (si está libre) o bloquear si ya la tomó otro
    if not request.user.is_superuser:
        ok, msg = tomar_denuncia_si_libre(
            denuncia,
            funcionario,
            motivo="Denuncia tomada al intentar resolver.",
        )
        if not ok:
            return render(request, "errors/403.html", status=403)

    # 3) marcar resuelta + historial
    estado_anterior = denuncia.estado
    denuncia.estado = "resuelta"
    denuncia.save(update_fields=["estado"])

    funcionario_cambio = funcionario  # ya lo tienes

    DenunciaHistorial.objects.create(
        id=get_uuid(),
        estado_anterior=estado_anterior,
        estado_nuevo="resuelta",
        comentario="Denuncia marcada como resuelta.",
        cambiado_por_funcionario=funcionario_cambio,
        created_at=timezone.now(),
        denuncia_id=denuncia.id,
    )

    # 4) IA (solo si está configurada)
    raw_text = ""
    if client:
        func_name = get_web_user_name_from_funcionario(denuncia.asignado_funcionario)
        prompt = f"""
Eres un asistente especializado en gestión de denuncias ciudadanas para la Municipalidad de Salcedo, Cotopaxi, Ecuador.

Datos de la denuncia:
- Ciudadano: {f"{denuncia.ciudadano.nombres} {denuncia.ciudadano.apellidos}" if denuncia.ciudadano else "Desconocido"}
- Descripción: {denuncia.descripcion}
- Referencia: {denuncia.referencia}
- Tipo: {denuncia.tipo_denuncia.nombre if denuncia.tipo_denuncia else "No especificado"}
- Estado: {denuncia.estado}
- Departamento: {denuncia.asignado_departamento.nombre if denuncia.asignado_departamento else "No asignado"}
- Funcionario: {func_name}

Responde en español, solo texto plano, con tono empático.
""".strip()

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Responde siempre en texto plano."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=500,
        )
        raw_text = (resp.choices[0].message.content or "").strip()
    else:
        raw_text = "Denuncia resuelta. Gracias por reportar. Su caso fue atendido."

    # 5) respuesta automática
    DenunciaRespuestas.objects.create(
        id=get_uuid(),
        denuncia=denuncia,
        funcionario=funcionario_cambio,
        mensaje=raw_text,
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )

    import logging
    logger = logging.getLogger(__name__)

    try:
        notificar_respuesta(denuncia)
    except Exception as e:
        logger.exception("Fallo al enviar push (Firebase). Continúo sin push: %s", e)

    messages.success(request, "  Denuncia marcada como resuelta.")
    return redirect("web:denuncia_detail", pk=denuncia_id)

#-----------------------------------
# rechazar denuncia texto
#-----------------------------------
@login_required
@require_POST
def rechazar_denuncia(request, denuncia_id):
    funcionario = get_funcionario_from_web_user(request.user)
    if not (request.user.is_superuser or funcionario):
        return render(request, "errors/403.html", status=403)

    motivo = (request.POST.get("motivo") or "").strip()
    if not motivo:
        messages.error(request, "❌ Debes escribir el motivo del rechazo.")
        return redirect("web:denuncia_detail", pk=denuncia_id)

    with transaction.atomic():
        denuncia = get_object_or_404(
            Denuncias.objects.select_for_update(),  # ✅ SIN joins
            id=denuncia_id,
        )


        #   tomar denuncia (si está libre) o bloquear si ya la tomó otro
        if not request.user.is_superuser:
            ok, msg = tomar_denuncia_si_libre(
                denuncia,
                funcionario,
                motivo="Denuncia tomada al intentar rechazar.",
            )
            if not ok:
                messages.warning(request, msg)
                return redirect("web:denuncia_detail", pk=denuncia_id)

        estado_anterior = denuncia.estado
        denuncia.estado = "rechazada"  # <- asegúrate que exista en tu sistema
        denuncia.updated_at = timezone.now()
        denuncia.save(update_fields=["estado", "updated_at", "asignado_funcionario"])

        # historial
        DenunciaHistorial.objects.create(
            id=get_uuid(),
            estado_anterior=estado_anterior,
            estado_nuevo="rechazada",
            comentario=f"Denuncia rechazada. Motivo: {motivo}",
            cambiado_por_funcionario=funcionario,
            created_at=timezone.now(),
            denuncia_id=denuncia.id,
        )

        # respuesta (mensaje al ciudadano)
        mensaje = (
            "Estimado/a ciudadano/a,\n\n"
            "Su denuncia no pudo ser aceptada o procesada por el siguiente motivo:\n"
            f"- {motivo}\n\n"
            "Si desea, puede actualizar la información y volver a reportarla. "
            "Estamos gustosos de ayudarle.\n"
        )

        DenunciaRespuestas.objects.create(
            id=get_uuid(),
            denuncia=denuncia,
            funcionario=funcionario,
            mensaje=mensaje,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )

    import logging
    logger = logging.getLogger(__name__)

    try:
        notificar_respuesta(denuncia)
    except Exception as e:
        logger.exception("Fallo push Firebase: %s", e)

    messages.success(request, "  Denuncia rechazada correctamente.")
    return redirect("web:denuncia_detail", pk=denuncia_id)


#------------------------------------
# rechazar denuncia con ia
#-----------------------------------
@login_required
@require_POST
def llm_rechazo_response(request, denuncia_id):
    if not client:
        return JsonResponse({"success": False, "error": "Servicio de IA no configurado (falta OPENAI_API_KEY)"}, status=503)

    funcionario = get_funcionario_from_web_user(request.user)
    if not (request.user.is_superuser or funcionario):
        return JsonResponse({"success": False, "error": "No autorizado"}, status=403)

    try:
        denuncia = Denuncias.objects.select_related(
            "ciudadano", "tipo_denuncia", "asignado_departamento", "asignado_funcionario"
        ).get(id=denuncia_id)

        #   tomar denuncia (si está libre) o bloquear si ya la tomó otro
        if not request.user.is_superuser:
            ok, msg = tomar_denuncia_si_libre(
                denuncia,
                funcionario,
                motivo="Denuncia tomada al generar rechazo con IA.",
            )
            if not ok:
                return JsonResponse({"success": False, "error": msg}, status=409)

        motivo = ""
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
            motivo = (body.get("motivo") or "").strip()
        except Exception:
            motivo = ""

        func_name = get_web_user_name_from_funcionario(denuncia.asignado_funcionario)

        prompt = f"""
Eres un asistente especializado en gestión de denuncias ciudadanas para la Municipalidad de Salcedo, Cotopaxi, Ecuador.

Redacta un mensaje CALIDO y RESPETUOSO para informar al ciudadano que su denuncia será RECHAZADA/NO PROCESADA.
Incluye:
- saludo
- explicación breve
- el motivo (si se proporciona)
- invitación a corregir y volver a reportar
- cierre amable

Datos:
- Ciudadano: {f"{denuncia.ciudadano.nombres} {denuncia.ciudadano.apellidos}" if denuncia.ciudadano else "Desconocido"}
- Tipo: {denuncia.tipo_denuncia.nombre if denuncia.tipo_denuncia else "No especificado"}
- Descripción: {denuncia.descripcion}
- Referencia: {denuncia.referencia}
- Departamento: {denuncia.asignado_departamento.nombre if denuncia.asignado_departamento else "No asignado"}
- Funcionario: {func_name}
- Motivo del rechazo (si existe): {motivo if motivo else "No proporcionado"}

Responde en español, solo texto plano.
""".strip()

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Responde siempre en texto plano."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=400,
        )

        raw_text = (resp.choices[0].message.content or "").strip()
        return JsonResponse({"success": True, "response": raw_text})

    except Denuncias.DoesNotExist:
        return JsonResponse({"success": False, "error": "Denuncia no encontrada"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)

# =========================================
# FUNCIONARIOS (CRUD)
# =========================================
from django.contrib import messages

class FuncionariosListView(FuncionarioRequiredMixin, ListView):
    model = Funcionarios
    template_name = "funcionarios/funcionario_list.html"
    context_object_name = "funcionarios"
    paginate_by = 10
    login_url = "web:login"

    def get_queryset(self):
        # OJO: Funcionarios y Departamentos vienen de db.models (arriba ya los importaste)
        return Funcionarios.objects.select_related("usuario", "departamento").order_by("-created_at")


class FuncionariosCreateView(CrudMessageMixin, FuncionarioRequiredMixin, CreateView):
    model = Funcionarios
    form_class = FuncionarioForm
    template_name = "funcionarios/funcionario_form.html"
    success_url = reverse_lazy("web:funcionario_list")
    login_url = "web:login"

    def form_valid(self, form):
        messages.success(self.request, " Funcionario creado correctamente.")
        return super().form_valid(form)



from django.contrib.auth.models import User

class FuncionariosUpdateView(CrudMessageMixin, FuncionarioRequiredMixin, UpdateView):
    model = Funcionarios
    form_class = FuncionarioForm
    template_name = "funcionarios/funcionario_form.html"
    success_url = reverse_lazy("web:funcionario_list")
    login_url = "web:login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        #  traer el auth_user correcto (entero) desde la tabla puente
        link = (
            FuncionarioWebUser.objects
            .select_related("web_user")  #  NO "usuario"
            .filter(funcionario=self.object)
            .first()
        )
        context["web_user"] = link.web_user if link else None
        return context

    def get_form(self, form_class=None):
        form = super().get_form(form_class)

        #  Si tu form tiene un campo para auth_user (por ejemplo: web_user o usuario_web)
        link = (
            FuncionarioWebUser.objects
            .select_related("web_user")
            .filter(funcionario=self.object)
            .first()
        )
        web_user_obj = link.web_user if link else None

        # 1) Si el campo se llama web_user
        if "web_user" in form.fields:
            form.fields["web_user"].initial = web_user_obj  #  objeto User (id entero)

        # 2) Si por tu diseño lo llamaste "usuario" pero en realidad es auth_user
        # (esto evita que se le meta el UUID de Usuarios)
        if "usuario" in form.fields:
            try:
                qs_model = getattr(form.fields["usuario"].queryset, "model", None)
                if qs_model == User:
                    form.fields["usuario"].initial = web_user_obj
            except Exception:
                pass

        return form

    def form_valid(self, form):
        messages.success(self.request, " Funcionario actualizado correctamente.")
        return super().form_valid(form)



class FuncionariosDetailView(FuncionarioRequiredMixin, DetailView):
    model = Funcionarios
    template_name = "funcionarios/funcionario_detail.html"
    context_object_name = "object"
    login_url = "web:login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        link = (
            FuncionarioWebUser.objects
            .select_related("web_user")
            .filter(funcionario=self.object)
            .first()
        )
        context["web_user"] = link.web_user if link else None
        return context


class FuncionariosDeleteView(CrudMessageMixin, FuncionarioRequiredMixin, DeleteView):
    model = Funcionarios
    template_name = "funcionarios/funcionario_confirm_delete.html"
    success_url = reverse_lazy("web:funcionario_list")
    login_url = "web:login"

    def delete(self, request, *args, **kwargs):
        messages.success(self.request, "🗑️ Funcionario eliminado.")
        return super().delete(request, *args, **kwargs)

# =========================================
# DEPARTAMENTOS (CRUD)
# =========================================

class DepartamentosListView(FuncionarioRequiredMixin, ListView):
    model = Departamentos
    template_name = "departamentos/departamento_list.html"
    context_object_name = "departamentos"
    paginate_by = 10
    login_url = "web:login"

    def get_queryset(self):
        return Departamentos.objects.order_by("nombre")


class DepartamentosCreateView(CrudMessageMixin, FuncionarioRequiredMixin, CreateView):
    model = Departamentos
    form_class = DepartamentoForm
    template_name = "departamentos/departamento_form.html"
    success_url = reverse_lazy("web:departamento_list")
    login_url = "web:login"


class DepartamentosDetailView(FuncionarioRequiredMixin, DetailView):
    model = Departamentos
    template_name = "departamentos/departamento_detail.html"
    context_object_name = "departamento"
    login_url = "web:login"


class DepartamentosUpdateView(CrudMessageMixin, FuncionarioRequiredMixin, UpdateView):
    model = Departamentos
    form_class = DepartamentoForm
    template_name = "departamentos/departamento_form.html"
    success_url = reverse_lazy("web:departamento_list")
    login_url = "web:login"


class DepartamentosDeleteView(CrudMessageMixin, FuncionarioRequiredMixin, DeleteView):
    model = Departamentos
    template_name = "departamentos/departamento_confirm_delete.html"
    success_url = reverse_lazy("web:departamento_list")
    login_url = "web:login"


# =========================================
# WEB USERS (Django auth_user CRUD)
# =========================================
from django.db.models import Prefetch
from django.contrib.auth.models import User

from web.models import FuncionarioWebUser

from web.services.delete_rules import can_hard_delete_user


class WebUserListView(LoginRequiredMixin, CustomPermissionRequiredMixin, ListView):
    model = User
    template_name = "webusers/webuser_list.html"
    context_object_name = "webusers"
    paginate_by = 10
    permission_required = "auth.view_user"
    login_url = "web:login"

    def get_queryset(self):
        # Prefetch de la tabla puente para que luego no haya N+1 al mostrar funcionario
        return (
            User.objects.all()
            .order_by("username")
            .prefetch_related("groups", "user_permissions")
            .prefetch_related(
                Prefetch(
                    "funcionariowebuser_set",  # <-- si tu related_name es otro, cámbialo
                    queryset=FuncionarioWebUser.objects.select_related("funcionario"),
                )
            )
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Inyectamos el flag can_delete en cada user de la página actual
        for u in ctx["page_obj"]:
            u.can_delete = can_hard_delete_user(u)

        return ctx

class WebUserCreateView(CrudMessageMixin, LoginRequiredMixin, CustomPermissionRequiredMixin, CreateView):
    model = User
    form_class = WebUserForm
    template_name = "webusers/webuser_form.html"
    success_url = reverse_lazy("web:webuser_list")
    permission_required = "auth.add_user"
    login_url = "web:login"

    def form_valid(self, form):
        user = form.save(commit=False)

        #   Forzar reglas internas (para que el signal dispare)
        user.is_staff = True
        user.is_active = True
        user.is_superuser = False  # si quieres permitir super admin, lo hacemos aparte

        password = form.cleaned_data.get("password")
        user.set_password(password)

        user.save()
        form.save_m2m()
        return redirect(self.success_url)


class WebUserDetailView(LoginRequiredMixin, CustomPermissionRequiredMixin, DetailView):
    model = User
    template_name = "webusers/webuser_detail.html"
    context_object_name = "web_user_detail"
    permission_required = "auth.view_user"
    login_url = "web:login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["groups"] = self.object.groups.all()
        #context["permissions"] = self.object.user_permissions.all()
        return context


class WebUserUpdateView(CrudMessageMixin, LoginRequiredMixin, CustomPermissionRequiredMixin, UpdateView):
    model = User
    form_class = WebUserForm
    template_name = "webusers/webuser_form.html"
    success_url = reverse_lazy("web:webuser_list")
    permission_required = "auth.change_user"
    login_url = "web:login"

    def form_valid(self, form):
        user = form.save(commit=False)
        password = form.cleaned_data.get("password")
        if password:
            user.set_password(password)
        user.save()
        form.save_m2m()
        return redirect(self.success_url)



class WebUserDeleteView(DeleteView):
    model = User
    template_name = "webusers/webuser_confirm_delete.html"
    success_url = reverse_lazy("web:webuser_list")

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # si pidió hard delete explícito
        hard_requested = (request.POST.get("hard_delete") == "1")

        allowed = can_hard_delete_user(self.object)

        if hard_requested and allowed:
            #   hard delete real (luego el signal pre_delete limpia el dominio)
            messages.success(request, "  Usuario eliminado definitivamente.")
            return super().post(request, *args, **kwargs)

        #   si NO se permite hard delete, o si no lo pidió: soft disable
        soft_disable_web_user(self.object)

        if not allowed:
            messages.warning(request, "⚠️ No se puede eliminar porque tiene denuncias tratadas. Se desactivó el usuario.")
        else:
            messages.info(request, "  Usuario desactivado (soft delete).")

        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["can_hard_delete"] = can_hard_delete_user(self.object)
        return ctx
    
#-----------------------------
# pdf
#---------------------------------
from django.http import HttpResponse, Http404
from django.template.loader import get_template
from django.shortcuts import get_object_or_404
from django.conf import settings
from xhtml2pdf import pisa
import os

from db.models import Denuncias, DenunciaRespuestas  # ajusta si tu import cambia

def link_callback(uri, rel):
    """
    Permite a xhtml2pdf encontrar archivos estáticos (logo, etc.)
    """
    # Ej: /static/assets/img/logo.png
    if uri.startswith(settings.STATIC_URL):
        path = os.path.join(settings.STATIC_ROOT, uri.replace(settings.STATIC_URL, ""))
        if os.path.isfile(path):
            return path

    # Si usas MEDIA en PDF (opcional)
    if hasattr(settings, "MEDIA_URL") and uri.startswith(settings.MEDIA_URL):
        path = os.path.join(settings.MEDIA_ROOT, uri.replace(settings.MEDIA_URL, ""))
        if os.path.isfile(path):
            return path

    return uri  # fallback

def denuncia_pdf(request, pk):
    denuncia = get_object_or_404(Denuncias, pk=pk)

    # Si quieres solo resueltas:
    if denuncia.estado != "resuelta" and denuncia.estado != "rechazada":
        raise Http404("La denuncia no está finalizada")

    # ✅ Última respuesta (la más reciente)
    respuesta = (
        DenunciaRespuestas.objects
        .filter(denuncia=denuncia)
        .order_by("-created_at")     # <-- AQUÍ está el fix del 500
        .first()
    )

    template = get_template("denuncias/denuncia_pdf.html")
    html = template.render({
        "denuncia": denuncia,
        "respuesta": respuesta,
        "request": request,
    })

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="denuncia_{denuncia.id}.pdf"'

    pisa_status = pisa.CreatePDF(
        html,
        dest=response,
        encoding="utf-8",
        link_callback=link_callback
    )

    if pisa_status.err:
        return HttpResponse("Error al generar PDF", status=500)

    return response

# web/views.py
from django.http import HttpResponse, Http404
from django.contrib.auth.decorators import login_required

from db.models import DenunciaArchivo, Denuncias  # ajusta si el import cambia

def _safe_filename(name: str | None) -> str | None:
    if not name:
        return None
    return name.replace("\n", "").replace("\r", "").replace('"', "").strip()

def _resolver_url_archivo_web(raw_url: str | None) -> str:
    """
    Convierte una URL guardada en BD a una URL usable en WEB.
    Soporta:
    - /api/denuncias/archivos/denuncia/<uuid>/
    - https://.../media/...
    - /media/...
    """
    raw_url = (raw_url or "").strip()
    if not raw_url:
        return ""

    m = re.search(r"/api/denuncias/archivos/denuncia/([0-9a-fA-F-]+)/?$", raw_url)
    if m:
        archivo_id = m.group(1)
        return reverse("web:web_denuncia_archivo_ver", args=[archivo_id])

    return raw_url

def _file_response(obj):
    content_type = getattr(obj, "content_type", None) or "application/octet-stream"
    resp = HttpResponse(bytes(obj.data), content_type=content_type)

    filename = _safe_filename(getattr(obj, "filename", None))
    if filename:
        resp["Content-Disposition"] = f'inline; filename="{filename}"'

    resp["X-Content-Type-Options"] = "nosniff"
    resp["Cache-Control"] = "no-store"
    return resp

@login_required(login_url="web:login")
def web_denuncia_archivo_ver(request, archivo_id):
    """
    WEB: sirve evidencias BIN para funcionarios/superuser (session auth).
    """
    # solo funcionarios o superuser (tu regla)
    funcionario = get_funcionario_from_web_user(request.user)
    if not (request.user.is_superuser or funcionario):
        raise Http404("No autorizado")

    try:
        obj = DenunciaArchivo.objects.select_related("denuncia").get(id=archivo_id)
    except DenunciaArchivo.DoesNotExist:
        raise Http404("Archivo no existe")

    # Admin/TICS ve todo
    is_admin = request.user.is_superuser or request.user.groups.filter(name="TICS_ADMIN").exists()
    if not is_admin:
        # funcionario SOLO puede ver denuncias de su depto
        if not funcionario or not funcionario.departamento_id:
            raise Http404("No autorizado")
        if obj.denuncia.asignado_departamento_id != funcionario.departamento_id:
            raise Http404("No autorizado")

    return _file_response(obj)

@login_required(login_url="web:login")
def web_denuncia_firma_ver(request, denuncia_id):
    """
    WEB: sirve la firma BIN para funcionarios/superuser (session auth).
    """
    funcionario = get_funcionario_from_web_user(request.user)
    if not (request.user.is_superuser or funcionario):
        raise Http404("No autorizado")

    denuncia = get_object_or_404(Denuncias, id=denuncia_id)
    firma = get_object_or_404(DenunciaFirmas, denuncia_id=denuncia_id)

    # Admin/TICS ve todo
    is_admin = request.user.is_superuser or request.user.groups.filter(name="TICS_ADMIN").exists()
    if not is_admin:
        if not funcionario or not funcionario.departamento_id:
            raise Http404("No autorizado")
        if denuncia.asignado_departamento_id != funcionario.departamento_id:
            raise Http404("No autorizado")

    # Caso 1: la firma guarda binario directo
    if hasattr(firma, "data") and getattr(firma, "data", None):
        return _file_response(firma)

    # Caso 2: la firma tiene FK archivo
    if hasattr(firma, "archivo") and getattr(firma, "archivo", None):
        return _file_response(firma.archivo)

    # Caso 3: la firma tiene archivo_id que apunta a DenunciaArchivo
    if hasattr(firma, "archivo_id") and getattr(firma, "archivo_id", None):
        try:
            archivo = DenunciaArchivo.objects.get(id=firma.archivo_id)
            return _file_response(archivo)
        except DenunciaArchivo.DoesNotExist:
            raise Http404("Archivo de firma no existe")

    raise Http404("Firma no disponible")