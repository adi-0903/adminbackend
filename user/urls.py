from django.urls import path
from .views import UserLoginView, VerifyOTPView, ApplyReferralCodeView, UserInformationView

urlpatterns = [
    path('login/', UserLoginView.as_view(), name='user-login'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('apply-referral-code/', ApplyReferralCodeView.as_view(), name='apply-referral-code'),
    path('user-info/', UserInformationView.as_view(), name='user-info'),
]
