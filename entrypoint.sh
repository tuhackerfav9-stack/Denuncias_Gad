#!/bin/sh
set -e

echo "Aplicando migraciones..."
python manage.py migrate --noinput

echo "Recolectando estáticos..."
python manage.py collectstatic --noinput

echo "Verificando superusuario..."
python manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()

username = os.getenv("DJANGO_SUPERUSER_USERNAME")
email = os.getenv("DJANGO_SUPERUSER_EMAIL")
password = os.getenv("DJANGO_SUPERUSER_PASSWORD")

if username and password:
    field_name = User.USERNAME_FIELD
    lookup = {field_name: username}

    if not User.objects.filter(**lookup).exists():
        extra = {}
        field_names = {f.name for f in User._meta.fields}
        if "email" in field_names and email:
            extra["email"] = email

        User.objects.create_superuser(password=password, **lookup, **extra)
        print("Superusuario creado correctamente.")
    else:
        print("El superusuario ya existe.")
else:
    print("Variables de superusuario no definidas. Se omite creación.")
PY

echo "Levantando Gunicorn..."
exec gunicorn config.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 2 \
  --threads 4 \
  --timeout 180 \
  --graceful-timeout 30 \
  --access-logfile - \
  --error-logfile - \
  --capture-output