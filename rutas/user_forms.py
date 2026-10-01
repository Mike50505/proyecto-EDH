from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.models import Group


ROLE_NAMES = ("Consulta e impresión", "Edición de rutas", "Administración de rutas")


def available_roles():
    return Group.objects.filter(name__in=ROLE_NAMES).order_by("name")


class UserCreateForm(forms.ModelForm):
    role = forms.ModelChoiceField(label="Rol", queryset=Group.objects.none(), empty_label="Seleccionar rol")
    password1 = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput)

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email", "is_active")
        labels = {"username": "Usuario", "first_name": "Nombre", "last_name": "Apellidos",
                  "email": "Correo electrónico", "is_active": "Acceso activo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = available_roles()
        self.fields["is_active"].initial = True
        self.fields["username"].widget.attrs["autocomplete"] = "off"
        self.fields["password1"].widget.attrs["autocomplete"] = "new-password"
        self.fields["password2"].widget.attrs["autocomplete"] = "new-password"

    def clean(self):
        data = super().clean()
        password1, password2 = data.get("password1"), data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", "Las contraseñas no coinciden.")
        if password1:
            candidate = self._meta.model(**{field: data.get(field, "") for field in
                                            ("username", "first_name", "last_name", "email")})
            try:
                password_validation.validate_password(password1, candidate)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = False
        user.is_superuser = False
        user.set_password(self.cleaned_data["password1"])
        if commit:
            user.save()
            user.groups.set([self.cleaned_data["role"]])
        return user


class UserEditForm(forms.ModelForm):
    role = forms.ModelChoiceField(label="Rol", queryset=Group.objects.none(), empty_label="Seleccionar rol")

    class Meta:
        model = get_user_model()
        fields = ("username", "first_name", "last_name", "email", "is_active")
        labels = {"username": "Usuario", "first_name": "Nombre", "last_name": "Apellidos",
                  "email": "Correo electrónico", "is_active": "Acceso activo"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].queryset = available_roles()
        if self.instance.pk:
            self.fields["role"].initial = self.instance.groups.filter(name__in=ROLE_NAMES).first()

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
            user.groups.set([self.cleaned_data["role"]])
        return user
