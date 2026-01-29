from django.contrib import admin
from .models import *
# Register your models here.

admin.site.register(Auditoria)
admin.site.register(ChatConversaciones)
admin.site.register(ChatMensajes)
admin.site.register(CiudadanoDocumentos)
admin.site.register(Ciudadanos)
admin.site.register(DenunciaBorradores)
admin.site.register(DenunciaEvidencias)
admin.site.register(DenunciaFirmas)
admin.site.register(DenunciaHistorial)
admin.site.register(DenunciaRespuestas)
admin.site.register(Denuncias)
admin.site.register(Departamentos)
admin.site.register(Faq)
admin.site.register(Notificaciones)
admin.site.register(PasswordResetTokens)
admin.site.register(Roles)
admin.site.register(TipoDenunciaDepartamento)
admin.site.register(TiposDenuncia)
admin.site.register(Usuarios)


admin.site.register(Funcionarios)

