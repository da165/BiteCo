# aws_collector/views.py
import boto3
from django.http import JsonResponse
from botocore.exceptions import ClientError
import datetime

def obtener_costos_aws(request, project_id):
    """
    Se conecta a AWS Cost Explorer para extraer los costos de un proyecto.
    """
    try:
        # Inicializar el cliente de AWS Cost Explorer
        # Nota: Las credenciales deben estar configuradas en el entorno o pasarse de forma segura.
        client = boto3.client('ce', region_name='us-east-1')
        
        # Definir el rango de fechas 
        hoy = datetime.date.today()
        inicio_mes = hoy.replace(day=1).strftime('%Y-%m-%d')
        fin_mes = hoy.strftime('%Y-%m-%d')

        # Consulta a AWS
        response = client.get_cost_and_usage(
            TimePeriod={
                'Start': inicio_mes,
                'End': fin_mes
            },
            Granularity='MONTHLY',
            Metrics=['UnblendedCost'],
            
        )

        # Procesar y retornar la data
        costos = response['ResultsByTime'][0]['Total']['UnblendedCost']['Amount']
        
        return JsonResponse({
            'status': 'success',
            'project_id': project_id,
            'costo_total': costos,
            'moneda': 'USD'
        }, status=200)

    except ClientError as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
