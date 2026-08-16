"""JWT authentication that enforces email-verification and MFA account policy."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from core.models import User
from core.security import account_ready_for_access, mfa_required


class VerifiedJWTAuthentication(JWTAuthentication):
    """Reject JWT use when the account is not eligible for API access."""

    def get_user(self, validated_token):
        user = super().get_user(validated_token)
        if not account_ready_for_access(user):
            raise AuthenticationFailed(
                'يجب تأكيد البريد الإلكتروني قبل استخدام الواجهة البرمجية.',
                code='email_unverified',
            )
        if mfa_required(user):
            raise AuthenticationFailed(
                'تتطلب هذه الحسابات مصادقة متعددة العوامل عبر بوابة الويب.',
                code='mfa_required',
            )
        return user


class VerifiedTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Issue tokens only to verified API-eligible accounts."""

    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user
        if not account_ready_for_access(user):
            raise AuthenticationFailed(
                'يجب تأكيد البريد الإلكتروني قبل تسجيل الدخول إلى الواجهة البرمجية.',
                code='email_unverified',
            )
        if mfa_required(user):
            raise AuthenticationFailed(
                'أكمل المصادقة متعددة العوامل عبر بوابة الويب أولًا.',
                code='mfa_required',
            )
        return data


class VerifiedTokenObtainPairView(TokenObtainPairView):
    serializer_class = VerifiedTokenObtainPairSerializer


class VerifiedTokenRefreshSerializer(TokenRefreshSerializer):
    """Refuse refresh rotation once an account is no longer eligible."""

    def validate(self, attrs):
        refresh = self.token_class(attrs['refresh'])
        user = User.objects.filter(id=refresh.get('user_id')).first()
        if not user or not account_ready_for_access(user) or mfa_required(user):
            raise AuthenticationFailed('لم يعد الحساب مؤهلًا لتجديد رمز الوصول.', code='account_not_ready')
        return super().validate(attrs)


class VerifiedTokenRefreshView(TokenRefreshView):
    serializer_class = VerifiedTokenRefreshSerializer
