# This is an auto-generated Django model module.
# You'll have to do the following manually to clean this up:
#   * Rearrange models' order
#   * Make sure each model has one field with primary_key=True
#   * Make sure each ForeignKey and OneToOneField has `on_delete` set to the desired behavior
#   * Remove `managed = True` lines if you wish to allow Django to create, modify, and delete the table
# Feel free to rename the models, but don't rename db_table values or field names.
from django.db import models
#apuntaodes
import uuid
from django.utils import timezone


class Auditoria(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('Usuarios', models.DO_NOTHING, blank=True, null=True)
    accion = models.CharField(max_length=100)
    tabla_afectada = models.CharField(max_length=100, blank=True, null=True)
    registro_id = models.TextField(blank=True, null=True)
    detalle = models.TextField(blank=True, null=True)
    ip_origen = models.CharField(max_length=45, blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'auditoria'

    def __str__(self):
        return f"Auditoría: {self.accion} - {self.usuario.correo if self.usuario else 'Sistema'} - {self.created_at}"


class ChatConversaciones(models.Model):
    id = models.UUIDField(primary_key=True)
    #ciudadano = models.ForeignKey('Ciudadanos', models.DO_NOTHING)
    ciudadano = models.ForeignKey('Ciudadanos', models.DO_NOTHING, db_column='ciudadano_id', to_field='usuario')
    denuncia = models.ForeignKey('Denuncias', models.DO_NOTHING, db_column='denuncia_id', to_field='id', blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'chat_conversaciones'

    def __str__(self):
        return f"Conversación: {self.ciudadano.nombres} {self.ciudadano.apellidos} - {self.created_at.date()}"


class ChatMensajes(models.Model):
    id = models.UUIDField(primary_key=True)
    conversacion = models.ForeignKey(ChatConversaciones, models.DO_NOTHING)
    emisor = models.CharField(max_length=10)
    mensaje = models.TextField()
    created_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'chat_mensajes'

    def __str__(self):
        return f"Mensaje {self.emisor}: {self.mensaje[:50]}... - {self.created_at}"


class CiudadanoDocumentos(models.Model):
    id = models.UUIDField(primary_key=True)
    #ciudadano = models.ForeignKey('Ciudadanos', models.DO_NOTHING)
    ciudadano = models.ForeignKey('Ciudadanos', models.DO_NOTHING, db_column='ciudadano_id', to_field='usuario')
    tipo_documento = models.CharField(max_length=50)
    url_frontal = models.TextField(blank=True, null=True)
    url_trasera = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'ciudadano_documentos'

    def __str__(self):
        return f"Documento {self.tipo_documento}: {self.ciudadano.nombres} {self.ciudadano.apellidos}"


class Ciudadanos(models.Model):
    usuario = models.OneToOneField('Usuarios', models.DO_NOTHING, primary_key=True)
    cedula = models.CharField(unique=True, max_length=15)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    fecha_nacimiento = models.DateField(blank=True, null=True)
    foto_perfil_url = models.TextField(blank=True, null=True)
    firma_url = models.TextField(blank=True, null=True)
    firma_base64 = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'ciudadanos'

    def __str__(self):
        return f"{self.nombres} {self.apellidos} - {self.cedula}"


class DenunciaAsignaciones(models.Model):
    id = models.UUIDField(primary_key=True)
    denuncia = models.ForeignKey('Denuncias', models.DO_NOTHING, db_column='denuncia_id', to_field='id')
    #funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, db_column='funcionario_id', to_field='id')
    funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, db_column='funcionario_id', to_field='usuario')
    asignado_en = models.DateTimeField()
    activo = models.BooleanField()

    class Meta:
        managed=False
        db_table = 'denuncia_asignaciones'

    def __str__(self):
        return f"Asignación: {self.denuncia.descripcion[:30]}... -> {self.funcionario.nombres} {self.funcionario.apellidos}"


class DenunciaBorradores(models.Model):
    id = models.UUIDField(primary_key=True)
    #ciudadano = models.ForeignKey(Ciudadanos, models.DO_NOTHING)
    ciudadano = models.ForeignKey(Ciudadanos, models.DO_NOTHING, db_column='ciudadano_id', to_field='usuario')
    conversacion = models.OneToOneField(ChatConversaciones, models.DO_NOTHING, blank=True, null=True)
    datos_json = models.JSONField()
    listo_para_enviar = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'denuncia_borradores'

    def __str__(self):
        return f"Borrador: {self.ciudadano.nombres} {self.ciudadano.apellidos} - {'Listo' if self.listo_para_enviar else 'En proceso'}"


class DenunciaEvidencias(models.Model):
    id = models.UUIDField(primary_key=True)
    denuncia = models.ForeignKey('Denuncias', models.DO_NOTHING, db_column='denuncia_id', to_field='id')
    tipo = models.TextField()  # This field type is a guess.
    url_archivo = models.TextField()
    nombre_archivo = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'denuncia_evidencias'

    def __str__(self):
        return f"Evidencia {self.tipo}: {self.nombre_archivo or 'Sin nombre'} - Denuncia {self.denuncia.id}"


class DenunciaFirmas(models.Model):
    id = models.UUIDField(primary_key=True)
    denuncia = models.OneToOneField('Denuncias', models.DO_NOTHING, db_column='denuncia_id', to_field='id')
    firma_url = models.TextField(blank=True, null=True)
    firma_base64 = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'denuncia_firmas'

    def __str__(self):
        return f"Firma Denuncia {self.denuncia.id} - {self.denuncia.ciudadano.nombres} {self.denuncia.ciudadano.apellidos}"


class DenunciaHistorial(models.Model):
    id = models.UUIDField(primary_key=True)
    denuncia = models.ForeignKey('Denuncias', models.DO_NOTHING, db_column='denuncia_id', to_field='id')
    estado_anterior = models.TextField(blank=True, null=True)  # This field type is a guess.
    estado_nuevo = models.TextField()  # This field type is a guess.
    comentario = models.TextField(blank=True, null=True)
    #cambiado_por_funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, db_column='cambiado_por_funcionario', to_field='id', blank=True, null=True)
    cambiado_por_funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, db_column='cambiado_por_funcionario', to_field='usuario', blank=True, null=True)

    created_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'denuncia_historial'

    def __str__(self):
        return f"Historial: {self.estado_anterior} -> {self.estado_nuevo} - Denuncia {self.denuncia.id}"


class DenunciaRespuestas(models.Model):
    id = models.UUIDField(primary_key=True)
    denuncia = models.ForeignKey('Denuncias', models.DO_NOTHING, db_column='denuncia_id', to_field='id')
    #funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, blank=True, null=True, db_column='funcionario_id', to_field='id')
    funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, db_column='funcionario_id', to_field='usuario', blank=True, null=True)
    mensaje = models.TextField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'denuncia_respuestas'

    def __str__(self):
        return f"Respuesta: {self.mensaje[:50]}... - {self.funcionario.nombres if self.funcionario else 'Sistema'} {self.funcionario.apellidos if self.funcionario else ''}"


