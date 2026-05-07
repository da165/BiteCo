from django.shortcuts import render
import requests
from django.http import JsonResponse
from django.core.cache import cache
from .models import ReporteGasto

AWS_MICROSERVICE_URL = "http://aws-service:8000/api/fetch-costs/"

def consultar_reporte(request, project_id, mes):
    # 1. Obtener la información del JWT que procesó tu middleware
    # (Ajusta 'jwt_payload' al nombre de variable exacto que use tu middleware de JWT)
    jwt_payload = getattr(request, 'jwt_payload', {})
    permissions = jwt_payload.get('permissions', [])

    # ==========================================
    # FLUJO DE ESCRITURA / MODIFICACIÓN (POST)
    # ==========================================
    if request.method == 'POST':
        # Validar rigurosamente que el token posea permisos de escritura
        if 'write:reportes' not in permissions:
            return JsonResponse({'error': 'Forbidden: Requiere permisos de escritura (write:reportes)'}, status=403)
        
        # Aquí iría tu lógica segura para modificar el reporte...
        return JsonResponse({'mensaje': 'Reporte modificado exitosamente (Simulado)'})

    # ==========================================
    # FLUJO DE LECTURA (GET)
    # ==========================================
    elif request.method == 'GET':
        # Validar que al menos tenga permisos de lectura
        if 'read:reportes' not in permissions and 'write:reportes' not in permissions:
            return JsonResponse({'error': 'Forbidden: Requiere permisos de lectura (read:reportes)'}, status=403)

        cache_key = f"reporte_{project_id}_{mes}"
        
        # 1. Intentar obtener de Caché 
        reporte_data = cache.get(cache_key)
        if reporte_data:
            return JsonResponse({'origen': 'cache', 'data': reporte_data})

        # 2. Buscar en la Base de Datos
        try:
            reporte_db = ReporteGasto.objects.get(project_id=project_id, mes=mes)
            cache.set(cache_key, reporte_db.datos_json, timeout=3600)
            return JsonResponse({'origen': 'base_de_datos', 'data': reporte_db.datos_json})

        except ReporteGasto.DoesNotExist:
            # 3. Solicitar a AWS si no está localmente
            try:
                respuesta_aws = requests.get(f"{AWS_MICROSERVICE_URL}{project_id}")
                if respuesta_aws.status_code == 200:
                    nueva_data = respuesta_aws.json()
                    
                    # Guardar en BD local y Caché
                    ReporteGasto.objects.create(
                        project_id=project_id,
                        mes=mes,
                        datos_json=nueva_data
                    )
                    cache.set(cache_key, nueva_data, timeout=3600)
                    return JsonResponse({'origen': 'microservicio_aws', 'data': nueva_data})
                else:
                    return JsonResponse({'error': 'No se pudo generar el reporte o el recurso no existe'}, status=404)
                    
            except requests.exceptions.RequestException:
                return JsonResponse({'error': 'Falla de comunicación con el servicio de extracción'}, status=503)

    else:
        return JsonResponse({'error': 'Método HTTP no soportado'}, status=405)
