from django.contrib import admin
from .models import Person

@admin.register(Person)
class PersonAdmin(admin.ModelAdmin):
    list_display = ('user', 'staff_access', 'admin_access')
    search_fields = ('user__email', 'user__username')
    exclude = ('is_staff', 'is_superuser')
    readonly_fields = ('staff_access', 'admin_access')

    @admin.display(boolean=True, description='Staff (definido em Users)')
    def staff_access(self, obj):
        return bool(obj and obj.user.is_staff)

    @admin.display(boolean=True, description='Administrador (definido em Users)')
    def admin_access(self, obj):
        return bool(obj and obj.user.is_superuser)
