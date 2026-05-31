from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ['username', 'email', 'is_blocked', 'is_staff']
    fieldsets = UserAdmin.fieldsets + (
        (None, {'fields': ('avatar', 'bio', 'birth_date', 'is_blocked')}),
    )

admin.site.register(CustomUser, CustomUserAdmin)