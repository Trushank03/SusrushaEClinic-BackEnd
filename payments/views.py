from rest_framework import status, permissions, filters
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ModelViewSet
from rest_framework.pagination import PageNumberPagination
from django.utils import timezone
from django.db.models import Q, Count, Sum, Avg
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from drf_spectacular.openapi import OpenApiTypes
from datetime import datetime, timedelta
import json
import requests
import hmac
import hashlib
import base64
from django.conf import settings

from authentication.models import User
from .models import (
    Payment, PaymentMethod, PaymentRefund, PaymentDiscount,
    PaymentTransaction
)
from .serializers import (
    PaymentSerializer, PaymentCreateSerializer,
    PaymentMethodSerializer, PaymentMethodCreateSerializer,
    PaymentRefundSerializer, PaymentRefundCreateSerializer,
    PaymentDiscountSerializer, PaymentTransactionSerializer,
    PaymentListSerializer,
    PaymentSearchSerializer, PaymentStatsSerializer,
    PaymentProcessSerializer, DiscountValidationSerializer,
    PaymentWebhookSerializer
)
from .phonepe_service import PhonePeService


class PaymentPagination(PageNumberPagination):
    """Custom pagination for payment lists"""
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


class PatientPaymentsView(APIView):
    """View for patient to get their payments"""
    permission_classes = [permissions.IsAuthenticated]
    
    @extend_schema(
        parameters=[
            OpenApiParameter('status', OpenApiTypes.STR, description='Filter by payment status'),
            OpenApiParameter('payment_method', OpenApiTypes.STR, description='Filter by payment method'),
            OpenApiParameter('ordering', OpenApiTypes.STR, description='Order by field (e.g., -created_at)'),
            OpenApiParameter('page', OpenApiTypes.INT, description='Page number'),
            OpenApiParameter('page_size', OpenApiTypes.INT, description='Number of items per page'),
        ],
        responses={200: PaymentListSerializer(many=True)},
        description="Get payments for the logged-in patient"
    )
    def get(self, request):
        """Get payments for the logged-in patient"""
        # Check if user is a patient
        if request.user.role != 'patient':
            return Response({
                'success': False,
                'error': {
                    'code': 'PERMISSION_DENIED',
                    'message': 'Only patients can access this endpoint'
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get payments for the patient
        queryset = Payment.objects.filter(patient=request.user).select_related('consultation')
        
        # Apply filters
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        payment_method = request.query_params.get('payment_method')
        if payment_method:
            queryset = queryset.filter(payment_method=payment_method)
        
        # Apply ordering
        ordering = request.query_params.get('ordering', '-created_at')
        queryset = queryset.order_by(ordering)
        
        # Apply pagination
        paginator = PaymentPagination()
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = PaymentListSerializer(page, many=True)
            return paginator.get_paginated_response(serializer.data)
        
        serializer = PaymentListSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'Patient payments retrieved successfully',
            'timestamp': timezone.now().isoformat()
        })


class PaymentViewSet(ModelViewSet):
    """ViewSet for payment management"""
    queryset = Payment.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = PaymentPagination
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['transaction_id', 'patient__name', 'description']
    ordering_fields = ['created_at', 'amount', 'status']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return PaymentCreateSerializer
        elif self.action == 'list':
            return PaymentListSerializer
        return PaymentSerializer
    
    def get_queryset(self):
        """Filter queryset based on user role"""
        user = self.request.user
        queryset = Payment.objects.select_related('patient', 'consultation')
        
        if user.role == 'patient':
            # Patients can only see their own payments
            return queryset.filter(patient=user)
        elif user.role == 'doctor':
            # Doctors can see payments for their consultations
            return queryset.filter(consultation__doctor=user)
        elif user.role in ['admin', 'superadmin']:
            # Admins can see all payments
            return queryset
        
        return queryset.none()
    
    @action(detail=True, methods=['post'])
    def process(self, request, pk=None):
        """Process payment"""
        payment = self.get_object()
        
        if payment.status != 'pending':
            return Response({
                'success': False,
                'error': {
                    'code': 'INVALID_STATUS',
                    'message': 'Only pending payments can be processed'
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = PaymentProcessSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'Invalid payment processing data',
                    'details': serializer.errors
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Process payment based on gateway
        gateway = serializer.validated_data['gateway']
        
        try:
            # Here you would integrate with actual payment gateways
            # For demo purposes, we'll simulate the process
            
            if gateway == 'stripe':
                result = self._process_stripe_payment(payment, serializer.validated_data)
            elif gateway == 'razorpay':
                result = self._process_razorpay_payment(payment, serializer.validated_data)
            elif gateway == 'payu':
                result = self._process_payu_payment(payment, serializer.validated_data)
            elif gateway == 'phonepe':
                result = self._process_phonepe_payment(payment, serializer.validated_data)
            else:
                raise ValueError(f"Unsupported gateway: {gateway}")
            
            # Update payment status based on result
            # For PhonePe, status might be 'processing' initially (requires user redirect)
            if result['success']:
                # PhonePe returns a payment URL that needs user interaction
                if gateway == 'phonepe' and result.get('payment_url'):
                    payment.status = 'processing'
                    payment.gateway_name = 'phonepe'
                else:
                    payment.status = 'completed'
                    payment.processed_at = timezone.now()
                
                payment.gateway_transaction_id = result.get('transaction_id') or result.get('merchant_transaction_id')
                payment.gateway_response = result.get('response', {})
            else:
                payment.status = 'failed'
                payment.failure_reason = result.get('error', 'Payment processing failed')
                payment.gateway_response = {'error': result.get('error', {})}
            
            payment.save()
            
            # Create transaction record
            PaymentTransaction.objects.create(
                payment=payment,
                transaction_type='payment',
                amount=payment.amount,
                is_successful=result['success'],
                gateway_transaction_id=payment.gateway_transaction_id,
                gateway_response=payment.gateway_response,
            )
            
            response_serializer = PaymentSerializer(payment)
            return Response({
                'success': True,
                'data': response_serializer.data,
                'payment_url': result.get('payment_url'),
                'message': 'Payment processed successfully' if result['success'] else 'Payment failed',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            payment.status = 'failed'
            payment.gateway_response = {'error': str(e)}
            payment.save()
            
            return Response({
                'success': False,
                'error': {
                    'code': 'PAYMENT_PROCESSING_ERROR',
                    'message': f'Payment processing failed: {str(e)}'
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _process_stripe_payment(self, payment, data):
        """Process payment via Stripe (mock implementation)"""
        # Mock Stripe payment processing
        import uuid
        return {
            'success': True,
            'transaction_id': f"stripe_{uuid.uuid4().hex[:16]}",
            'payment_url': f"https://checkout.stripe.com/pay/{uuid.uuid4().hex}",
            'response': {'status': 'succeeded', 'gateway': 'stripe'}
        }
    
    def _process_razorpay_payment(self, payment, data):
        """Process payment via Razorpay (mock implementation)"""
        # Mock Razorpay payment processing
        import uuid
        return {
            'success': True,
            'transaction_id': f"razorpay_{uuid.uuid4().hex[:16]}",
            'payment_url': f"https://api.razorpay.com/v1/checkout/{uuid.uuid4().hex}",
            'response': {'status': 'captured', 'gateway': 'razorpay'}
        }
    
    def _process_payu_payment(self, payment, data):
        """Process payment via PayU (mock implementation)"""
        # Mock PayU payment processing
        import uuid
        return {
            'success': True,
            'transaction_id': f"payu_{uuid.uuid4().hex[:16]}",
            'payment_url': f"https://secure.payu.in/_payment/{uuid.uuid4().hex}",
            'response': {'status': 'success', 'gateway': 'payu'}
        }
    
    def _process_phonepe_payment(self, payment, data):
        """Process payment via PhonePe"""
        phonepe_service = PhonePeService()
        
        # Get customer information from payment
        customer_info = {
            'mobile': getattr(payment.patient, 'phone', '') or getattr(payment.patient, 'phone_number', '') or '',
            'email': getattr(payment.patient, 'email', '') or '',
            'name': getattr(payment.patient, 'name', '') or getattr(payment.patient, 'full_name', '') or ''
        }
        
        # Prepare additional info
        additional_info = {
            'payment_type': payment.payment_type,
            'description': payment.description,
            'consultation_id': str(payment.consultation.id) if payment.consultation else None
        }
        
        # Initiate payment
        result = phonepe_service.initiate_payment(
            payment_id=payment.id,
            amount=float(payment.net_amount),
            customer_info=customer_info,
            additional_info=additional_info
        )
        
        return result
    
    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """Initiate payment refund"""
        payment = self.get_object()
        
        if payment.status != 'completed':
            return Response({
                'success': False,
                'error': {
                    'code': 'INVALID_STATUS',
                    'message': 'Only completed payments can be refunded'
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        serializer = PaymentRefundCreateSerializer(data=request.data)
        if serializer.is_valid():
            refund = serializer.save()
            
            # Process refund (mock implementation)
            refund.status = 'completed'
            refund.processed_at = timezone.now()
            refund.save()
            
            response_serializer = PaymentRefundSerializer(refund)
            return Response({
                'success': True,
                'data': response_serializer.data,
                'message': 'Refund processed successfully',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_201_CREATED)
        
        return Response({
            'success': False,
            'error': {
                'code': 'VALIDATION_ERROR',
                'message': 'Invalid refund data',
                'details': serializer.errors
            },
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_400_BAD_REQUEST)


class PaymentMethodViewSet(ModelViewSet):
    """ViewSet for payment method management"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get payment methods for authenticated user"""
        return PaymentMethod.objects.filter(user=self.request.user)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return PaymentMethodCreateSerializer
        return PaymentMethodSerializer
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set payment method as default"""
        payment_method = self.get_object()
        
        # Remove default from other methods
        PaymentMethod.objects.filter(user=request.user).update(is_default=False)
        
        # Set this method as default
        payment_method.is_default = True
        payment_method.save()
        
        serializer = PaymentMethodSerializer(payment_method)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'Payment method set as default',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)


class PaymentRefundViewSet(ModelViewSet):
    """ViewSet for payment refund management"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Get refunds based on user role"""
        user = self.request.user
        if user.role in ['admin', 'superadmin']:
            return PaymentRefund.objects.all()
        else:
            return PaymentRefund.objects.filter(payment__patient=user)
    
    def get_serializer_class(self):
        """Return appropriate serializer based on action"""
        if self.action == 'create':
            return PaymentRefundCreateSerializer
        return PaymentRefundSerializer


class PaymentDiscountViewSet(ModelViewSet):
    """ViewSet for payment discount management"""
    queryset = PaymentDiscount.objects.all()
    serializer_class = PaymentDiscountSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        """Filter discounts based on user role"""
        user = self.request.user
        if user.role in ['admin', 'superadmin']:
            return PaymentDiscount.objects.all()
        else:
            # Regular users can only see active discounts
            return PaymentDiscount.objects.filter(
                is_active=True,
                valid_from__lte=timezone.now(),
                valid_until__gte=timezone.now()
            )


class PaymentSearchView(APIView):
    """Search payments with advanced filters"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Search payments with advanced filters"""
        serializer = PaymentSearchSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'Invalid search parameters',
                    'details': serializer.errors
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Build query
        queryset = Payment.objects.select_related('patient', 'consultation')
        
        # Apply role-based filtering
        user = request.user
        if user.role == 'patient':
            queryset = queryset.filter(patient=user)
        elif user.role == 'doctor':
            queryset = queryset.filter(consultation__doctor=user)
        elif user.role not in ['admin', 'superadmin']:
            return Response({
                'success': False,
                'error': {
                    'code': 'PERMISSION_DENIED',
                    'message': 'Insufficient permissions'
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Apply search filters
        search_data = serializer.validated_data
        
        if search_data.get('query'):
            query = search_data['query']
            queryset = queryset.filter(
                Q(patient__name__icontains=query) |
                Q(id__icontains=query) |
                Q(description__icontains=query)
            )
        
        if search_data.get('patient_id'):
            queryset = queryset.filter(patient_id=search_data['patient_id'])
        
        if search_data.get('consultation_id'):
            queryset = queryset.filter(consultation_id=search_data['consultation_id'])
        
        if search_data.get('payment_type'):
            queryset = queryset.filter(payment_type=search_data['payment_type'])
        
        if search_data.get('status'):
            queryset = queryset.filter(status=search_data['status'])
        
        if search_data.get('payment_method'):
            queryset = queryset.filter(payment_method__icontains=search_data['payment_method'])
        
        if search_data.get('amount_min'):
            queryset = queryset.filter(amount__gte=search_data['amount_min'])
        
        if search_data.get('amount_max'):
            queryset = queryset.filter(amount__lte=search_data['amount_max'])
        
        if search_data.get('date_from'):
            queryset = queryset.filter(created_at__date__gte=search_data['date_from'])
        
        if search_data.get('date_to'):
            queryset = queryset.filter(created_at__date__lte=search_data['date_to'])
        
        # Paginate results
        paginator = PaymentPagination()
        page = paginator.paginate_queryset(queryset, request)
        
        if page is not None:
            serializer = PaymentListSerializer(page, many=True)
            return paginator.get_paginated_response({
                'success': True,
                'data': serializer.data,
                'message': 'Search results retrieved successfully',
                'timestamp': timezone.now().isoformat()
            })
        
        serializer = PaymentListSerializer(queryset, many=True)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'Search results retrieved successfully',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)


class PaymentStatsView(APIView):
    """Get payment statistics"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get payment statistics"""
        # Check permissions
        if request.user.role not in ['admin', 'superadmin']:
            return Response({
                'success': False,
                'error': {
                    'code': 'PERMISSION_DENIED',
                    'message': 'Insufficient permissions'
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Build base queryset with clinic filtering
        payments = Payment.objects.all()
        
        # Filter by clinic if user is an admin (not superadmin)
        if request.user.role == 'admin':
            # Get clinics where this user is admin
            from eclinic.models import Clinic
            user_clinics = Clinic.objects.filter(admin=request.user)
            if user_clinics.exists():
                clinic_ids = [clinic.id for clinic in user_clinics]
                payments = payments.filter(consultation__clinic__id__in=clinic_ids)
        
        # Calculate statistics
        total_payments = payments.count()
        successful_payments = payments.filter(status='completed').count()
        failed_payments = payments.filter(status='failed').count()
        pending_payments = payments.filter(status='pending').count()
        
        # Revenue calculations
        total_revenue = payments.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        total_refunds = PaymentRefund.objects.filter(status='completed').aggregate(
            total=Sum('refund_amount')
        )['total'] or 0
        
        # Payment method distribution
        payment_method_distribution = dict(
            payments.values('payment_method').annotate(
                count=Count('payment_method')
            ).values_list('payment_method', 'count')
        )
        
        # Monthly revenue (last 12 months)
        monthly_revenue = []
        for i in range(12):
            month_start = timezone.now().replace(day=1) - timedelta(days=30*i)
            month_end = month_start + timedelta(days=30)
            
            month_revenue = payments.filter(
                status='completed',
                processed_at__gte=month_start,
                processed_at__lt=month_end
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            monthly_revenue.append({
                'month': month_start.strftime('%Y-%m'),
                'revenue': float(month_revenue)
            })
        
        # Average transaction amount
        avg_amount = payments.filter(status='completed').aggregate(
            avg=Avg('amount')
        )['avg'] or 0
        
        stats_data = {
            'total_payments': total_payments,
            'successful_payments': successful_payments,
            'failed_payments': failed_payments,
            'pending_payments': pending_payments,
            'total_revenue': float(total_revenue),
            'total_refunds': float(total_refunds),
            'payment_method_distribution': payment_method_distribution,
            'monthly_revenue': monthly_revenue,
            'average_transaction_amount': float(avg_amount)
        }
        
        serializer = PaymentStatsSerializer(stats_data)
        return Response({
            'success': True,
            'data': serializer.data,
            'message': 'Payment statistics retrieved successfully',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)


class DiscountValidationView(APIView):
    """Validate discount codes"""
    permission_classes = [permissions.IsAuthenticated]
    
    def post(self, request):
        """Validate discount code"""
        serializer = DiscountValidationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': {
                    'code': 'VALIDATION_ERROR',
                    'message': 'Invalid discount validation data',
                    'details': serializer.errors
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)
        
        discount_code = serializer.validated_data['discount_code']
        amount = serializer.validated_data['amount']
        
        try:
            discount = PaymentDiscount.objects.get(
                code=discount_code,
                is_active=True,
                valid_from__lte=timezone.now(),
                valid_until__gte=timezone.now()
            )
            
            # Check minimum amount
            if discount.min_order_amount and amount < discount.min_order_amount:
                return Response({
                    'success': False,
                    'error': {
                        'code': 'MINIMUM_AMOUNT_NOT_MET',
                        'message': f'Minimum amount of {discount.min_order_amount} required'
                    },
                    'timestamp': timezone.now().isoformat()
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Calculate discount amount
            if discount.discount_type == 'percentage':
                discount_amount = (amount * discount.discount_value) / 100
            else:  # fixed
                discount_amount = discount.discount_value
            
            # Apply maximum discount limit
            if discount.max_discount_amount:
                discount_amount = min(discount_amount, discount.max_discount_amount)
            
            final_amount = amount - discount_amount
            
            return Response({
                'success': True,
                'data': {
                    'discount': PaymentDiscountSerializer(discount).data,
                    'original_amount': float(amount),
                    'discount_amount': float(discount_amount),
                    'final_amount': float(final_amount)
                },
                'message': 'Discount code validated successfully',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except PaymentDiscount.DoesNotExist:
            return Response({
                'success': False,
                'error': {
                    'code': 'INVALID_DISCOUNT_CODE',
                    'message': 'Invalid or expired discount code'
                },
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_400_BAD_REQUEST)


class PhonePeCallbackView(APIView):
    """Handle PhonePe payment callback/webhook"""
    permission_classes = []  # No authentication required for webhooks
    
    def post(self, request):
        """Handle PhonePe callback"""
        try:
            phonepe_service = PhonePeService()
            
            # Get X-VERIFY header for signature verification
            x_verify_header = request.headers.get('X-VERIFY', '')
            
            # PhonePe sends base64 encoded response in request body
            webhook_data = request.data
            
            # Process webhook
            result = phonepe_service.process_webhook(webhook_data, x_verify_header)
            
            if not result['success']:
                return Response({
                    'success': False,
                    'error': result.get('error', 'Invalid webhook')
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Find payment by merchant transaction ID
            merchant_transaction_id = result.get('merchant_transaction_id')
            payment = Payment.objects.filter(gateway_transaction_id=merchant_transaction_id).first()
            
            if not payment:
                return Response({
                    'success': False,
                    'error': 'Payment not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Update payment status based on PhonePe response
            status_mapping = {
                'SUCCESS': 'completed',
                'PENDING': 'processing',
                'FAILURE': 'failed',
                'CANCELLED': 'cancelled'
            }
            
            phonepe_status = result.get('status', '').upper()
            payment.status = status_mapping.get(phonepe_status, 'failed')
            
            if payment.status == 'completed':
                payment.processed_at = timezone.now()
                payment.completed_at = timezone.now()
            elif payment.status == 'failed':
                payment.failed_at = timezone.now()
                payment.failure_reason = result.get('response_code', 'Payment failed')
                payment.failure_code = result.get('code', '')
            
            payment.gateway_response = result.get('response', {})
            payment.save()
            
            # Create transaction record
            PaymentTransaction.objects.create(
                payment=payment,
                transaction_type='webhook',
                amount=payment.amount,
                is_successful=payment.status == 'completed',
                gateway_transaction_id=result.get('transaction_id', merchant_transaction_id),
                gateway_response=result.get('response', {}),
            )
            
            return Response({
                'success': True,
                'message': 'PhonePe callback processed successfully'
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Error processing PhonePe callback: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def get(self, request):
        """Handle PhonePe redirect callback (GET request after payment)"""
        try:
            merchant_transaction_id = request.query_params.get('merchantTransactionId') or request.query_params.get('transaction_id')
            
            if not merchant_transaction_id:
                return Response({
                    'success': False,
                    'error': 'Missing transaction ID'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Find payment
            payment = Payment.objects.filter(gateway_transaction_id=merchant_transaction_id).first()
            
            if not payment:
                return Response({
                    'success': False,
                    'error': 'Payment not found'
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check payment status with PhonePe API
            phonepe_service = PhonePeService()
            status_result = phonepe_service.check_payment_status(merchant_transaction_id)
            
            if status_result['success']:
                status_mapping = {
                    'SUCCESS': 'completed',
                    'PENDING': 'processing',
                    'FAILURE': 'failed',
                    'CANCELLED': 'cancelled'
                }
                
                phonepe_status = status_result.get('status', '').upper()
                payment.status = status_mapping.get(phonepe_status, 'failed')
                
                if payment.status == 'completed':
                    payment.processed_at = timezone.now()
                    payment.completed_at = timezone.now()
                elif payment.status == 'failed':
                    payment.failed_at = timezone.now()
                    payment.failure_reason = status_result.get('code', 'Payment failed')
                
                payment.gateway_response = status_result.get('response', {})
                payment.save()
            
            # Return payment status
            serializer = PaymentSerializer(payment)
            return Response({
                'success': True,
                'data': serializer.data,
                'payment_status': payment.status
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Error processing redirect: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaymentWebhookView(APIView):
    """Handle payment gateway webhooks"""
    permission_classes = []  # No authentication required for webhooks
    
    def post(self, request):
        """Handle payment webhook"""
        serializer = PaymentWebhookSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'error': 'Invalid webhook data'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        webhook_data = serializer.validated_data
        
        try:
            # Find payment by transaction ID
            payment = Payment.objects.get(
                gateway_transaction_id=webhook_data['gateway_transaction_id']
            )
            
            # Update payment status based on webhook
            if webhook_data['status'] in ['completed', 'succeeded', 'captured']:
                payment.status = 'completed'
                payment.processed_at = timezone.now()
            elif webhook_data['status'] in ['failed', 'declined']:
                payment.status = 'failed'
            
            payment.gateway_response = webhook_data.get('metadata', {})
            payment.save()
            
            # Create transaction record
            PaymentTransaction.objects.create(
                payment=payment,
                transaction_type='webhook',
                amount=webhook_data.get('amount', payment.amount),
                is_successful=payment.status == 'completed',
                gateway_transaction_id=webhook_data['gateway_transaction_id'],
                gateway_response=webhook_data.get('metadata', {}),
            )
            
            return Response({
                'success': True,
                'message': 'Webhook processed successfully'
            }, status=status.HTTP_200_OK)
            
        except Payment.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Payment not found'
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({
                'success': False,
                'error': f'Webhook processing failed: {str(e)}'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PaymentInitiateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        request=PaymentProcessSerializer,
        responses={200: PaymentSerializer},
        description="Initiate payment for consultation"
    )
    def post(self, request):
        """Initiate payment for consultation"""
        serializer = PaymentProcessSerializer(data=request.data)
        if serializer.is_valid():
            # Payment initiation logic
            pass
        return Response({
            'success': False,
            'error': 'Payment initiation not implemented yet'
        }, status=status.HTTP_501_NOT_IMPLEMENTED)


class PaymentTrackingView(APIView):
    """Comprehensive payment tracking and analytics"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        """Get comprehensive payment tracking data"""
        # Check permissions
        if request.user.role not in ['admin', 'superadmin']:
            return Response({
                'success': False,
                'error': 'Insufficient permissions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get date range from query params
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        # Base queryset - filter by user's clinic if admin
        payments = Payment.objects.all()
        
        # Filter by clinic if user is an admin (not superadmin)
        if request.user.role == 'admin':
            # Get clinics where this user is admin
            from eclinic.models import Clinic
            user_clinics = Clinic.objects.filter(admin=request.user)
            if user_clinics.exists():
                clinic_ids = [clinic.id for clinic in user_clinics]
                payments = payments.filter(consultation__clinic__id__in=clinic_ids)
        
        # Apply date filters if provided
        if start_date:
            payments = payments.filter(created_at__date__gte=start_date)
        if end_date:
            payments = payments.filter(created_at__date__lte=end_date)
        
        # Calculate comprehensive statistics
        total_payments = payments.count()
        successful_payments = payments.filter(status='completed').count()
        failed_payments = payments.filter(status='failed').count()
        pending_payments = payments.filter(status='pending').count()
        
        # Revenue calculations
        total_revenue = payments.filter(status='completed').aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        total_refunds = PaymentRefund.objects.filter(status='completed').aggregate(
            total=Sum('refund_amount')
        )['total'] or 0
        
        # Payment method breakdown
        payment_method_breakdown = list(
            payments.values('payment_method').annotate(
                count=Count('payment_method'),
                total_amount=Sum('amount')
            ).order_by('-total_amount')
        )
        
        # Daily revenue for the last 30 days
        daily_revenue = []
        for i in range(30):
            date = timezone.now().date() - timedelta(days=i)
            day_revenue = payments.filter(
                status='completed',
                created_at__date=date
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            daily_revenue.append({
                'date': date.isoformat(),
                'revenue': float(day_revenue),
                'count': payments.filter(
                    status='completed',
                    created_at__date=date
                ).count()
            })
        
        # Top revenue sources (doctors)
        top_revenue_sources = list(
            payments.filter(
                status='completed',
                consultation__isnull=False
            ).values('consultation__doctor__name').annotate(
                total_revenue=Sum('amount'),
                consultation_count=Count('consultation')
            ).order_by('-total_revenue')[:10]
        )
        
        # Recent payments
        recent_payments = payments.order_by('-created_at')[:10]
        
        tracking_data = {
            'overview': {
                'total_payments': total_payments,
                'successful_payments': successful_payments,
                'failed_payments': failed_payments,
                'pending_payments': pending_payments,
                'total_revenue': float(total_revenue),
                'total_refunds': float(total_refunds),
                'net_revenue': float(total_revenue - total_refunds),
                'success_rate': (successful_payments / total_payments * 100) if total_payments > 0 else 0
            },
            'payment_method_breakdown': payment_method_breakdown,
            'daily_revenue': daily_revenue,
            'top_revenue_sources': top_revenue_sources,
            'recent_payments': PaymentListSerializer(recent_payments, many=True).data
        }
        
        return Response({
            'success': True,
            'data': tracking_data,
            'message': 'Payment tracking data retrieved successfully',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)


class PaymentReceiptView(APIView):
    """Handle payment receipt generation and retrieval"""
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request, payment_id):
        """Get payment receipt"""
        try:
            payment = Payment.objects.get(id=payment_id)
            
            # Check permissions
            user = request.user
            if user.role == 'patient' and payment.patient != user:
                return Response({
                    'success': False,
                    'error': 'You can only view your own payment receipts'
                }, status=status.HTTP_403_FORBIDDEN)
            
            if user.role == 'doctor' and payment.consultation and payment.consultation.doctor != user:
                return Response({
                    'success': False,
                    'error': 'You can only view receipts for your consultations'
                }, status=status.HTTP_403_FORBIDDEN)
            
            # Generate receipt data
            receipt_data = {
                'payment_id': payment.id,
                'receipt_number': payment.receipt_number or f"RCP{payment.id}",
                'patient_name': payment.patient.name,
                'doctor_name': payment.doctor.name if payment.doctor else 'N/A',
                'consultation_id': payment.consultation.id if payment.consultation else 'N/A',
                'amount': payment.amount,
                'currency': payment.currency,
                'payment_method': payment.payment_method,
                'status': payment.status,
                'description': payment.description,
                'created_at': payment.created_at,
                'completed_at': payment.completed_at,
                'gateway_transaction_id': payment.gateway_transaction_id,
                'clinic_name': payment.consultation.clinic.name if payment.consultation and payment.consultation.clinic else 'N/A'
            }
            
            return Response({
                'success': True,
                'data': receipt_data,
                'message': 'Payment receipt retrieved successfully',
                'timestamp': timezone.now().isoformat()
            }, status=status.HTTP_200_OK)
            
        except Payment.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Payment not found'
            }, status=status.HTTP_404_NOT_FOUND)


class PaymentHistoryView(APIView):
    """Get detailed payment history with filters"""
    permission_classes = [permissions.IsAuthenticated]
    
    @extend_schema(
        parameters=[
            OpenApiParameter(name='start_date', type=OpenApiTypes.DATE, description='Start date for filtering'),
            OpenApiParameter(name='end_date', type=OpenApiTypes.DATE, description='End date for filtering'),
            OpenApiParameter(name='status', type=OpenApiTypes.STR, description='Payment status filter'),
            OpenApiParameter(name='payment_method', type=OpenApiTypes.STR, description='Payment method filter'),
            OpenApiParameter(name='min_amount', type=OpenApiTypes.DECIMAL, description='Minimum amount filter'),
            OpenApiParameter(name='max_amount', type=OpenApiTypes.DECIMAL, description='Maximum amount filter'),
        ],
        responses={200: PaymentListSerializer},
        description="Get filtered payment history"
    )
    def get(self, request):
        """Get filtered payment history"""
        # Check permissions
        if request.user.role not in ['admin', 'superadmin']:
            return Response({
                'success': False,
                'error': 'Insufficient permissions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get filters from query params
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        status_filter = request.query_params.get('status')
        payment_method = request.query_params.get('payment_method')
        min_amount = request.query_params.get('min_amount')
        max_amount = request.query_params.get('max_amount')
        
        # Build queryset
        payments = Payment.objects.select_related('patient', 'doctor', 'consultation').all()
        
        # Filter by clinic if user is an admin (not superadmin)
        if request.user.role == 'admin':
            # Get clinics where this user is admin
            from eclinic.models import Clinic
            user_clinics = Clinic.objects.filter(admin=request.user)
            if user_clinics.exists():
                clinic_ids = [clinic.id for clinic in user_clinics]
                payments = payments.filter(consultation__clinic__id__in=clinic_ids)
        
        # Apply filters
        if start_date:
            payments = payments.filter(created_at__date__gte=start_date)
        if end_date:
            payments = payments.filter(created_at__date__lte=end_date)
        if status_filter:
            payments = payments.filter(status=status_filter)
        if payment_method:
            payments = payments.filter(payment_method=payment_method)
        if min_amount:
            payments = payments.filter(amount__gte=min_amount)
        if max_amount:
            payments = payments.filter(amount__lte=max_amount)
        
        # Pagination
        paginator = PaymentPagination()
        paginated_payments = paginator.paginate_queryset(payments, request)
        
        serializer = PaymentListSerializer(paginated_payments, many=True)
        
        # Return the data in the expected format
        return Response({
            'success': True,
            'data': {
                'count': paginator.page.paginator.count,
                'next': paginator.get_next_link(),
                'previous': paginator.get_previous_link(),
                'results': serializer.data
            },
            'message': 'Payment history retrieved successfully',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)


class PaymentAnalyticsView(APIView):
    """Advanced payment analytics and insights"""
    permission_classes = [permissions.IsAuthenticated]
    
    @extend_schema(
        responses={200: PaymentStatsSerializer},
        description="Get advanced payment analytics"
    )
    def get(self, request):
        """Get advanced payment analytics"""
        # Check permissions
        if request.user.role not in ['admin', 'superadmin']:
            return Response({
                'success': False,
                'error': 'Insufficient permissions'
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Get period from query params
        period = request.query_params.get('period', 'month')
        
        # Calculate period dates
        today = timezone.now().date()
        if period == 'week':
            start_date = today - timedelta(days=7)
        elif period == 'month':
            start_date = today - timedelta(days=30)
        elif period == 'quarter':
            start_date = today - timedelta(days=90)
        elif period == 'year':
            start_date = today - timedelta(days=365)
        else:
            start_date = today - timedelta(days=30)
        
        # Filter payments by period
        payments = Payment.objects.filter(created_at__date__gte=start_date)
        
        # Filter by clinic if user is an admin (not superadmin)
        if request.user.role == 'admin':
            # Get clinics where this user is admin
            from eclinic.models import Clinic
            user_clinics = Clinic.objects.filter(admin=request.user)
            if user_clinics.exists():
                clinic_ids = [clinic.id for clinic in user_clinics]
                payments = payments.filter(consultation__clinic__id__in=clinic_ids)
        
        # Revenue trends
        revenue_trends = []
        if period == 'week':
            for i in range(7):
                date = today - timedelta(days=i)
                revenue = payments.filter(
                    status='completed',
                    created_at__date=date
                ).aggregate(total=Sum('amount'))['total'] or 0
                revenue_trends.append({
                    'date': date.isoformat(),
                    'revenue': float(revenue)
                })
        else:
            # Monthly breakdown for longer periods
            current_date = start_date
            while current_date <= today:
                month_start = current_date.replace(day=1)
                month_end = (month_start + timedelta(days=32)).replace(day=1) - timedelta(days=1)
                
                revenue = payments.filter(
                    status='completed',
                    created_at__date__range=[month_start, month_end]
                ).aggregate(total=Sum('amount'))['total'] or 0
                
                revenue_trends.append({
                    'period': month_start.strftime('%Y-%m'),
                    'revenue': float(revenue)
                })
                
                current_date = (month_start + timedelta(days=32)).replace(day=1)
        
        # Payment method performance
        method_performance = list(
            payments.values('payment_method').annotate(
                total_amount=Sum('amount'),
                count=Count('id'),
                success_rate=Count('id', filter=Q(status='completed')) * 100.0 / Count('id')
            ).order_by('-total_amount')
        )
        
        # Top performing doctors
        top_doctors = list(
            payments.filter(
                status='completed',
                consultation__isnull=False
            ).values('consultation__doctor__name').annotate(
                total_revenue=Sum('amount'),
                consultation_count=Count('consultation', distinct=True),
                avg_amount=Avg('amount')
            ).order_by('-total_revenue')[:10]
        )
        
        # Payment failure analysis
        failure_analysis = list(
            payments.filter(status='failed').values('payment_method').annotate(
                failure_count=Count('id'),
                total_attempts=Count('id')
            ).order_by('-failure_count')
        )
        
        analytics_data = {
            'period': period,
            'revenue_trends': revenue_trends,
            'method_performance': method_performance,
            'top_doctors': top_doctors,
            'failure_analysis': failure_analysis,
            'summary': {
                'total_revenue': float(payments.filter(status='completed').aggregate(total=Sum('amount'))['total'] or 0),
                'total_transactions': payments.count(),
                'success_rate': (payments.filter(status='completed').count() / payments.count() * 100) if payments.count() > 0 else 0,
                'avg_transaction_value': float(payments.filter(status='completed').aggregate(avg=Avg('amount'))['avg'] or 0)
            }
        }
        
        return Response({
            'success': True,
            'data': analytics_data,
            'message': 'Payment analytics retrieved successfully',
            'timestamp': timezone.now().isoformat()
        }, status=status.HTTP_200_OK)



