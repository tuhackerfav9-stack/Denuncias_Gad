from notificaciones.models import DeviceToken
from notificaciones.fcm import send_push

def notificar_respuesta(denuncia):
    ciudadano = denuncia.ciudadano
    uid = str(denuncia.ciudadano_id)

    tokens = list(
        DeviceToken.objects.filter(usuario_id=uid)
        .values_list("fcm_token", flat=True)
    )

    
    if not tokens:
        return 0

    #  MENSAJE de psuh notication
    titulo = "📩 Respuesta a tu denuncia"
    cuerpo = (
        f"Tipo: {denuncia.tipo_denuncia.nombre}\n"
        f"Estado: {denuncia.estado.replace('_', ' ').title()}"
    )

    data = {
        "denuncia_id": str(denuncia.id),
        "tipo": denuncia.tipo_denuncia.nombre,
        "estado": denuncia.estado,
        "accion": "ver_denuncia",
    }

    return send_push(
        tokens=tokens,
        title=titulo,
        body=cuerpo,
        data=data,
    )