class Denuncias(models.Model):
    id = models.UUIDField(primary_key=True)
    #ciudadano = models.ForeignKey(Ciudadanos, models.DO_NOTHING)
    #tipo_denuncia = models.ForeignKey('TiposDenuncia', models.DO_NOTHING)
    ciudadano = models.ForeignKey(Ciudadanos, models.DO_NOTHING, db_column='ciudadano_id', to_field='usuario')
    tipo_denuncia = models.ForeignKey('TiposDenuncia', models.DO_NOTHING, db_column='tipo_denuncia_id')
    descripcion = models.TextField()
    referencia = models.TextField(blank=True, null=True)
    latitud = models.FloatField()
    longitud = models.FloatField()
    direccion_texto = models.TextField(blank=True, null=True)
    origen = models.TextField()  # This field type is a guess.
    estado = models.TextField()  # This field type is a guess.
    asignado_departamento = models.ForeignKey('Departamentos', models.DO_NOTHING, blank=True, null=True, db_column='asignado_departamento_id')
    #asignado_funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, blank=True, null=True, db_column='asignado_funcionario_id', to_field='id')
    asignado_funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, blank=True, null=True, db_column='asignado_funcionario_id', to_field='usuario')
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'denuncias'

    def __str__(self):
        return f"Denuncia {self.id}: {self.descripcion[:50]}... - {self.ciudadano.nombres} {self.ciudadano.apellidos}"

