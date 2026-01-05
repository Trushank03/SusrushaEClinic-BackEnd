from rest_framework import serializers
from django.utils import timezone
from django.db import models
from django.core.exceptions import ValidationError
from authentication.models import User
from .models import (
    Clinic, ClinicService, ClinicInventory, ClinicReview, 
    ClinicAppointment, ClinicDocument, GlobalMedication
)
from utils.signed_urls import get_signed_media_url


class FlexibleImageField(serializers.ImageField):
    """Accepts either a file upload or a URL string.
    - If a URL string is provided, the field is omitted from update so existing image is preserved.
    - If a file is provided, it is validated and saved as usual.
    """

    def get_value(self, dictionary):
        value = super().get_value(dictionary)
        # If the incoming value is a non-empty string (URL), skip updating this field
        if isinstance(value, str) and value.strip():
            return serializers.empty
        return value

    def to_internal_value(self, data):
        # If it's a string URL, return None so validators are skipped and field can be omitted later
        if isinstance(data, str):
            return None
        return super().to_internal_value(data)

    def run_validators(self, value):
        # Skip validation when value is None (URL case)
        if value is None:
            return
        super().run_validators(value)


def validate_image_file(value):
    """Custom validator for image files"""
    # Check file size (20MB = 20 * 1024 * 1024 bytes)
    max_size = 20 * 1024 * 1024  # 20MB
    if value.size > max_size:
        raise ValidationError(f'Image file size must be no more than 20MB. Current size: {value.size / (1024 * 1024):.2f}MB')
    
    # Check file type
    allowed_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp']
    if hasattr(value, 'content_type') and value.content_type not in allowed_types:
        raise ValidationError('Only JPEG, PNG, and WebP image files are allowed.')
    
    return value


class ClinicSerializer(serializers.ModelSerializer):
    admin = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role='admin'), required=True)
    admin_name = serializers.CharField(source='admin.name', read_only=True)
    admin_phone = serializers.CharField(source='admin.phone', read_only=True)
    cover_image = serializers.SerializerMethodField()

    class Meta:
        model = Clinic
        fields = [
            'id', 'name', 'clinic_type', 'description',
            'phone', 'email', 'website',
            'street', 'city', 'state', 'pincode', 'country',
            'latitude', 'longitude', 'operating_hours',
            'specialties', 'services', 'facilities',
            'registration_number', 'license_number', 'accreditation',
            'cover_image', 'gallery_images',
            'is_active', 'is_verified', 'accepts_online_consultations',
            'consultation_duration', 'admin', 'admin_name', 'admin_phone', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_verified']

    def validate_admin(self, value):
        # Only superadmin can change admin
        request = self.context.get('request')
        if request and request.method in ['PUT', 'PATCH']:
            user = request.user
            if not hasattr(user, 'role') or user.role != 'superadmin':
                raise serializers.ValidationError('Only superadmin can change the admin of a clinic.')
        # Check if this admin is already assigned to another clinic (exclude current clinic)
        clinic_id = self.instance.id if self.instance else None
        if Clinic.objects.filter(admin=value).exclude(id=clinic_id).exists():
            raise serializers.ValidationError('This admin is already assigned to another clinic.')
        return value
    
    def get_cover_image(self, obj):
        """Generate signed URL for cover image"""
        if obj.cover_image:
            return get_signed_media_url(str(obj.cover_image))
        return None

class ClinicCreateSerializer(serializers.ModelSerializer):
    admin = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role='admin'), required=True)
    cover_image = FlexibleImageField(validators=[validate_image_file], required=False, allow_null=True)

    class Meta:
        model = Clinic
        fields = [
            'name', 'clinic_type', 'description',
            'phone', 'email', 'website',
            'street', 'city', 'state', 'pincode', 'country',
            'latitude', 'longitude', 'operating_hours',
            'specialties', 'services', 'facilities',
            'registration_number', 'license_number', 'accreditation',
            'cover_image', 'gallery_images',
            'is_active', 'accepts_online_consultations',
            'consultation_duration', 'admin',
        ]

    def to_internal_value(self, data):
        """Convert string boolean values to actual booleans"""
        # Handle FormData boolean conversion
        if hasattr(data, '_mutable') and not data._mutable:
            # Make a mutable copy if it's an immutable QueryDict
            data = data.copy()
        
        if isinstance(data, dict):
            for key in ['is_active', 'accepts_online_consultations']:
                if key in data and isinstance(data[key], str):
                    data[key] = data[key].lower() in ['true', '1', 'yes', 'on']
        
        return super().to_internal_value(data)

    def create(self, validated_data):
        validated_data['is_verified'] = True
        return super().create(validated_data)

    def validate_admin(self, value):
        # Check if this admin is already assigned to a clinic
        # For updates, exclude the current clinic from the check
        queryset = Clinic.objects.filter(admin=value)
        
        # If this is an update operation, exclude the current instance
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        
        if queryset.exists():
            raise serializers.ValidationError("This admin is already assigned to another clinic.")
        return value

    def update(self, instance, validated_data):
        # If cover_image resolved to None (URL string case), don't touch existing image
        if 'cover_image' in validated_data and validated_data['cover_image'] is None:
            validated_data.pop('cover_image')
        return super().update(instance, validated_data)


