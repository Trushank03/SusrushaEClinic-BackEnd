from rest_framework import serializers
from django.utils import timezone
from authentication.models import User
from .models import (
    Payment, PaymentMethod, PaymentRefund, PaymentDiscount,
    PaymentTransaction
)

class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for payment"""
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.name', read_only=True)
    consultation_id = serializers.CharField(source='consultation.id', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'patient', 'doctor', 'patient_name', 'doctor_name', 'consultation', 'consultation_id',
            'payment_type', 'amount', 'currency', 'description', 'payment_method', 'payment_method_details',
            'status', 'gateway_name', 'gateway_transaction_id', 'gateway_response',
            'platform_fee', 'gateway_fee', 'tax_amount', 'discount_amount', 'net_amount',
            'initiated_at', 'processed_at', 'completed_at', 'failed_at',
            'failure_reason', 'failure_code', 'receipt_number', 'receipt_url',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'gateway_transaction_id', 'gateway_response', 'net_amount', 'created_at', 'updated_at']


class PaymentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payment"""
    
    class Meta:
        model = Payment
        fields = [
            'doctor', 'consultation', 'payment_type', 'amount', 'currency',
            'description', 'payment_method', 'payment_method_details'
        ]
    
    def create(self, validated_data):
        """Create payment"""
        patient = self.context['request'].user
        validated_data['patient'] = patient
        validated_data['status'] = 'pending'
        
        # Generate transaction ID
        import uuid
        validated_data['transaction_id'] = f"TXN{uuid.uuid4().hex[:12].upper()}"
        
        return super().create(validated_data)