# los que estan aqui valian en app movil
class Departamentos(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=120)
    #activo = models.BooleanField()
    color_hex = models.CharField(max_length=7, blank=True, null=True)
    #created_at = models.DateTimeField()
    #updated_at = models.DateTimeField()
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)


    class Meta:
        managed=False
        db_table = 'departamentos'

    def __str__(self):
        return f"{self.nombre} {'(Activo)' if self.activo else '(Inactivo)'}"


class Faq(models.Model):
    id = models.BigAutoField(primary_key=True)
    pregunta = models.TextField()
    respuesta = models.TextField()
    visible = models.BooleanField()
    creado_por = models.ForeignKey('Usuarios', models.DO_NOTHING, db_column='creado_por', blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'faq'

    def __str__(self):
        return f"FAQ: {self.pregunta[:50]}... {'(Visible)' if self.visible else '(Oculto)'}"


class FuncionarioRoles(models.Model):
    #pk = models.CompositePrimaryKey('funcionario_id', 'rol_id')
    #funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, db_column='funcionario_id', to_field='id')
    funcionario = models.ForeignKey('Funcionarios', models.DO_NOTHING, db_column='funcionario_id', to_field='usuario')
    rol = models.ForeignKey('Roles', models.DO_NOTHING, db_column='rol_id')
    created_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'funcionario_roles'
        unique_together = (('funcionario', 'rol'),)

    def __str__(self):
        return f"Rol: {self.rol.nombre} - {self.funcionario.nombres} {self.funcionario.apellidos}"

# funcionario que valia em movil pilas # es la que valia y ### es lo que estab comnetado
#class Funcionarios(models.Model):
#    ###id = models.AutoField(primary_key=True, db_column='id')
#    usuario = models.OneToOneField('Usuarios', models.DO_NOTHING, primary_key=True, db_column='usuario_id')
#    cedula = models.CharField(unique=True, max_length=15, db_column='cedula')
#    nombres = models.CharField(max_length=100, db_column='nombres')
#    apellidos = models.CharField(max_length=100, db_column='apellidos')
#    telefono = models.CharField(max_length=20, blank=True, null=True, db_column='telefono')
#    departamento = models.ForeignKey(Departamentos, models.DO_NOTHING, blank=True, null=True, db_column='departamento_id')
#    cargo = models.CharField(max_length=100, blank=True, null=True, db_column='cargo')
#    activo = models.BooleanField(default=True, db_column='activo')
#    created_at = models.DateTimeField(db_column='created_at')
#    updated_at = models.DateTimeField(db_column='updated_at')
#    ###web_user = models.ForeignKey('auth.User', models.DO_NOTHING, blank=True, null=True, db_column='web_user_id')
#
#    class Meta:
#        managed=False
#        db_table = 'funcionarios'
#
#    ###def __str__(self):
#    ###    if self.web_user:
#    ###        return f"{self.nombres} {self.apellidos} - {self.cargo or 'Sin cargo'} - {self.web_user.username}"
#    ###    return f"{self.nombres} {self.apellidos} - {self.cargo or 'Sin cargo'}"

class Funcionarios(models.Model):
    usuario = models.OneToOneField(
        'Usuarios',
        on_delete=models.CASCADE,
        primary_key=True,
        db_column="usuario_id"
    )

    cedula = models.CharField(max_length=15, unique=True)
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    telefono = models.CharField(max_length=20, null=True, blank=True)

    departamento = models.ForeignKey(
        "Departamentos",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        db_column="departamento_id"
    )

    cargo = models.CharField(max_length=100, null=True, blank=True)
    activo = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)  # ✅
    updated_at = models.DateTimeField(default=timezone.now)  # ✅

    class Meta:
        managed = False
        db_table = "funcionarios"


class Notificaciones(models.Model):
    id = models.BigAutoField(primary_key=True)
    usuario = models.ForeignKey('Usuarios', models.DO_NOTHING)
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    tipo = models.CharField(max_length=30)
    leido = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'notificaciones'

    def __str__(self):
        return f"Notificación: {self.titulo} - {self.usuario.correo} - {'Leído' if self.leido else 'No leído'}"


class PasswordResetTokens(models.Model):
    id = models.UUIDField(primary_key=True)
    usuario = models.ForeignKey('Usuarios', models.DO_NOTHING)
    codigo_6 = models.CharField(max_length=6)
    expira_en = models.DateTimeField()
    usado = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'password_reset_tokens'

    def __str__(self):
        return f"Token: {self.usuario.correo} - {'Usado' if self.usado else 'Válido'} - Expira: {self.expira_en}"


