from rest_framework import serializers
from django.utils import timezone
from authentication.models import User
from .models import PatientProfile, MedicalRecord, PatientDocument, PatientNote


class PatientProfileSerializer(serializers.ModelSerializer):
    """Serializer for patient profile"""
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    date_of_birth = serializers.DateField(source='user.date_of_birth', read_only=True)
    gender = serializers.CharField(source='user.gender', read_only=True)
    age = serializers.ReadOnlyField()
    medical_history = serializers.CharField(source='user.medical_history', read_only=True)
    street = serializers.CharField(source='user.street', read_only=True)
    city = serializers.CharField(source='user.city', read_only=True)
    state = serializers.CharField(source='user.state', read_only=True)
    pincode = serializers.CharField(source='user.pincode', read_only=True)
    country = serializers.CharField(source='user.country', read_only=True)
    emergency_contact_name = serializers.CharField(source='user.emergency_contact_name', read_only=True)
    emergency_contact_phone = serializers.CharField(source='user.emergency_contact_phone', read_only=True)
    emergency_contact_relationship = serializers.CharField(source='user.emergency_contact_relationship', read_only=True)
    
    class Meta:
        model = PatientProfile
        fields = [
            'id', 'user', 'user_name', 'user_phone', 'user_email',
            'date_of_birth', 'gender', 'blood_group',
            'allergies', 'chronic_conditions', 'current_medications',
            'insurance_provider', 'insurance_policy_number', 'insurance_expiry',
            'preferred_language', 'medical_history',
            'street', 'city', 'state', 'pincode', 'country',
            'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship',
            'created_at', 'updated_at', 'age'
        ]
        read_only_fields = ['id', 'user', 'created_at', 'updated_at']


class PatientProfileCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating patient profile"""
    
    class Meta:
        model = PatientProfile
        fields = [
            'blood_group',
            'allergies', 'chronic_conditions', 'current_medications',
            'insurance_provider', 'insurance_policy_number', 'insurance_expiry',
            'preferred_language'
        ]
    
    def create(self, validated_data):
        """Create patient profile for authenticated user"""
        user = self.context['request'].user
        validated_data['user'] = user
        return super().create(validated_data)


class MedicalRecordSerializer(serializers.ModelSerializer):
    """Serializer for medical records"""
    recorded_by_name = serializers.CharField(source='recorded_by.name', read_only=True)
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    document_url = serializers.SerializerMethodField()
    
    class Meta:
        model = MedicalRecord
        fields = [
            'id', 'patient', 'patient_name', 'record_type',
            'title', 'description', 'date_recorded', 'document', 'document_url',
            'recorded_by', 'recorded_by_name', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'patient', 'recorded_by', 'created_at', 'updated_at']
    
    def get_document_url(self, obj):
        """Get signed URL for document if it exists"""
        if obj.document:
            try:
                from utils.signed_urls import get_signed_media_url
                return get_signed_media_url(obj.document.name)
            except Exception:
                return obj.document.url if hasattr(obj.document, 'url') else None
        return None


class MedicalRecordCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating medical records"""
    
    class Meta:
        model = MedicalRecord
        fields = [
            'record_type', 'title', 'description', 'date_recorded', 'document'
        ]
    
    def validate_document(self, value):
        """Validate uploaded document"""
        if value:
            # Check file size (max 10MB)
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError("File size must be less than 10MB")
            
            # Check file type
            allowed_types = [
                'image/jpeg', 'image/jpg', 'image/png', 'image/gif',
                'application/pdf', 'application/msword', 
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'text/plain'
            ]
            if value.content_type not in allowed_types:
                raise serializers.ValidationError(
                    "Only JPEG, PNG, GIF, PDF, DOC, DOCX, and TXT files are allowed"
                )
        
        return value
    
    def create(self, validated_data):
        """Create medical record for patient"""
        patient_id = self.context['view'].kwargs.get('patient_id')
        doctor = self.context['request'].user
        
        validated_data['patient_id'] = patient_id
        validated_data['recorded_by'] = doctor
        return super().create(validated_data)


class PatientDocumentSerializer(serializers.ModelSerializer):
    """Serializer for patient documents"""
    verified_by_name = serializers.CharField(source='verified_by.name', read_only=True)
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = PatientDocument
        fields = [
            'id', 'patient', 'patient_name', 'document_type', 'title', 'description',
            'file', 'file_url',
            'is_verified', 'verified_by', 'verified_by_name', 'verified_at',
            'uploaded_at', 'updated_at'
        ]
        read_only_fields = ['id', 'patient', 'verified_by', 'verified_at', 'uploaded_at', 'updated_at']
    
    def get_file_url(self, obj):
        """Get signed URL for file if it exists"""
        if obj.file:
            try:
                from utils.signed_urls import get_signed_media_url
                return get_signed_media_url(obj.file.name)
            except Exception:
                return obj.file.url if hasattr(obj.file, 'url') else None
        return None


