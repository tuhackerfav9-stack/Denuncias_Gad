from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import ListView, TemplateView
from django.shortcuts import redirect, get_object_or_404, render

from web.forms_unified import UnifiedWebUserForm
from web.services.unified_user_service import (
    upsert_unified_user,
    can_hard_delete_user,
    soft_disable_unified_user,
    hard_delete_unified_user,
)
from web.models import FuncionarioWebUser


class UnifiedUserListView(LoginRequiredMixin, ListView):
    template_name = "unified_users/unified_user_list.html"
    context_object_name = "rows"
    paginate_by = 10
    login_url = "web:login"

    def get_queryset(self):
        """
        Listado real con JOIN por la tabla puente:
        devuelve filas que ya están encadenadas (las 4 tablas).
        """
        qs = (
            FuncionarioWebUser.objects
            .select_related("web_user", "funcionario", "funcionario__usuario", "funcionario__departamento")
            .order_by("web_user__username")
        )

        q = (self.request.GET.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(web_user__username__icontains=q) |
                Q(web_user__email__icontains=q) |
                Q(funcionario__cedula__icontains=q) |
                Q(funcionario__nombres__icontains=q) |
                Q(funcionario__apellidos__icontains=q)
            )
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # flag de hard delete por cada fila (solo los de la página)
        for link in ctx["page_obj"]:
            link.can_hard_delete = can_hard_delete_user(link.web_user)

        ctx["q"] = (self.request.GET.get("q") or "").strip()
        return ctx


class UnifiedUserCreateView(LoginRequiredMixin, TemplateView):
    template_name = "unified_users/unified_user_form.html"
    login_url = "web:login"

    def get(self, request, *args, **kwargs):
        form = UnifiedWebUserForm()
        return render(request, self.template_name, {"form": form, "object": None})

    def post(self, request, *args, **kwargs):
        form = UnifiedWebUserForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "object": None})

        r = upsert_unified_user(
            web_user=None,
            username=form.cleaned_data["username"],
            email=form.cleaned_data["email"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            password=form.cleaned_data["password"],
            is_superuser=form.cleaned_data["is_superuser"],
            group=form.cleaned_data["group"],
            departamento_id=form.cleaned_data["departamento"].id,
            cedula=form.cleaned_data["cedula"],
            telefono=form.cleaned_data["telefono"],
            cargo=form.cleaned_data["cargo"],
            activo=form.cleaned_data["activo"],
        )

        messages.success(request, "✅ Usuario creado (auth_user + usuarios + funcionarios + puente).")
        return redirect("web:unified_user_list")


class UnifiedUserDetailView(LoginRequiredMixin, TemplateView):
    template_name = "unified_users/unified_user_detail.html"
    login_url = "web:login"

    def get(self, request, pk, *args, **kwargs):
        link = get_object_or_404(
            FuncionarioWebUser.objects.select_related(
                "web_user", "funcionario", "funcionario__usuario", "funcionario__departamento"
            ),
            web_user_id=pk
        )

        return render(request, self.template_name, {
            "link": link,
            "can_hard_delete": can_hard_delete_user(link.web_user)
        })


class UnifiedUserUpdateView(LoginRequiredMixin, TemplateView):
    template_name = "unified_users/unified_user_form.html"
    login_url = "web:login"

    def get(self, request, pk, *args, **kwargs):
        link = get_object_or_404(
            FuncionarioWebUser.objects.select_related(
                "web_user", "funcionario", "funcionario__usuario", "funcionario__departamento"
            ),
            web_user_id=pk
        )
        u = link.web_user
        f = link.funcionario

        initial = {
            "username": u.username,
            "email": u.email,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "is_superuser": u.is_superuser,
            "group": u.groups.first(),
            "departamento": f.departamento,
            "cedula": f.cedula,
            "telefono": f.telefono,
            "cargo": f.cargo,
            "activo": u.is_active,
        }
        form = UnifiedWebUserForm(initial=initial, web_user=u)
        return render(request, self.template_name, {"form": form, "object": u, "link": link})

    def post(self, request, pk, *args, **kwargs):
        link = get_object_or_404(FuncionarioWebUser.objects.select_related("web_user", "funcionario"), web_user_id=pk)
        u = link.web_user

        form = UnifiedWebUserForm(request.POST, web_user=u)
        if not form.is_valid():
            return render(request, self.template_name, {"form": form, "object": u, "link": link})

        upsert_unified_user(
            web_user=u,
            username=form.cleaned_data["username"],
            email=form.cleaned_data["email"],
            first_name=form.cleaned_data["first_name"],
            last_name=form.cleaned_data["last_name"],
            password=form.cleaned_data["password"] or None,
            is_superuser=form.cleaned_data["is_superuser"],
            group=form.cleaned_data["group"],
            departamento_id=form.cleaned_data["departamento"].id,
            cedula=form.cleaned_data["cedula"],
            telefono=form.cleaned_data["telefono"],
            cargo=form.cleaned_data["cargo"],
            activo=form.cleaned_data["activo"],
        )

        messages.success(request, "✅ Usuario actualizado y sincronizado en las 4 tablas.")
        return redirect("web:unified_user_list")


class UnifiedUserDeleteView(LoginRequiredMixin, TemplateView):
    template_name = "unified_users/unified_user_confirm_delete.html"
    login_url = "web:login"

    def get(self, request, pk, *args, **kwargs):
        u = get_object_or_404(User, pk=pk)
        return render(request, self.template_name, {"object": u, "can_hard_delete": can_hard_delete_user(u)})

    def post(self, request, pk, *args, **kwargs):
        u = get_object_or_404(User, pk=pk)
        hard_requested = (request.POST.get("hard_delete") == "1")
        allowed = can_hard_delete_user(u)

        if hard_requested and allowed:
            hard_delete_unified_user(u)
            messages.success(request, "✅ Usuario eliminado definitivamente.")
            return redirect("web:unified_user_list")

        soft_disable_unified_user(u)
        if not allowed:
            messages.warning(request, "⚠️ Tiene denuncias tratadas: NO se puede eliminar. Se desactivó.")
        else:
            messages.info(request, "✅ Se desactivó (soft delete).")

        return redirect("web:unified_user_list")
