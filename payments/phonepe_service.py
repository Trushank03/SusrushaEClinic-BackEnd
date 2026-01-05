"""
PhonePe Payment Gateway Integration Service
Handles payment initiation, status checking, and webhook processing
"""
import json
import hmac
import hashlib
import base64
import uuid
from decimal import Decimal
from django.conf import settings
import requests


class PhonePeService:
    """Service class for PhonePe payment gateway integration"""
    
    def __init__(self):
        """Initialize PhonePe service with credentials from settings"""
        self.environment = getattr(settings, 'PHONEPE_ENVIRONMENT', 'sandbox')
        
        if self.environment == 'production':
            self.merchant_id = getattr(settings, 'PHONEPE_PROD_MERCHANT_ID', '')
            self.salt_key = getattr(settings, 'PHONEPE_PROD_SALT_KEY', '')
            self.salt_index = getattr(settings, 'PHONEPE_PROD_SALT_INDEX', '1')
            self.base_url = getattr(settings, 'PHONEPE_PROD_PAY_URL', 'https://api.phonepe.com/apis/hermes/pg/v1/pay')
        else:
            self.merchant_id = getattr(settings, 'PHONEPE_MERCHANT_ID', 'PGTESTPAYUAT86')
            self.salt_key = getattr(settings, 'PHONEPE_SALT_KEY', '96434309-7796-489d-8924-ab56988a6076')
            self.salt_index = getattr(settings, 'PHONEPE_SALT_INDEX', '1')
            self.base_url = getattr(settings, 'PHONEPE_SANDBOX_PAY_URL', 'https://api-preprod.phonepe.com/apis/pg-sandbox/pg/v1/pay')
        
        self.callback_url = getattr(settings, 'PHONEPE_CALLBACK_URL', '')
        self.redirect_url = getattr(settings, 'PHONEPE_REDIRECT_URL', '')
    
    def _generate_x_verify_header(self, payload_string, endpoint):
        """
        Generate X-VERIFY header for PhonePe API requests
        Format: SHA256(payload_string + endpoint + salt_key)###salt_index
        """
        message = payload_string + endpoint + self.salt_key
        sha256_hash = hashlib.sha256(message.encode()).hexdigest()
        verify_string = f"{sha256_hash}###{self.salt_index}"
        return verify_string
    
    def _encode_base64(self, payload):
        """Encode payload to base64"""
        payload_string = json.dumps(payload, separators=(',', ':'))
        return base64.b64encode(payload_string.encode()).decode()
    
    def _decode_base64(self, encoded_string):
        """Decode base64 string to JSON"""
        decoded_bytes = base64.b64decode(encoded_string.encode())
        return json.loads(decoded_bytes.decode())
    
    def initiate_payment(self, payment_id, amount, customer_info, additional_info=None):
        """
        Initiate a payment with PhonePe
        
        Args:
            payment_id: Unique payment identifier (your internal payment ID)
            amount: Payment amount in paise (smallest currency unit, e.g., 10000 = ₹100.00)
            customer_info: Dictionary with customer details
                - mobile: Customer mobile number
                - email: Customer email (optional)
                - name: Customer name (optional)
            additional_info: Additional information dictionary (optional)
        
        Returns:
            Dictionary with payment URL and transaction ID
        """
        # Convert amount to paise (multiply by 100)
        amount_in_paise = int(float(amount) * 100)
        
        # Generate unique transaction ID
        transaction_id = f"TXN{payment_id}{uuid.uuid4().hex[:8].upper()}"
        
        # Prepare payload
        payload = {
            "merchantId": self.merchant_id,
            "merchantTransactionId": transaction_id,
            "merchantUserId": customer_info.get('mobile', ''),
            "amount": amount_in_paise,
            "redirectUrl": f"{self.redirect_url}?transaction_id={transaction_id}",
            "redirectMode": "REDIRECT",
            "callbackUrl": f"{self.callback_url}",
            "mobileNumber": customer_info.get('mobile', ''),
            "paymentInstrument": {
                "type": "PAY_PAGE"
            }
        }
        
        # Add customer details if available
        if customer_info.get('email'):
            payload['merchantUserId'] = customer_info['email']
        
        # Add additional info if provided
        if additional_info:
            payload['additionalInfo'] = additional_info
        
        # Encode payload
        encoded_payload = self._encode_base64(payload)
        
        # Generate X-VERIFY header
        endpoint = "/pg/v1/pay"
        x_verify = self._generate_x_verify_header(encoded_payload, endpoint)
        
        # Prepare request
        headers = {
            "Content-Type": "application/json",
            "X-VERIFY": x_verify,
            "Accept": "application/json"
        }
        
        request_payload = {
            "request": encoded_payload
        }
        
        try:
            # Make API call
            response = requests.post(
                self.base_url,
                json=request_payload,
                headers=headers,
                timeout=30
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Check if payment initiation was successful
            if response_data.get('success') and response_data.get('data'):
                payment_url = response_data['data'].get('instrumentResponse', {}).get('redirectInfo', {}).get('url')
                
                return {
                    'success': True,
                    'payment_url': payment_url,
                    'transaction_id': transaction_id,
                    'merchant_transaction_id': transaction_id,
                    'response': response_data
                }
            else:
                return {
                    'success': False,
                    'error': response_data.get('message', 'Payment initiation failed'),
                    'response': response_data
                }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}',
                'response': {}
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error initiating payment: {str(e)}',
                'response': {}
            }
    
    def check_payment_status(self, merchant_transaction_id):
        """
        Check payment status using PhonePe status API
        
        Args:
            merchant_transaction_id: The merchant transaction ID used during payment initiation
        
        Returns:
            Dictionary with payment status and details
        """
        # Build status check endpoint
        status_endpoint = "/pg/v1/status"
        if self.environment == 'production':
            status_url = "https://api.phonepe.com/apis/hermes/pg/v1/status"
        else:
            status_url = "https://api-preprod.phonepe.com/apis/pg-sandbox/pg/v1/status"
        
        # Prepare payload
        payload = {
            "merchantId": self.merchant_id,
            "merchantTransactionId": merchant_transaction_id
        }
        
        # Encode payload
        encoded_payload = self._encode_base64(payload)
        
        # Generate X-VERIFY header
        x_verify = self._generate_x_verify_header(encoded_payload, status_endpoint)
        
        # Prepare request
        headers = {
            "Content-Type": "application/json",
            "X-VERIFY": x_verify,
            "X-MERCHANT-ID": self.merchant_id,
            "Accept": "application/json"
        }
        
        request_payload = {
            "request": encoded_payload
        }
        
        try:
            # Make API call (PhonePe status API uses POST)
            response = requests.post(
                status_url,
                json=request_payload,
                headers=headers,
                timeout=30
            )
            
            response.raise_for_status()
            response_data = response.json()
            
            # Decode response if it contains encoded data
            if response_data.get('success') and response_data.get('data'):
                encoded_response = response_data['data'].get('response', '')
                if encoded_response:
                    decoded_response = self._decode_base64(encoded_response)
                    response_data['decoded_data'] = decoded_response
                    
                    # Extract payment status
                    code = decoded_response.get('code', '')
                    state = decoded_response.get('state', '')
                    transaction_id = decoded_response.get('transactionId', '')
                    
                    return {
                        'success': True,
                        'status': state,
                        'code': code,
                        'transaction_id': transaction_id,
                        'response': decoded_response,
                        'raw_response': response_data
                    }
            
            return {
                'success': False,
                'error': 'Unable to decode payment status',
                'response': response_data
            }
                
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}',
                'response': {}
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Error checking payment status: {str(e)}',
                'response': {}
            }
    
    def verify_webhook_signature(self, payload, x_verify_header):
        """
        Verify webhook signature from PhonePe
        
        Args:
            payload: Raw payload string from webhook
            x_verify_header: X-VERIFY header value from webhook
        
        Returns:
            Boolean indicating if signature is valid
        """
        try:
            # Extract hash and salt index from header
            # Format: hash###salt_index
            parts = x_verify_header.split('###')
            if len(parts) != 2:
                return False
            
            received_hash = parts[0]
            salt_index = parts[1]
            
            # Recalculate hash
            # PhonePe webhook: SHA256(payload + salt_key)###salt_index
            message = payload + self.salt_key
            calculated_hash = hashlib.sha256(message.encode()).hexdigest()
            
            # Compare hashes using constant-time comparison
            return hmac.compare_digest(calculated_hash, received_hash)
            
        except Exception:
            return False
    
    def process_webhook(self, webhook_data, x_verify_header):
        """
        Process PhonePe webhook callback
        
        Args:
            webhook_data: Webhook payload (may be base64 encoded)
            x_verify_header: X-VERIFY header for signature verification
        
        Returns:
            Dictionary with payment status and transaction details
        """
        try:
            # Verify signature if webhook data is string
            if isinstance(webhook_data, str):
                if not self.verify_webhook_signature(webhook_data, x_verify_header):
                    return {
                        'success': False,
                        'error': 'Invalid webhook signature',
                        'response': {}
                    }
                # Decode base64 if needed
                webhook_data = self._decode_base64(webhook_data)
            
            # Extract payment information
            transaction_id = webhook_data.get('transactionId', '')
            merchant_transaction_id = webhook_data.get('merchantTransactionId', '')
            state = webhook_data.get('state', '')
            code = webhook_data.get('code', '')
            response_code = webhook_data.get('responseCode', '')
            
            return {
                'success': True,
                'transaction_id': transaction_id,
                'merchant_transaction_id': merchant_transaction_id,
                'status': state,  # SUCCESS, PENDING, FAILURE
                'code': code,
                'response_code': response_code,
                'response': webhook_data
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Error processing webhook: {str(e)}',
                'response': {}
            }