class PaymentMethodSerializer(serializers.ModelSerializer):
    """Serializer for payment method"""
    user_name = serializers.CharField(source='user.name', read_only=True)
    
    class Meta:
        model = PaymentMethod
        fields = [
            'id', 'user', 'user_name', 'method_type', 'card_last_four', 'card_brand',
            'card_expiry_month', 'card_expiry_year', 'upi_id', 'bank_name',
            'account_last_four', 'wallet_provider', 'wallet_phone', 'gateway_method_id',
            'gateway_customer_id', 'is_default', 'is_active', 'nickname', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PaymentMethodCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payment method"""
    
    class Meta:
        model = PaymentMethod
        fields = [
            'method_type', 'card_last_four', 'card_brand', 'card_expiry_month',
            'card_expiry_year', 'upi_id', 'bank_name', 'account_last_four',
            'wallet_provider', 'wallet_phone', 'gateway_method_id', 'gateway_customer_id',
            'is_default', 'is_active', 'nickname'
        ]
    
    def create(self, validated_data):
        """Create payment method"""
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)


class PaymentRefundSerializer(serializers.ModelSerializer):
    """Serializer for payment refund"""
    payment_id = serializers.CharField(source='payment.id', read_only=True)
    patient_name = serializers.CharField(source='payment.patient.name', read_only=True)
    initiated_by_name = serializers.CharField(source='initiated_by.name', read_only=True)
    
    class Meta:
        model = PaymentRefund
        fields = [
            'id', 'payment', 'payment_id', 'patient_name', 'initiated_by', 'initiated_by_name',
            'refund_amount', 'reason', 'description', 'status', 'gateway_refund_id',
            'gateway_response', 'initiated_at', 'processed_at', 'completed_at',
            'failure_reason', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'gateway_refund_id', 'gateway_response', 'initiated_at', 'processed_at', 'completed_at', 'created_at', 'updated_at']


class PaymentRefundCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating payment refund"""
    
    class Meta:
        model = PaymentRefund
        fields = ['payment', 'refund_amount', 'reason', 'description']
    
    def create(self, validated_data):
        """Create payment refund"""
        initiated_by = self.context['request'].user
        validated_data['initiated_by'] = initiated_by
        validated_data['status'] = 'pending'
        return super().create(validated_data)


class PaymentDiscountSerializer(serializers.ModelSerializer):
    """Serializer for payment discount"""
    
    class Meta:
        model = PaymentDiscount
        fields = [
            'id', 'code', 'name', 'description', 'discount_type',
            'discount_value', 'max_discount_amount', 'min_order_amount',
            'max_uses', 'max_uses_per_user', 'current_uses', 'valid_from', 'valid_until',
            'applicable_to_first_time_users', 'is_active', 'created_by', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'current_uses', 'created_at', 'updated_at']


class PaymentTransactionSerializer(serializers.ModelSerializer):
    """Serializer for payment transaction"""
    payment_id = serializers.CharField(source='payment.id', read_only=True)
    patient_name = serializers.CharField(source='payment.patient.name', read_only=True)
    
    class Meta:
        model = PaymentTransaction
        fields = [
            'id', 'payment', 'payment_id', 'patient_name', 'transaction_type', 'amount',
            'gateway_transaction_id', 'gateway_response', 'is_successful', 'error_message', 'created_at'
        ]
        read_only_fields = ['id', 'gateway_transaction_id', 'gateway_response', 'created_at']




class PaymentListSerializer(serializers.ModelSerializer):
    """Serializer for payment list view"""
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.name', read_only=True)
    consultation_id = serializers.CharField(source='consultation.id', read_only=True)
    
    class Meta:
        model = Payment
        fields = [
            'id', 'patient', 'doctor', 'patient_name', 'doctor_name', 'consultation', 'consultation_id',
            'payment_type', 'amount', 'currency', 'status', 'payment_method',
            'gateway_transaction_id', 'net_amount', 'initiated_at', 'created_at'
        ]


class PaymentSearchSerializer(serializers.Serializer):
    """Serializer for payment search"""
    query = serializers.CharField(max_length=200, required=False)
    user_id = serializers.IntegerField(required=False)
    consultation_id = serializers.IntegerField(required=False)
    payment_type = serializers.ChoiceField(
        choices=Payment._meta.get_field('payment_type').choices,
        required=False
    )
    status = serializers.ChoiceField(
        choices=Payment._meta.get_field('status').choices,
        required=False
    )
    payment_method = serializers.CharField(max_length=50, required=False)
    amount_min = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    amount_max = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    
    def validate(self, attrs):
        """Validate search parameters"""
        date_from = attrs.get('date_from')
        date_to = attrs.get('date_to')
        amount_min = attrs.get('amount_min')
        amount_max = attrs.get('amount_max')
        
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError('date_from cannot be greater than date_to')
        
        if amount_min and amount_max and amount_min > amount_max:
            raise serializers.ValidationError('amount_min cannot be greater than amount_max')
        
        return attrs


class PaymentStatsSerializer(serializers.Serializer):
    """Serializer for payment statistics"""
    total_payments = serializers.IntegerField()
    successful_payments = serializers.IntegerField()
    failed_payments = serializers.IntegerField()
    pending_payments = serializers.IntegerField()
    total_revenue = serializers.DecimalField(max_digits=15, decimal_places=2)
    total_refunds = serializers.DecimalField(max_digits=15, decimal_places=2)
    payment_method_distribution = serializers.DictField()
    monthly_revenue = serializers.ListField()
    average_transaction_amount = serializers.DecimalField(max_digits=10, decimal_places=2)


class PaymentProcessSerializer(serializers.Serializer):
    """Serializer for processing payment"""
    payment_method_id = serializers.IntegerField(required=False)
    gateway = serializers.ChoiceField(
        choices=[('stripe', 'Stripe'), ('razorpay', 'Razorpay'), ('payu', 'PayU'), ('phonepe', 'PhonePe')],
        required=True
    )
    payment_token = serializers.CharField(max_length=500, required=False)
    return_url = serializers.URLField(required=False)
    cancel_url = serializers.URLField(required=False)


class DiscountValidationSerializer(serializers.Serializer):
    """Serializer for discount validation"""
    discount_code = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    
    def validate_discount_code(self, value):
        """Validate discount code"""
        try:
            discount = PaymentDiscount.objects.get(
                code=value,
                is_active=True,
                valid_from__lte=timezone.now(),
                valid_until__gte=timezone.now()
            )
            
            if discount.usage_limit and discount.used_count >= discount.usage_limit:
                raise serializers.ValidationError('Discount code has reached its usage limit')
            
            return value
        except PaymentDiscount.DoesNotExist:
            raise serializers.ValidationError('Invalid or expired discount code')


class PaymentWebhookSerializer(serializers.Serializer):
    """Serializer for payment webhook data"""
    gateway = serializers.CharField(max_length=50)
    event_type = serializers.CharField(max_length=100)
    transaction_id = serializers.CharField(max_length=100)
    gateway_transaction_id = serializers.CharField(max_length=100)
    status = serializers.CharField(max_length=50)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    currency = serializers.CharField(max_length=3, required=False)
    metadata = serializers.JSONField(required=False)

