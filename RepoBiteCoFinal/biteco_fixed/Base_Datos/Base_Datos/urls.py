from django.contrib import admin
from django.urls import path
from BD_ManejoCostos.views import consultar_reporte
from Base_Datos.control_acceso import health_check  # FIX: registrar health check

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/reportes/<str:project_id>/<str:mes>/', consultar_reporte, name='consultar_reporte'),
    path('health/', health_check, name='health_check'),  # FIX: endpoint ASR
]
