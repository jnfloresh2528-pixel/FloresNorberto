# ventas/views_tareas.py
"""Direcciones protegidas por token para ejecutar tareas desde fuera.

Las llama GitHub Actions (u otro programador externo):
    POST /tareas/reporte/   → reporte de ventas del día anterior
    POST /tareas/stock/     → revisión de stock bajo

La respuesta es mínima a propósito: los registros de GitHub pueden ser
públicos y no deben mostrar ventas ni nombres de productos.
"""
import hmac
import logging

from django.conf import settings
from django.http import HttpResponseForbidden, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from ventas.tasks import reporte_ventas_diario, verificar_stock_bajo
from datetime import time

from django.utils import timezone

from ventas.models import EjecucionTarea

logger = logging.getLogger(__name__)


def _tarea_reporte() -> dict:
    r = reporte_ventas_diario.apply(
        kwargs={'dias_atras': settings.REPORTE_DIAS_ATRAS}
    ).get()
    return {'correo_enviado': r['correo_enviado']}


def _tarea_stock() -> dict:
    r = verificar_stock_bajo.apply(kwargs={'umbral': 5}).get()
    return {'total': r['total'], 'alerta_enviada': r['alerta_enviada']}
    
def _tarea_reporte_programado() -> dict:
    """Envía el reporte si ya pasó REPORTE_HORA y hoy no se ha enviado."""
    ahora = timezone.localtime()
    try:
        hh, mm = settings.REPORTE_HORA.split(':')
        hora_objetivo = time(int(hh), int(mm))
    except ValueError:
        return {'ejecutado': False, 'motivo': 'REPORTE_HORA inválida'}

    if ahora.time() < hora_objetivo:
        return {'ejecutado': False, 'motivo': 'aún no es la hora'}

    registro, creado = EjecucionTarea.objects.get_or_create(
        nombre='reporte', fecha=ahora.date()
    )
    if not creado:
        return {'ejecutado': False, 'motivo': 'ya se envió hoy'}

    try:
        resumen = _tarea_reporte()
    except Exception:
        registro.delete()          # permite reintentar en la siguiente llamada
        raise
    if not resumen['correo_enviado']:
        registro.delete()
    return {'ejecutado': True, **resumen}

TAREAS = {
    'reporte': _tarea_reporte,
    'stock':   _tarea_stock,
    'reporte-programado': _tarea_reporte_programado,
}


def _token_valido(request) -> bool:
    esperado = settings.TAREAS_TOKEN
    recibido = request.headers.get('X-Tareas-Token', '')
    if not esperado:                      # sin token configurado = apagado
        return False
    return hmac.compare_digest(recibido.encode(), esperado.encode())


@csrf_exempt
@require_POST
def ejecutar_tarea(request, nombre):
    """Ejecuta una tarea si el token es correcto."""
    if not _token_valido(request):
        return HttpResponseForbidden('Token inválido')

    funcion = TAREAS.get(nombre)
    if funcion is None:
        return JsonResponse({'ok': False, 'error': 'Tarea desconocida'}, status=404)

    try:
        resumen = funcion()
    except Exception as exc:
        logger.error(f'[tareas] Error en {nombre}: {exc}')
        return JsonResponse({'ok': False, 'tarea': nombre}, status=500)

    return JsonResponse({'ok': True, 'tarea': nombre, **resumen})
