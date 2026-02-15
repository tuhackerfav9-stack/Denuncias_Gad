from django import forms
from django.contrib.auth.models import User, Group

from db.models import Departamentos


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

    # tu regla: 1 grupo
    group = forms.ModelChoiceField(
        queryset=Group.objects.all().order_by("name"),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Grupo"
    )

    # dominio funcionario
    departamento = forms.ModelChoiceField(
        queryset=Departamentos.objects.filter(activo=True).order_by("nombre"),
        required=True,
        widget=forms.Select(attrs={"class": "form-select"})
    )
    cedula = forms.CharField(widget=forms.TextInput(attrs={"class": "form-control"}))
    telefono = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    cargo = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control"}))

    # estado unificado
    activo = forms.BooleanField(required=False, initial=True, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    def __init__(self, *args, web_user: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.web_user = web_user

        creating = web_user is None
        if creating:
            self.fields["password"].required = True
        else:
            self.fields["password"].required = False
