from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


class PatientProfile(models.Model):
    """Extended profile for patients"""
    
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='patient_profile'
    )
    
    # Medical Information
    BLOOD_GROUP_CHOICES = [
        ('A+', 'A+'), ('A-', 'A-'), ('B+', 'B+'), ('B-', 'B-'),
        ('AB+', 'AB+'), ('AB-', 'AB-'), ('O+', 'O+'), ('O-', 'O-')
    ]
    blood_group = models.CharField(max_length=5, choices=BLOOD_GROUP_CHOICES, blank=True)
    allergies = models.TextField(blank=True, help_text="Known allergies")
    chronic_conditions = models.JSONField(default=list, help_text="List of chronic conditions")
    current_medications = models.JSONField(default=list, help_text="List of current medications")
    
    # Insurance Information
    insurance_provider = models.CharField(max_length=100, blank=True)
    insurance_policy_number = models.CharField(max_length=50, blank=True)
    insurance_expiry = models.DateField(blank=True, null=True)
    
    # Preferences
    preferred_language = models.CharField(max_length=20, default='english')
    notification_preferences = models.JSONField(default=dict, help_text="SMS, Email, Push notification preferences")
    
    # Status
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'patient_profiles'
        verbose_name = 'Patient Profile'
        verbose_name_plural = 'Patient Profiles'
    
    def __str__(self):
        return f"Patient Profile - {self.user.name}"
    
    @property
    def total_consultations(self):
        """Get total number of consultations"""
        return self.user.patient_consultations.count()
    
    @property
    def last_consultation_date(self):
        """Get last consultation date"""
        last_consultation = self.user.patient_consultations.order_by('-created_at').first()
        return last_consultation.created_at.date() if last_consultation else None

    @property
    def age(self):
        """Calculate age from user's date of birth"""
        if self.user.date_of_birth:
            today = timezone.now().date()
            return today.year - self.user.date_of_birth.year - ((today.month, today.day) < (self.user.date_of_birth.month, self.user.date_of_birth.day))
        return None


class MedicalRecord(models.Model):
    """Medical records for patients"""
    
    RECORD_TYPES = [
        ('lab_report', 'Lab Report'),
        ('prescription', 'Prescription'),
        ('diagnosis', 'Diagnosis'),
        ('vaccination', 'Vaccination'),
        ('surgery', 'Surgery'),
        ('allergy', 'Allergy'),
        ('other', 'Other'),
    ]
    
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='medical_records'
    )
    record_type = models.CharField(max_length=20, choices=RECORD_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default='')
    date_recorded = models.DateField()
    
    # File attachments
    document = models.FileField(upload_to='medical_records/', blank=True, null=True)
    
    # Doctor who recorded this
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='recorded_medical_records'
    )
    
    # Metadata
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'medical_records'
        verbose_name = 'Medical Record'
        verbose_name_plural = 'Medical Records'
        ordering = ['-date_recorded']
    
    def __str__(self):
        return f"{self.title} - {self.patient.name}"


class PatientDocument(models.Model):
    """Documents uploaded by or for patients"""
    
    DOCUMENT_TYPES = [
        ('id_proof', 'ID Proof'),
        ('address_proof', 'Address Proof'),
        ('insurance_card', 'Insurance Card'),
        ('medical_report', 'Medical Report'),
        ('prescription', 'Prescription'),
        ('lab_report', 'Lab Report'),
        ('other', 'Other'),
    ]
    
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='documents'
    )
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES)
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    file = models.FileField(upload_to='patient_documents/')
    
    # Verification status
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='verified_documents'
    )
    verified_at = models.DateTimeField(blank=True, null=True)
    
    # Metadata
    uploaded_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'patient_documents'
        verbose_name = 'Patient Document'
        verbose_name_plural = 'Patient Documents'
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.title} - {self.patient.name}"


class PatientNote(models.Model):
    """Notes about patients (for internal use by doctors/staff)"""
    
    patient = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='patient_notes'
    )
    note = models.TextField()
    is_private = models.BooleanField(default=True, help_text="Private notes are only visible to doctors")
    
    # Author
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name='created_patient_notes'
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'patient_notes'
        verbose_name = 'Patient Note'
        verbose_name_plural = 'Patient Notes'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Note for {self.patient.name} by {self.created_by.name}"


class PatientAccessLog(models.Model):
    """Audit log for admin access to patient medical records"""
    
    ACCESS_TYPES = [
        ('medical_records', 'Medical Records'),
        ('documents', 'Documents'),
        ('notes', 'Notes'),
        ('profile', 'Profile'),
        ('prescriptions', 'Prescriptions'),
    ]
    
    patient = models.ForeignKey(
        'PatientProfile',
        on_delete=models.CASCADE,
        related_name='access_logs'
    )
    admin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='patient_access_logs'
    )
    access_type = models.CharField(max_length=20, choices=ACCESS_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    user_agent = models.CharField(max_length=255, blank=True)
    
    # Additional context
    session_duration = models.IntegerField(blank=True, null=True, help_text="Session duration in seconds")
    records_accessed = models.IntegerField(default=0, help_text="Number of records accessed")
    
    class Meta:
        db_table = 'patient_access_logs'
        verbose_name = 'Patient Access Log'
        verbose_name_plural = 'Patient Access Logs'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['patient', 'timestamp']),
            models.Index(fields=['admin', 'timestamp']),
            models.Index(fields=['access_type', 'timestamp']),
        ]
    
    def __str__(self):
        return f"{self.admin.name} accessed {self.patient.user.name}'s {self.access_type} at {self.timestamp}"
    
    @property
    def is_recent(self):
        """Check if access was within last 24 hours"""
        return self.timestamp > timezone.now() - timedelta(hours=24)

