from django.contrib import admin
from django.urls import path
from AWS_Consulta.views import obtener_costos_aws
from AWS.control_acceso import health_check  # FIX: registrar health check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/aws/costos/<str:project_id>/', obtener_costos_aws, name='obtener_costos_aws'),
    path('health/', health_check, name='health_check'),  # FIX: endpoint ASR
]
