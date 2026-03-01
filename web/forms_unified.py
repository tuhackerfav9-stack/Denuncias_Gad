from django import forms
from django.contrib.auth.models import User, Group

from db.models import Departamentos, Funcionarios  # 👈 agrega Funcionarios


class UnifiedWebUserForm(forms.Form):
    # auth_user
    username = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    first_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    last_name = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"class": "form-control"}),
        help_text="En edición: dejar en blanco para no cambiar."
    )

    is_superuser = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    group = forms.ModelChoiceField(
        queryset=Group.objects.all().order_by("name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Grupo"
    )

    departamento = forms.ModelChoiceField(
        queryset=Departamentos.objects.filter(activo=True).order_by("nombre"),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"})
    )

    cedula = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    telefono = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    cargo = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    activo = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def __init__(self, *args, web_user: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.web_user = web_user

        creating = web_user is None
        self.fields["password"].required = creating

        # 👇 opcional: que al haber error se ponga rojo automáticamente
        self._apply_bootstrap_error_classes()

    # =========================
    # VALIDACIONES POR CAMPO
    # =========================
    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        qs = User.objects.filter(username=username)
        if self.web_user and self.web_user.pk:
            qs = qs.exclude(pk=self.web_user.pk)
        if qs.exists():
            raise forms.ValidationError("Este usuario (username) ya existe. Prueba con otro.")
        return username

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip().lower()
        qs = User.objects.filter(email=email)
        if self.web_user and self.web_user.pk:
            qs = qs.exclude(pk=self.web_user.pk)
        if qs.exists():
            raise forms.ValidationError("Este correo ya está usado en otro usuario web. Usa otro correo.")
        return email

    def clean_cedula(self):
        cedula = (self.cleaned_data.get("cedula") or "").strip()

        qs = Funcionarios.objects.filter(cedula=cedula)

        # si es update, excluir el funcionario ligado al web_user actual (si existe)
        if self.web_user and self.web_user.pk:
            try:
                from web.models import FuncionarioWebUser
                link = FuncionarioWebUser.objects.select_related("funcionario").filter(web_user=self.web_user).first()
                if link and link.funcionario_id:
                    qs = qs.exclude(pk=link.funcionario_id)
            except Exception:
                # si por algo falla el lookup, igual no rompemos el form
                pass

        if qs.exists():
            raise forms.ValidationError(f"Ya existe un funcionario con la cédula {cedula}.")
        return cedula

    # =========================
    # HELPER: CLASE ROJA BOOTSTRAP
    # =========================
    def _apply_bootstrap_error_classes(self):
        """
        Si un campo tiene errores, agrega 'is-invalid' al widget.
        (Bootstrap 4/5 lo pinta rojo automáticamente)
        """
        for name, field in self.fields.items():
            css = field.widget.attrs.get("class", "")
            # cuando ya re-renderiza con errores, Django ya tiene self.errors cargado
            if self.errors.get(name):
                if "is-invalid" not in css:
                    field.widget.attrs["class"] = (css + " is-invalid").strip()