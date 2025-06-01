from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser, Doctor, Patient, Service, Appointment, ServiceCategory, Review 

class CustomUserAdmin(UserAdmin):
    model = CustomUser
    list_display = ('phone', 'first_name', 'last_name', 'is_staff', 'is_superuser')
    search_fields = ('phone', 'first_name', 'last_name', 'patronymic')
    ordering = ('phone',)
    fieldsets = (
        (None, {'fields': ('phone', 'password')}),
        ('Личная информация', {'fields': ('first_name', 'patronymic', 'last_name')}),
        ('Права доступа', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Даты', {'fields': ('last_login',)}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone', 'first_name', 'last_name', 'patronymic', 'password1', 'password2', 'is_staff', 'is_superuser')}
        ),
    )

admin.site.register(CustomUser, CustomUserAdmin)
admin.site.register(Doctor)
admin.site.register(Patient)
@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price")
    list_filter = ("category",)
    search_fields = ("name",)
    ordering = ("category__name", "name")
    fields = ("category", "name", "price")

    # Делает колонку «Категория» редактируемой прямо из списка
    list_editable = ("category",)

    # Чтобы список оставался читабельным, переносим кнопку «Сохранить» ниже:
    list_display_links = ("name",)
admin.site.register(Appointment)
admin.site.register(Review)
