from django.contrib import admin
from .models import Admin

@admin.register(Admin)
class AdminUserAdmin(admin.ModelAdmin):
    list_display = ('name', 'email')
    search_fields = ('name', 'email')