class Roles(models.Model):
    id = models.UUIDField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=40)
    descripcion = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'roles'

    def __str__(self):
        return f"Rol: {self.nombre}"


class TipoDenunciaDepartamento(models.Model):
    tipo_denuncia = models.OneToOneField('TiposDenuncia', models.DO_NOTHING, primary_key=True)
    departamento = models.ForeignKey(Departamentos, models.DO_NOTHING)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'tipo_denuncia_departamento'

    def __str__(self):
        return f"{self.tipo_denuncia.nombre} - {self.departamento.nombre}"


class TiposDenuncia(models.Model):
    id = models.BigAutoField(primary_key=True)
    nombre = models.CharField(unique=True, max_length=120)
    descripcion = models.TextField(blank=True, null=True)
    activo = models.BooleanField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()

    class Meta:
        managed=False
        db_table = 'tipos_denuncia'

    def __str__(self):
        return f"{self.nombre} {'(Activo)' if self.activo else '(Inactivo)'}"

#esta es usuarios donde vale la app movil
#class Usuarios(models.Model):
#    id = models.UUIDField(primary_key=True)
#    tipo = models.TextField()  # This field type is a guess.
#    correo = models.CharField(unique=True, max_length=150)
#    password_hash = models.TextField()
#    activo = models.BooleanField()
#    correo_verificado = models.BooleanField()
#    created_at = models.DateTimeField()
#    updated_at = models.DateTimeField()
#
#    class Meta:
#        managed=False
#        db_table = 'usuarios'
#
#    def __str__(self):
#        return f"{self.correo} ({self.tipo}) - {'Activo' if self.activo else 'Inactivo'}"

class Usuarios(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tipo = models.TextField()
    correo = models.CharField(unique=True, max_length=150)
    password_hash = models.TextField()
    activo = models.BooleanField(default=True)
    correo_verificado = models.BooleanField(default=False)

    created_at = models.DateTimeField(default=timezone.now)  # ✅
    updated_at = models.DateTimeField(default=timezone.now)  # ✅

    class Meta:
        managed = False
        db_table = 'usuarios'

#-------------------------------------------------------------------------
# mapero unin de mi bdd condjango para permiso
class Denuncia(models.Model):
    id = models.UUIDField(primary_key=True)
    asignado_departamento = models.ForeignKey(
        "Departamentos",
        on_delete=models.SET_NULL,
        null=True,
        db_column="asignado_departamento_id"
    )
    asignado_funcionario = models.ForeignKey(
        "Funcionarios",
        on_delete=models.SET_NULL,
        null=True,
        db_column="asignado_funcionario_id"
    )
    estado = models.CharField(max_length=50)

    class Meta:
        managed = False
        db_table = "denuncias"

class DenunciaRespuesta(models.Model):
    id = models.UUIDField(primary_key=True)
    denuncia = models.ForeignKey(Denuncia, on_delete=models.CASCADE)
    funcionario = models.ForeignKey("Funcionarios", on_delete=models.SET_NULL, null=True)
    mensaje = models.TextField()

    class Meta:
        managed = False
        db_table = "denuncia_respuestas"


# --- Archivos binarios (NUEVO) ---
import uuid
from django.db import models

class BorradorArchivo(models.Model):
    TIPOS = (
        ("cedula", "cedula"),
        ("firma", "firma"),
        ("foto", "foto"),
        ("audio", "audio"),
        ("video", "video"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    borrador = models.ForeignKey(
        "DenunciaBorradores",
        on_delete=models.CASCADE,
        related_name="archivos",
        db_column="borrador_id",
    )

    tipo = models.CharField(max_length=20, choices=TIPOS)
    filename = models.CharField(max_length=255, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    data = models.BinaryField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "borrador_archivos"   # ✅ tabla nueva (no existe aún)
        managed = True                  # ✅ Django la crea


class DenunciaArchivo(models.Model):
    TIPOS = BorradorArchivo.TIPOS

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    denuncia = models.ForeignKey(
        "Denuncias",
        on_delete=models.CASCADE,
        related_name="archivos",
        db_column="denuncia_id",
    )

    tipo = models.CharField(max_length=20, choices=TIPOS)
    filename = models.CharField(max_length=255, null=True, blank=True)
    content_type = models.CharField(max_length=100, null=True, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    data = models.BinaryField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "denuncia_archivos"   # ✅ tabla nueva
        managed = True
