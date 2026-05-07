# DB_ManejoCostos/auth0_utils.py

import json
from urllib.request import urlopen
from jose import jwt
from django.http import JsonResponse
from django.conf import settings

def get_token_auth_header(request):
    """Extrae el token del header 'Authorization: Bearer <token>'"""
    auth = request.headers.get("Authorization", None)
    if not auth:
        return None
    parts = auth.split()
    if parts[0].lower() != "bearer" or len(parts) != 2:
        return None
    return parts[1]

def requires_permission(required_permission):
    """Decorador que bloquea a los hackers si no tienen el permiso exacto"""
    def decorator(f):
        def wrapper(request, *args, **kwargs):
            token = get_token_auth_header(request)
            if not token:
                return JsonResponse({'error': 'Falta el token de autorización'}, status=401)
            
            # Descargar las llaves públicas de Auth0 para verificar la firma
            jsonurl = urlopen(f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json")
            jwks = json.loads(jsonurl.read())
            unverified_header = jwt.get_unverified_header(token)
            
            rsa_key = {}
            for key in jwks["keys"]:
                if key["kid"] == unverified_header["kid"]:
                    rsa_key = {
                        "kty": key["kty"], "kid": key["kid"],
                        "use": key["use"], "n": key["n"], "e": key["e"]
                    }
            if rsa_key:
                try:
                    # Desencriptar y verificar el token (Garantiza que no fue alterado)
                    payload = jwt.decode(
                        token,
                        rsa_key,
                        algorithms=["RS256"],
                        audience=settings.API_AUDIENCE,
                        issuer=f"https://{settings.AUTH0_DOMAIN}/"
                    )
                except Exception:
                    return JsonResponse({'error': 'Token inválido o expirado'}, status=401)
                
                # ¡AQUÍ ESTÁ LA MAGIA DEL ASR16!
                # Extraemos los permisos del token y verificamos
                token_permissions = payload.get("permissions", [])
                
                if required_permission not in token_permissions:
                    # Si el Hacker/Developer intenta escribir sin permiso, le cerramos la puerta
                    return JsonResponse({
                        'error': '403 Forbidden: No tienes permisos para realizar esta acción de tampering.'
                    }, status=403)
                
                return f(request, *args, **kwargs)
            return JsonResponse({'error': 'No se pudo verificar el token'}, status=401)
        return wrapper
    return decorator
