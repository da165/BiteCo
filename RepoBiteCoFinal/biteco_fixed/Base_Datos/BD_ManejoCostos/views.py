from django.shortcuts import render
import requests
from django.http import JsonResponse
from django.core.cache import cache
from .models import ReporteGasto

# URL interna del microservicio de AWS
AWS_MICROSERVICE_URL = "http://aws-service:8000/api/fetch-costs/"

def consultar_reporte(request, project_id, mes):
    """
    Revisa si el reporte existe en Caché o BD. Si no, lo solicita a AWS.
    """
    cache_key = f"reporte_{project_id}_{mes}"
    
    # 1. Intentar obtener de Caché 
    reporte_data = cache.get(cache_key)
    if reporte_data:
        return JsonResponse({'origen': 'cache', 'data': reporte_data})

    # 2. Si no está en caché, buscar en la Base de Datos (PostgreSQL, por ejemplo)
    try:
        reporte_db = ReporteGasto.objects.get(project_id=project_id, mes=mes)
        
        # Guardar en caché para la próxima vez 
        cache.set(cache_key, reporte_db.datos_json, timeout=3600)
        
        return JsonResponse({'origen': 'base_de_datos', 'data': reporte_db.datos_json})

    except ReporteGasto.DoesNotExist:
        # 3. Si no existe en la BD, se debe solicitar al microservicio de recolección (AWS)
        
        try:
            # Llamada síncrona al microservicio de AWS 
            respuesta_aws = requests.get(f"{AWS_MICROSERVICE_URL}{project_id}")
            
            if respuesta_aws.status_code == 200:
                nueva_data = respuesta_aws.json()
                
                # Guardar el nuevo reporte en la BD local
                nuevo_reporte = ReporteGasto.objects.create(
                    project_id=project_id,
                    mes=mes,
                    datos_json=nueva_data
                )
                
                # Guardar en caché
                cache.set(cache_key, nueva_data, timeout=3600)
                
                return JsonResponse({'origen': 'microservicio_aws', 'data': nueva_data})
            else:
                return JsonResponse({'error': 'No se pudo generar el reporte o el recurso no existe'}, status=404)
                
        except requests.exceptions.RequestException as e:
            return JsonResponse({'error': 'Falla de comunicación con el servicio de extracción'}, status=503)
# Create your views here.
