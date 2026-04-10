from django.contrib import admin
from django.urls import path
from seguridad.views import (
    login_usuario,
    registro_usuario,
    perfil_usuario,
    logout_usuario,
    validar_token,
)
from seguridad.control_acceso import health_check

urlpatterns = [
    path("admin/",                  admin.site.urls),
    # Autenticación
    path("auth/login/",             login_usuario,    name="login"),
    path("auth/registro/",          registro_usuario, name="registro"),
    path("auth/perfil/",            perfil_usuario,   name="perfil"),
    path("auth/logout/",            logout_usuario,   name="logout"),
    path("auth/validar-token/",     validar_token,    name="validar_token"),  # usado por Kong
    # Monitoreo
    path("health/",                 health_check,     name="health_check"),
]
