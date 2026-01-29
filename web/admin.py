from django.contrib import admin
from .models import Menus
from .models import Menus, FuncionarioWebUser
@admin.register(Menus)
class MenusAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'url', 'padre', 'orden')
    list_editable = ('orden',)
    search_fields = ('nombre', 'url')
    ordering = ('orden',)

admin.site.register(FuncionarioWebUser)