from django.contrib import admin
from .models import Wallet, WalletTransaction

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['id', 'user', 'balance', 'is_active', 'created_at', 'updated_at']
    list_filter = ['is_active']
    search_fields = ['user__phone_number']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('user')

@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ['id', 'wallet_user', 'amount', 'description','transaction_type', 'status', 
                    'razorpay_order_id', 'created_at']
    list_filter = ['transaction_type', 'status', 'created_at']
    search_fields = ['wallet__user__phone_number', 'razorpay_order_id', 
                    'razorpay_payment_id', 'description']
    readonly_fields = ['created_at', 'updated_at']
    ordering = ['-created_at']

    def wallet_user(self, obj):
        return obj.wallet.user.phone_number
    wallet_user.short_description = 'User'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('wallet', 'wallet__user')
