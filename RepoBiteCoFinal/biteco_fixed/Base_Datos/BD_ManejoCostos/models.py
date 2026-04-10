from django.db import models

class ReporteGasto(models.Model):
    project_id = models.CharField(max_length=100, db_index=True)
    mes = models.CharField(max_length=7) # Formato YYYY-MM
    datos_json = models.JSONField() # Almacena la estructura del reporte consolidado
    fecha_generacion = models.DateTimeField(auto_now_add=True)
