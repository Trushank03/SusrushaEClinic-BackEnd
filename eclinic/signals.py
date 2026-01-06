"""
Signals for automatic file upload to DigitalOcean Spaces
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from .models import Clinic
import threading
import boto3
import os

def upload_files_async(clinic_id):
    """
    Asynchronous function to upload files to DigitalOcean Spaces
    """
    try:
        from eclinic.models import Clinic
        
        # Get the clinic
        clinic = Clinic.objects.get(id=clinic_id)
        
        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        # Upload cover image if it exists
        if clinic.cover_image and hasattr(clinic.cover_image, 'path'):
            local_path = clinic.cover_image.path
            if os.path.exists(local_path):
                remote_key = f"{settings.AWS_LOCATION}/{clinic.cover_image.name}"
                try:
                    s3_client.upload_file(local_path, settings.AWS_STORAGE_BUCKET_NAME, remote_key)
                    # Make file public
                    s3_client.put_object_acl(
                        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                        Key=remote_key,
                        ACL='public-read'
                    )
                    print(f"✅ [ASYNC] Uploaded cover image to DigitalOcean Spaces: {remote_key}")
                except Exception as e:
                    print(f"❌ [ASYNC] Error uploading cover image: {e}")
                    
    except Exception as e:
        print(f"❌ [ASYNC] Error in upload_files_async: {e}")

@receiver(post_save, sender=Clinic)
def upload_clinic_files_to_spaces(sender, instance, created, **kwargs):
    """
    Automatically upload clinic files to DigitalOcean Spaces after saving
    """
    if not settings.ALWAYS_UPLOAD_FILES_TO_AWS:
        return
    
    try:
        # For immediate access, upload synchronously first, then start async thread for any retries
        upload_files_sync(instance.id)
        
        # Also start async thread for any additional processing
        thread = threading.Thread(target=upload_files_async, args=(instance.id,))
        thread.daemon = True  # Thread will be killed when main process exits
        thread.start()
        print(f"🚀 [SIGNAL] Started async upload thread for clinic {instance.id}")
                    
    except Exception as e:
        print(f"❌ Error in upload_clinic_files_to_spaces signal: {e}")

def upload_files_sync(clinic_id):
    """
    Synchronous function to upload files to DigitalOcean Spaces immediately
    """
    try:
        from eclinic.models import Clinic
        
        # Get the clinic
        clinic = Clinic.objects.get(id=clinic_id)
        
        # Initialize S3 client
        s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            endpoint_url=settings.AWS_S3_ENDPOINT_URL,
            region_name=settings.AWS_S3_REGION_NAME
        )
        
        # Upload cover image if it exists
        if clinic.cover_image and hasattr(clinic.cover_image, 'path'):
            local_path = clinic.cover_image.path
            if os.path.exists(local_path):
                remote_key = f"{settings.AWS_LOCATION}/{clinic.cover_image.name}"
                try:
                    s3_client.upload_file(local_path, settings.AWS_STORAGE_BUCKET_NAME, remote_key)
                    # Make file public
                    s3_client.put_object_acl(
                        Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                        Key=remote_key,
                        ACL='public-read'
                    )
                    print(f"✅ [SYNC] Uploaded cover image to DigitalOcean Spaces: {remote_key}")
                except Exception as e:
                    print(f"❌ [SYNC] Error uploading cover image: {e}")
                    
    except Exception as e:
        print(f"❌ [SYNC] Error in upload_files_sync: {e}") 

# Signal to auto-assign patient to clinic when consultation is created
from consultations.models import Consultation
from .models import ClinicPatient

@receiver(post_save, sender=Consultation)
def auto_assign_patient_to_clinic(sender, instance, created, **kwargs):
    """
    Automatically assign patient to clinic when a consultation is created.
    This ensures patients who book consultations are registered to the clinic.
    """
    if created and instance.clinic and instance.patient:
        try:
            # Check if patient is already registered to this clinic
            existing = ClinicPatient.objects.filter(
                clinic=instance.clinic,
                patient=instance.patient
            ).exists()
            
            if not existing:
                ClinicPatient.objects.create(
                    clinic=instance.clinic,
                    patient=instance.patient,
                    registration_source='consultation',
                    registered_by=None,  # Auto-registered via consultation
                    is_active=True
                )
                print(f"✅ Auto-registered patient {instance.patient.id} to clinic {instance.clinic.id} via consultation")
        except Exception as e:
            print(f"❌ Error auto-registering patient to clinic: {e}")