class ClinicServiceSerializer(serializers.ModelSerializer):
    """Serializer for clinic service"""
    clinic_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicService
        fields = [
            'id', 'clinic', 'clinic_name', 'name', 'category', 'description',
            'base_price', 'price_range_min', 'price_range_max', 'is_available',
            'requires_appointment', 'estimated_duration', 'preparation_required',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_clinic_name(self, obj):
        """Get clinic name, return 'N/A' if no clinic assigned"""
        return obj.clinic.name if obj.clinic else 'N/A'


class ClinicServiceCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating clinic service"""
    
    class Meta:
        model = ClinicService
        fields = [
            'name', 'category', 'description', 'base_price', 'price_range_min',
            'price_range_max', 'is_available', 'requires_appointment',
            'estimated_duration', 'preparation_required'
        ]
    
    def create(self, validated_data):
        """Create clinic service"""
        clinic_id = self.context['view'].kwargs.get('clinic_id')
        validated_data['clinic_id'] = clinic_id
        return super().create(validated_data)


class GlobalMedicationSerializer(serializers.ModelSerializer):
    """Serializer for global medications"""
    
    created_by_name = serializers.CharField(source='created_by.name', read_only=True)
    dosage_form_display = serializers.CharField(source='get_dosage_form_display', read_only=True)
    medication_type_display = serializers.CharField(source='get_medication_type_display', read_only=True)
    
    class Meta:
        model = GlobalMedication
        fields = [
            'id', 'name', 'generic_name', 'brand_name', 'composition',
            'dosage_form', 'dosage_form_display', 'strength', 'medication_type', 'medication_type_display',
            'therapeutic_class', 'indication', 'contraindications', 'side_effects',
            'dosage_instructions', 'frequency_options', 'timing_options',
            'manufacturer', 'license_number', 'is_prescription_required',
            'is_active', 'is_verified', 'created_by_name',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'created_by_name']


class GlobalMedicationCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating global medications"""
    
    class Meta:
        model = GlobalMedication
        fields = [
            'name', 'generic_name', 'brand_name', 'composition',
            'dosage_form', 'strength', 'medication_type',
            'therapeutic_class', 'indication', 'contraindications', 'side_effects',
            'dosage_instructions', 'frequency_options', 'timing_options',
            'manufacturer', 'license_number', 'is_prescription_required',
            'is_active', 'is_verified'
        ]
    
    def validate_name(self, value):
        """Check if medication name already exists"""
        if GlobalMedication.objects.filter(name__iexact=value).exists():
            raise serializers.ValidationError("A medication with this name already exists.")
        return value
    
    def create(self, validated_data):
        """Create medication with current user as creator"""
        validated_data['created_by'] = self.context['request'].user
        return super().create(validated_data)


class GlobalMedicationSearchSerializer(serializers.ModelSerializer):
    """Serializer for medication search results"""
    
    dosage_form_display = serializers.CharField(source='get_dosage_form_display', read_only=True)
    medication_type_display = serializers.CharField(source='get_medication_type_display', read_only=True)
    
    class Meta:
        model = GlobalMedication
        fields = [
            'id', 'name', 'generic_name', 'brand_name', 'composition',
            'dosage_form', 'dosage_form_display', 'strength', 'medication_type', 'medication_type_display',
            'therapeutic_class', 'indication', 'manufacturer', 'is_prescription_required',
            'frequency_options', 'timing_options'
        ]


class ClinicInventorySerializer(serializers.ModelSerializer):
    """Serializer for clinic inventory"""
    
    clinic_name = serializers.SerializerMethodField()
    global_medication_details = GlobalMedicationSerializer(source='global_medication', read_only=True)
    
    class Meta:
        model = ClinicInventory
        fields = [
            'id', 'clinic', 'clinic_name', 'global_medication', 'global_medication_details',
            'item_name', 'category', 'description', 'brand', 'model_number',
            'current_stock', 'minimum_stock', 'maximum_stock', 'unit',
            'unit_cost', 'selling_price', 'batch_number', 'expiry_date',
            'supplier_name', 'supplier_contact', 'is_active',
            'is_low_stock', 'is_expired', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'clinic_name', 'global_medication_details']
    
    def get_clinic_name(self, obj):
        """Get clinic name, return 'N/A' if no clinic assigned"""
        return obj.clinic.name if obj.clinic else 'N/A'


class ClinicInventoryCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating clinic inventory items"""
    
    class Meta:
        model = ClinicInventory
        fields = [
            'global_medication', 'item_name', 'category', 'description', 'brand', 'model_number',
            'current_stock', 'minimum_stock', 'maximum_stock', 'unit',
            'unit_cost', 'selling_price', 'batch_number', 'expiry_date',
            'supplier_name', 'supplier_contact', 'is_active'
        ]
    
    def validate(self, data):
        """Validate inventory data"""
        # If global_medication is provided, ensure category is medicine
        if data.get('global_medication') and data.get('category') != 'medicine':
            raise serializers.ValidationError("Global medication can only be linked to medicine category.")
        
        # If category is medicine but no global_medication, ensure item_name is provided
        if data.get('category') == 'medicine' and not data.get('global_medication') and not data.get('item_name'):
            raise serializers.ValidationError("Medicine name is required when not linking to global medication.")
        
        return data


class ClinicAppointmentSerializer(serializers.ModelSerializer):
    """Serializer for clinic appointment"""
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    doctor_name = serializers.CharField(source='doctor.name', read_only=True)
    clinic_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicAppointment
        fields = [
            'id', 'clinic', 'patient', 'doctor', 'clinic_name',
            'patient_name', 'doctor_name', 'appointment_date',
            'appointment_time', 'status', 'reason', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_clinic_name(self, obj):
        """Get clinic name, return 'N/A' if no clinic assigned"""
        return obj.clinic.name if obj.clinic else 'N/A'


class ClinicAppointmentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating clinic appointment"""
    
    class Meta:
        model = ClinicAppointment
        fields = [
            'doctor', 'appointment_date', 'appointment_time', 'reason'
        ]
    
    def create(self, validated_data):
        """Create clinic appointment"""
        clinic_id = self.context['view'].kwargs.get('clinic_id')
        patient = self.context['request'].user
        
        validated_data['clinic_id'] = clinic_id
        validated_data['patient'] = patient
        validated_data['status'] = 'scheduled'
        
        return super().create(validated_data)


class ClinicReviewSerializer(serializers.ModelSerializer):
    """Serializer for clinic review"""
    patient_name = serializers.CharField(source='patient.name', read_only=True)
    clinic_name = serializers.SerializerMethodField()
    
    class Meta:
        model = ClinicReview
        fields = [
            'id', 'clinic', 'patient', 'clinic_name', 'patient_name',
            'overall_rating', 'cleanliness_rating', 'staff_rating',
            'facilities_rating', 'wait_time_rating', 'review_text', 
            'is_anonymous', 'is_approved', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'patient', 'created_at', 'updated_at']
    
    def get_clinic_name(self, obj):
        """Get clinic name, return 'N/A' if no clinic assigned"""
        return obj.clinic.name if obj.clinic else 'N/A'


class ClinicReviewCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating clinic review"""
    
    class Meta:
        model = ClinicReview
        fields = [
            'overall_rating', 'cleanliness_rating', 'staff_rating',
            'facilities_rating', 'wait_time_rating', 'review_text', 'is_anonymous'
        ]
    
    def create(self, validated_data):
        """Create clinic review"""
        clinic_id = self.context['view'].kwargs.get('clinic_id')
        patient = self.context['request'].user
        
        validated_data['clinic_id'] = clinic_id
        validated_data['patient'] = patient
        validated_data['is_approved'] = True
        
        return super().create(validated_data)


class ClinicDocumentSerializer(serializers.ModelSerializer):
    """Serializer for clinic document"""
    clinic_name = serializers.SerializerMethodField()
    uploaded_by_name = serializers.CharField(source='uploaded_by.name', read_only=True)
    
    class Meta:
        model = ClinicDocument
        fields = [
            'id', 'clinic', 'clinic_name', 'document_type', 'title',
            'description', 'file', 'uploaded_by', 'uploaded_by_name',
            'uploaded_at', 'updated_at'
        ]
        read_only_fields = ['id', 'uploaded_by', 'uploaded_at', 'updated_at']
    
    def get_clinic_name(self, obj):
        """Get clinic name, return 'N/A' if no clinic assigned"""
        return obj.clinic.name if obj.clinic else 'N/A'


class ClinicDocumentCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating clinic document"""
    
    class Meta:
        model = ClinicDocument
        fields = ['document_type', 'title', 'description', 'file']
    
    def create(self, validated_data):
        """Create clinic document"""
        clinic_id = self.context['view'].kwargs.get('clinic_id')
        uploaded_by = self.context['request'].user
        
        validated_data['clinic_id'] = clinic_id
        validated_data['uploaded_by'] = uploaded_by
        
        return super().create(validated_data)


class ClinicListSerializer(serializers.ModelSerializer):
    """Serializer for clinic list view"""
    admin_name = serializers.CharField(source='admin.name', read_only=True)
    total_doctors = serializers.SerializerMethodField()
    average_rating = serializers.SerializerMethodField()
    
    class Meta:
        model = Clinic
        fields = [
            'id', 'name', 'clinic_type', 'description', 'admin_name',
            'phone', 'email', 'street', 'city', 'state', 'country',
            'total_doctors', 'average_rating', 'is_verified', 'is_active',
            'accepts_online_consultations', 'consultation_duration', 'created_at'
        ]
        read_only_fields = ['id', 'total_doctors', 'average_rating', 'created_at']
    
    def get_total_doctors(self, obj):
        """Get total number of doctors in clinic"""
        return obj.doctors.filter(is_active=True).count()
    
    def get_average_rating(self, obj):
        """Get average rating of clinic"""
        reviews = obj.reviews.filter(is_approved=True)
        if reviews.exists():
            return round(reviews.aggregate(avg=models.Avg('overall_rating'))['avg'], 2)
        return 0


class ClinicSearchSerializer(serializers.Serializer):
    """Serializer for clinic search"""
    query = serializers.CharField(max_length=200, required=False)
    city = serializers.CharField(max_length=100, required=False)
    state = serializers.CharField(max_length=100, required=False)
    specialization = serializers.CharField(max_length=100, required=False)
    service = serializers.CharField(max_length=100, required=False)
    is_verified = serializers.BooleanField(required=False)
    latitude = serializers.FloatField(required=False)
    longitude = serializers.FloatField(required=False)
    radius_km = serializers.FloatField(required=False, default=10)
    
    def validate(self, attrs):
        """Validate search parameters"""
        latitude = attrs.get('latitude')
        longitude = attrs.get('longitude')
        
        if (latitude is not None and longitude is None) or (latitude is None and longitude is not None):
            raise serializers.ValidationError('Both latitude and longitude must be provided for location-based search')
        
        return attrs


class ClinicStatsSerializer(serializers.Serializer):
    """Serializer for clinic statistics"""
    total_clinics = serializers.IntegerField()
    verified_clinics = serializers.IntegerField()
    active_clinics = serializers.IntegerField()
    total_appointments = serializers.IntegerField()
    total_doctors = serializers.IntegerField()
    total_services = serializers.IntegerField()
    city_distribution = serializers.DictField()
    specialization_distribution = serializers.DictField()
    monthly_registrations = serializers.ListField()
    average_rating = serializers.FloatField()

