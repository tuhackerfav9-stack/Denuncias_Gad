from django.db import migrations
import uuid
from django.utils import timezone


def seed_demo_denuncias(apps, schema_editor):
    now = timezone.now()
    connection = schema_editor.connection

    with connection.cursor() as cursor:

        # 1) Crear usuario demo si no existe
        cursor.execute("""
            INSERT INTO usuarios (id, tipo, correo, password_hash, activo, correo_verificado, created_at, updated_at)
            SELECT gen_random_uuid(), 'ciudadano', 'demo.ciudadano@utc.local', 'demo', true, true, now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM usuarios WHERE correo = 'demo.ciudadano@utc.local'
            )
        """)

        # 2) Obtener ID del usuario demo
        cursor.execute("""
            SELECT id FROM usuarios 
            WHERE correo = 'demo.ciudadano@utc.local'
            LIMIT 1
        """)
        user_id = cursor.fetchone()[0]

        # 3) Crear ciudadano si no existe
        cursor.execute("""
            INSERT INTO ciudadanos (usuario_id, cedula, nombres, apellidos, telefono, created_at, updated_at)
            SELECT %s, '1100000000', 'Ciudadano', 'Demo', '0999999999', now(), now()
            WHERE NOT EXISTS (
                SELECT 1 FROM ciudadanos WHERE usuario_id = %s
            )
        """, [user_id, user_id])

        # 4) Obtener 6 tipos
        cursor.execute("""
            SELECT id FROM tipos_denuncia
            ORDER BY id
            LIMIT 6
        """)
        tipos = cursor.fetchall()

        if not tipos:
            return

        demo_data = [
            ("Bache en la vía principal (DEMO)", "Frente al parque central", -0.915601, -78.6318955, "formulario"),
            ("Falta de alumbrado público (DEMO)", "Calle Bolívar y Sucre", -0.915592, -78.6318774, "chat"),
            ("Basura acumulada (DEMO)", "Esquina del mercado", -0.9156072, -78.6319116, "formulario"),
            ("Fuga de agua (DEMO)", "Barrio Norte", -0.9156003, -78.6319039, "chat"),
            ("Quema de basura (DEMO)", "Cerca de la cancha", -0.9145766, -78.6289773, "formulario"),
            ("Aceras dañadas (DEMO)", "Av. Principal", -1.0433963, -78.5917322, "chat"),
        ]

        for i, (desc, ref, lat, lng, origen) in enumerate(demo_data):
            tipo_id = tipos[i % len(tipos)][0]

            cursor.execute("""
                INSERT INTO denuncias (
                    id,
                    ciudadano_id,
                    tipo_denuncia_id,
                    descripcion,
                    referencia,
                    latitud,
                    longitud,
                    origen,
                    created_at,
                    updated_at
                )
                SELECT gen_random_uuid(), %s, %s, %s, %s, %s, %s, %s, now(), now()
                WHERE NOT EXISTS (
                    SELECT 1 FROM denuncias WHERE descripcion = %s
                )
            """, [user_id, tipo_id, desc, ref, lat, lng, origen, desc])


def unseed_demo_denuncias(apps, schema_editor):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM denuncias WHERE descripcion ILIKE '%(DEMO)%'")
        cursor.execute("DELETE FROM ciudadanos WHERE cedula = '1100000000'")
        cursor.execute("DELETE FROM usuarios WHERE correo = 'demo.ciudadano@utc.local'")


class Migration(migrations.Migration):

    dependencies = [
        ("db", "0002_borradorarchivo_denunciaarchivo"),
    ]

    operations = [
        migrations.RunPython(seed_demo_denuncias, reverse_code=unseed_demo_denuncias),
    ]