class PatientDocumentUploadSerializer(serializers.ModelSerializer):
    """Serializer for uploading patient documents"""
    
    class Meta:
        model = PatientDocument
        fields = [
            'document_type', 'title', 'description', 'file'
        ]
    
    def validate_file(self, value):
        """Validate uploaded file"""
        if value:
            # Check file size (max 10MB)
            if value.size > 10 * 1024 * 1024:
                raise serializers.ValidationError("File size must be less than 10MB")
            
            # Check file type
            allowed_types = [
                'image/jpeg', 'image/jpg', 'image/png', 'image/gif',
                'application/pdf', 'application/msword', 
                'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'text/plain'
            ]
            if value.content_type not in allowed_types:
                raise serializers.ValidationError(
                    "Only JPEG, PNG, GIF, PDF, DOC, DOCX, and TXT files are allowed"
                )
        
        return value
    
    def create(self, validated_data):
        """Create patient document"""
        patient_id = self.context['view'].kwargs.get('patient_id')
        
        validated_data['patient_id'] = patient_id
        
        return super().create(validated_data)


class PatientNoteSerializer(serializers.ModelSerializer):
    """Serializer for patient notes"""
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    
    class Meta:
        model = PatientNote
        fields = [
            'id', 'patient', 'note',
            'is_private', 'created_by', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_by', 'created_at', 'updated_at']


class PatientNoteCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating patient notes"""
    
    class Meta:
        model = PatientNote
        fields = ['note', 'is_private']
    
    def create(self, validated_data):
        """Create patient note"""
        patient_id = self.context['view'].kwargs.get('patient_id')
        created_by = self.context['request'].user
        
        validated_data['patient_id'] = patient_id
        validated_data['created_by'] = created_by
        return super().create(validated_data)


class PatientListSerializer(serializers.ModelSerializer):
    """Serializer for patient list view"""
    user_name = serializers.CharField(source='user.name', read_only=True)
    user_phone = serializers.CharField(source='user.phone', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)
    date_of_birth = serializers.DateField(source='user.date_of_birth', read_only=True)
    gender = serializers.CharField(source='user.gender', read_only=True)
    age = serializers.ReadOnlyField()
    total_consultations = serializers.SerializerMethodField()
    last_consultation_date = serializers.SerializerMethodField()
    street = serializers.CharField(source='user.street', read_only=True)
    city = serializers.CharField(source='user.city', read_only=True)
    state = serializers.CharField(source='user.state', read_only=True)
    pincode = serializers.CharField(source='user.pincode', read_only=True)
    country = serializers.CharField(source='user.country', read_only=True)
    emergency_contact_name = serializers.CharField(source='user.emergency_contact_name', read_only=True)
    emergency_contact_phone = serializers.CharField(source='user.emergency_contact_phone', read_only=True)
    emergency_contact_relationship = serializers.CharField(source='user.emergency_contact_relationship', read_only=True)
    medical_history = serializers.CharField(source='user.medical_history', read_only=True)
    
    class Meta:
        model = PatientProfile
        fields = [
            'id', 'user', 'user_name', 'user_phone', 'user_email',
            'date_of_birth', 'gender', 'blood_group',
            'allergies', 'chronic_conditions', 'current_medications',
            'preferred_language', 'is_active',
            'street', 'city', 'state', 'pincode', 'country',
            'emergency_contact_name', 'emergency_contact_phone', 'emergency_contact_relationship',
            'medical_history',
            'created_at', 'updated_at', 'age',
            'total_consultations', 'last_consultation_date'
        ]
    
    def get_total_consultations(self, obj):
        """Get total number of consultations"""
        return obj.user.patient_consultations.count()
    
    def get_last_consultation_date(self, obj):
        """Get last consultation date"""
        last_consultation = obj.user.patient_consultations.order_by('-created_at').first()
        if last_consultation:
            return last_consultation.created_at
        return None


class PatientSearchSerializer(serializers.Serializer):
    """Serializer for patient search"""
    query = serializers.CharField(max_length=200, required=False)
    gender = serializers.ChoiceField(
        choices=[('male', 'Male'), ('female', 'Female'), ('other', 'Other')],
        required=False
    )
    blood_group = serializers.ChoiceField(
        choices=[
            ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
            ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-')
        ],
        required=False
    )
    age_min = serializers.IntegerField(min_value=0, max_value=150, required=False)
    age_max = serializers.IntegerField(min_value=0, max_value=150, required=False)
    city = serializers.CharField(max_length=100, required=False)
    state = serializers.CharField(max_length=100, required=False)
    
    def validate(self, attrs):
        """Validate search parameters"""
        min_age = attrs.get('age_min')
        max_age = attrs.get('age_max')
        if min_age and max_age and min_age > max_age:
            raise serializers.ValidationError('age_min cannot be greater than age_max')
        return attrs


class PatientStatsSerializer(serializers.Serializer):
    """Serializer for patient statistics"""
    total_patients = serializers.IntegerField()
    new_patients_this_month = serializers.IntegerField()
    active_patients = serializers.IntegerField()
    gender_distribution = serializers.DictField()
    age_distribution = serializers.DictField()
    blood_group_distribution = serializers.DictField()
    top_cities = serializers.ListField()
    consultation_stats = serializers.DictField()

