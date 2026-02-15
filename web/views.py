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

def mi_vista(request):
    context = {
        "menus_principales": build_menus_for_user(request.user),
    }
    return render(request, "x.html", context)

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
    if denuncia.asignado_funcionario_id and denuncia.asignado_funcionario_id != funcionario.id:
        nombre_otro = f"{denuncia.asignado_funcionario.nombres} {denuncia.asignado_funcionario.apellidos}"
        return False, f"Esta denuncia ya está siendo atendida por {nombre_otro}."

    # Si está libre, tomarla
    if not denuncia.asignado_funcionario_id:
        estado_anterior = denuncia.estado

        denuncia.asignado_funcionario = funcionario

        # ✅ Cuando se toma por atención, pasa a en_proceso si aún no está resuelta/rechazada
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
        DenunciaAsignaciones.objects.create(
            id=get_uuid(),
            denuncia=denuncia,
            funcionario=funcionario,
            asignado_en=timezone.now(),
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
            Denuncias.objects.select_for_update().select_related("asignado_funcionario"),
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
        # SUPERADMIN (TICS) ve TODO
        current_user_department = None
    else:
        # Funcionario normal: necesita existir y tener depto
        funcionario = get_funcionario_from_web_user(user)
        if not funcionario:
            return render(request, "errors/403.html", status=403)

        current_user_department = getattr(funcionario, "departamento", None)

        if current_user_department:
            denuncias_qs = denuncias_qs.filter(asignado_departamento=current_user_department)
            funcionarios_qs = funcionarios_qs.filter(departamento=current_user_department)
            departamentos_qs = departamentos_qs.filter(pk=current_user_department.pk)
        else:
            # Si no tiene depto, no debería ver nada (o puedes permitirle ver "sin asignar")
            denuncias_qs = denuncias_qs.none()
            funcionarios_qs = funcionarios_qs.none()
            departamentos_qs = departamentos_qs.none()
    
    # =========================
    # 3) Fechas
    # =========================
    fecha_hace_30_dias = timezone.now() - timedelta(days=30)
    fecha_hace_7_dias = timezone.now() - timedelta(days=7)

    # =========================
    # 4) KPIs
    # =========================
    total_denuncias = denuncias_qs.count()
    denuncias_este_mes = denuncias_qs.filter(created_at__gte=fecha_hace_30_dias).count()

    denuncias_pendientes = denuncias_qs.filter(estado="pendiente").count()
    denuncias_en_proceso = denuncias_qs.filter(estado="en_proceso").count()

    # OJO: tu estado en BD es "resuelta"
    denuncias_resueltas = denuncias_qs.filter(estado="resuelta").count()

    # =========================
    # 5) Charts
    # =========================
    chart_kpi2 = ColumnChart(
        {"Pendientes": denuncias_pendientes, "En Proceso": denuncias_en_proceso, "Resueltas": denuncias_resueltas},
        title="Denuncias por estado",
        download={"filename": "chart_kpi2"},
    )

    # Ciudadanos: si quieres que también se filtre por depto para funcionario, déjalo así
    # (si quieres global para todos, usa Ciudadanos.objects.all())
    total_ciudadanos = Ciudadanos.objects.count()
    ciudadanos_este_mes = Ciudadanos.objects.filter(created_at__gte=fecha_hace_30_dias).count()

    total_funcionarios = funcionarios_qs.count()
    funcionarios_activos = funcionarios_qs.filter(activo=True).count()

    total_departamentos = departamentos_qs.count()
    departamentos_activos = departamentos_qs.filter(activo=True).count()

    promedio_denuncias_depto = total_denuncias / max(departamentos_activos, 1)

    denuncias_por_tipo = (
        denuncias_qs.values("tipo_denuncia__nombre")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    chart_kpi7 = PieChart(
        {i["tipo_denuncia__nombre"]: i["count"] for i in denuncias_por_tipo if i["tipo_denuncia__nombre"]},
        title="Denuncias por tipo",
        donut=True,
        download={"filename": "chart_kpi7"},
    )

    # Por departamento
    denuncias_por_departamento_data = (
        denuncias_qs.filter(asignado_departamento__isnull=False)
        .values("asignado_departamento__nombre", "asignado_departamento__color_hex")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    dept_data = {}
    dept_colors = []
    for item in denuncias_por_departamento_data:
        dept_data[item["asignado_departamento__nombre"]] = item["count"]
        dept_colors.append(item["asignado_departamento__color_hex"] or "#0d6efd")

    chart_denuncias_departamento = BarChart(
        dept_data,
        title="Número de Denuncias por Departamento",
        xtitle="Cantidad",
        ytitle="Departamento",
        colors=dept_colors,
    )

    # Top ciudadanos
    ciudadanos_top_data = (
        denuncias_qs.values("ciudadano__nombres", "ciudadano__apellidos")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    chart_ciudadanos_top = BarChart(
        {f"{i['ciudadano__nombres']} {i['ciudadano__apellidos']}": i["count"] for i in ciudadanos_top_data},
        title="Ciudadanos con más Denuncias (Top 10)",
        xtitle="Cantidad",
        ytitle="Ciudadano",
    )

    # Semana / Mes
    denuncias_semana_data = (
        denuncias_qs.filter(created_at__gte=fecha_hace_30_dias)
        .annotate(semana=TruncWeek("created_at"))
        .values("semana")
        .annotate(count=Count("id"))
        .order_by("semana")
    )

    chart_denuncias_semana = LineChart(
        {i["semana"].strftime("%Y-%m-%d"): i["count"] for i in denuncias_semana_data if i["semana"]},
        title="Denuncias por Semana",
        xtitle="Semana",
        ytitle="Cantidad",
        download={"filename": "chart_denuncias_semana"},
    )

    denuncias_mes_data = (
        denuncias_qs.filter(created_at__gte=fecha_hace_30_dias)
        .annotate(mes=TruncMonth("created_at"))
        .values("mes")
        .annotate(count=Count("id"))
        .order_by("mes")
    )

    chart_denuncias_mes = LineChart(
        {i["mes"].strftime("%Y-%m"): i["count"] for i in denuncias_mes_data if i["mes"]},
        title="Denuncias por Mes",
        xtitle="Mes",
        ytitle="Cantidad",
    )

    chart_estado_denuncias = PieChart(
        {"Resueltas": denuncias_resueltas, "Pendientes": denuncias_pendientes, "En Proceso": denuncias_en_proceso},
        title="Estado de Denuncias",
        donut=True,
    )

    tasa_resolucion = (denuncias_resueltas / total_denuncias) * 100 if total_denuncias > 0 else 0

    # =========================
    # 6) Mapa (orden y limite)
    # =========================
    denuncias_mapa = (
        denuncias_qs.select_related("ciudadano", "tipo_denuncia", "asignado_departamento")
        .order_by("-created_at")[:100]
    )

    context = {
        "total_denuncias": total_denuncias,
        "denuncias_este_mes": denuncias_este_mes,
        "denuncias_pendientes": denuncias_pendientes,
        "denuncias_en_proceso": denuncias_en_proceso,
        "denuncias_resueltas": denuncias_resueltas,
        "total_ciudadanos": total_ciudadanos,
        "ciudadanos_este_mes": ciudadanos_este_mes,
        "total_funcionarios": total_funcionarios,
        "funcionarios_activos": funcionarios_activos,
        "total_departamentos": total_departamentos,
        "departamentos_activos": departamentos_activos,
        "promedio_denuncias_depto": round(promedio_denuncias_depto, 2),
        "tasa_resolucion": round(tasa_resolucion, 1),
        "denuncias_mapa": denuncias_mapa,
        "denuncias_por_tipo": denuncias_por_tipo,                 # 👈 para la lista del template
        "departamentos_con_denuncias": list(denuncias_por_departamento_data[:10]),  # 👈 si lo usas como lista
        "chart_denuncias_departamento": chart_denuncias_departamento,
        "chart_ciudadanos_top": chart_ciudadanos_top,
        "chart_denuncias_semana": chart_denuncias_semana,
        "chart_denuncias_mes": chart_denuncias_mes,
        "chart_estado_denuncias": chart_estado_denuncias,
        "chart_kpi2": chart_kpi2,
        "chart_kpi7": chart_kpi7,
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
    paginate_by = 15


class GrupoCreateView(CrudMessageMixin, LoginRequiredMixin, CustomPermissionRequiredMixin, CreateView):
    model = Group
    form_class = GrupoForm
    template_name = "grupos/grupo_form.html"
    success_url = reverse_lazy("web:grupo_list")
    permission_required = "auth.add_group"
    login_url = "web:login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        if form:
            selected_ids = [str(pk) for pk in form.data.getlist("permissions")] if form.is_bound else []
            context["selected_ids"] = selected_ids
        return context


class GrupoUpdateView(CrudMessageMixin, LoginRequiredMixin, CustomPermissionRequiredMixin, UpdateView):
    model = Group
    form_class = GrupoForm
    template_name = "grupos/grupo_form.html"
    success_url = reverse_lazy("web:grupo_list")
    permission_required = "auth.change_group"
    login_url = "web:login"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form = context.get("form")
        if form:
            if form.is_bound:
                selected_ids = form.data.getlist("permissions")
            else:
                selected_ids = list(form.instance.permissions.values_list("id", flat=True)) if form.instance.pk else []
            context["selected_ids"] = [str(pk) for pk in selected_ids]
        return context


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


class MenuUpdateView(LoginRequiredMixin, SuperUserRequiredMixin, UpdateView):
    model = Menus
    form_class = MenuForm
    template_name = "menus/menu_form.html"
    success_url = reverse_lazy("web:menu_list")
    login_url = "web:login"


class MenuDeleteView(LoginRequiredMixin, SuperUserRequiredMixin, DeleteView):
    model = Menus
    template_name = "menus/menu_confirm_delete.html"
    success_url = reverse_lazy("web:menu_list")
    login_url = "web:login"


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
    paginate_by = 15


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
    paginate_by = 20

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

        # Asignaciones
        context["asignaciones"] = (
            DenunciaAsignaciones.objects.filter(denuncia=denuncia)
            .select_related("funcionario")
            .order_by("-asignado_en")
        )

        # Evidencias
        context["evidencias"] = DenunciaEvidencias.objects.filter(denuncia=denuncia).order_by("-created_at")

        # Historial (paginado)
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

        # Respuestas
        context["respuestas"] = (
            DenunciaRespuestas.objects.filter(denuncia=denuncia)
            .select_related("funcionario")
            .order_by("-created_at")
        )

        # 🔒 Lock: puede responder?
        funcionario = get_funcionario_from_web_user(user)

        if self._is_admin(user):
            puede_responder = True
        else:
            puede_responder = bool(
                funcionario and (
                    (not denuncia.asignado_funcionario_id) or (denuncia.asignado_funcionario_id == funcionario.id)
                )
            )

        context["puede_responder"] = puede_responder

        # Firma OneToOne
        firma = DenunciaFirmas.objects.filter(denuncia_id=denuncia.id).first()
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

        # ✅ Para volver exacto a donde estabas (lista con filtros/página)
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
        # ✅ Al guardar, vuelve con filtros/página si venían
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

        messages.success(self.request, "✅ Denuncia actualizada correctamente.")
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

        # ✅ Si nadie la está tratando, el primero que responde la “toma”
        if denuncia.asignado_funcionario_id is None:
            denuncia.asignado_funcionario = funcionario

        # ❌ Si ya la está tratando otro, bloquear respuesta
        elif denuncia.asignado_funcionario_id != funcionario.pk:
            messages.warning(
                request,
                f"⚠️ Esta denuncia ya está siendo atendida por {denuncia.asignado_funcionario.nombres} {denuncia.asignado_funcionario.apellidos}."
            )
            return redirect("web:denuncia_detail", pk=pk)

        # ✅ Si responde, pasar a EN_PROCESO si estaba pendiente/en_revision/asignada
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

    notificar_respuesta(denuncia)
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
    paginate_by = 15
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
    paginate_by = 15


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
        obj.activo = True  # ✅ por si acaso (regla del sistema)
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

        # ✅ Relación correcta: TipoDenunciaDepartamento.tipo_denuncia
        rel = (TipoDenunciaDepartamento.objects
               .select_related("departamento")
               .filter(tipo_denuncia=tipo)
               .first())
        ctx["departamento_asignado"] = rel.departamento if rel else None

        # ✅ Conteo correcto usando la tabla real Denuncias.tipo_denuncia
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
    context_object_name = "tipo_denuncia"  # ✅ para que tu template lo reciba también

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        tipo = self.object
        ctx["total_denuncias"] = Denuncias.objects.filter(tipo_denuncia=tipo).count()  # ✅ modelo real
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

        # ✅ tomar denuncia (si está libre) o bloquear si ya la tomó otro
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

    notificar_respuesta(denuncia)
    return redirect("web:denuncia_detail", pk=denuncia_id)



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
#  Estos se quedan con CustomPermissionRequiredMixin porque usan auth.* (EXISTE)
class WebUserListView(LoginRequiredMixin, CustomPermissionRequiredMixin, ListView):
    model = User
    template_name = "webusers/webuser_list.html"
    context_object_name = "webusers"
    paginate_by = 10
    permission_required = "auth.view_user"
    login_url = "web:login"

    def get_queryset(self):
        return User.objects.all().order_by("username").prefetch_related("groups", "user_permissions")


class WebUserCreateView(CrudMessageMixin, LoginRequiredMixin, CustomPermissionRequiredMixin, CreateView):
    model = User
    form_class = WebUserForm
    template_name = "webusers/webuser_form.html"
    success_url = reverse_lazy("web:webuser_list")
    permission_required = "auth.add_user"
    login_url = "web:login"

    def form_valid(self, form):
        user = form.save(commit=False)
        password = form.cleaned_data.get("password")
        if password:
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


class WebUserDeleteView(CrudMessageMixin, LoginRequiredMixin, CustomPermissionRequiredMixin, DeleteView):
    model = User
    template_name = "webusers/webuser_confirm_delete.html"
    success_url = reverse_lazy("web:webuser_list")
    permission_required = "auth.delete_user"
    login_url = "web:login"




from django.template.loader import render_to_string
from django.http import HttpResponse, Http404
from django.template.loader import get_template
from xhtml2pdf import pisa
from django.shortcuts import get_object_or_404

def denuncia_pdf(request, pk):
    denuncia = get_object_or_404(Denuncias, pk=pk)

    if denuncia.estado != "resuelta":
        raise Http404("La denuncia no está resuelta")

    template = get_template("denuncias/denuncia_pdf.html")
    html = template.render({"denuncia": denuncia})

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="denuncia_{denuncia.id}.pdf"'
    )

    pisa_status = pisa.CreatePDF(
        html, dest=response, encoding="utf-8"
    )

    if pisa_status.err:
        return HttpResponse("Error al generar PDF", status=500)

    return response
