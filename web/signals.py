# web/signals.py
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User

from web.services.webuser_domain import ensure_domain_for_web_user, detach_domain_for_web_user


@receiver(post_save, sender=User)
def on_user_saved(sender, instance: User, created, **kwargs):
    #   crea o sincroniza SI es staff
    ensure_domain_for_web_user(instance)


@receiver(pre_delete, sender=User)
def on_user_delete(sender, instance: User, **kwargs):
    #   limpieza en 3 tablas
    detach_domain_for_web_user(instance)
