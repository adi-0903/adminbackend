from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User, UserInformation

class CustomUserAdmin(UserAdmin):
    list_display = ('phone_number', 'referral_code', 'is_staff', 'is_active', 'date_joined')
    list_filter = ('is_staff', 'is_active')
    fieldsets = (
        (None, {'fields': ('phone_number', 'password', 'referral_code')}),
        ('Permissions', {'fields': ('is_staff', 'is_active', 'groups', 'user_permissions')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('phone_number', 'password1', 'password2', 'is_staff', 'is_active')}
        ),
    )
    search_fields = ('phone_number',)
    ordering = ('phone_number',)

admin.site.register(User, CustomUserAdmin)

class UserInformationAdmin(admin.ModelAdmin):
    list_display = ('user', 'name', 'email', 'user_phone_number', 'user_referral_code')
    search_fields = ('user__phone_number', 'name', 'email')
    list_filter = ('user__is_active',)
    list_select_related = ('user',)

    def user_phone_number(self, obj: UserInformation) -> str:
        return obj.user.phone_number if obj.user else ''
    user_phone_number.short_description = 'Phone Number'
    user_phone_number.admin_order_field = 'user__phone_number'

    def user_referral_code(self, obj: UserInformation) -> str:
        return obj.user.referral_code if obj.user else ''
    user_referral_code.short_description = 'Referral Code'
    user_referral_code.admin_order_field = 'user__referral_code'

admin.site.register(UserInformation, UserInformationAdmin)