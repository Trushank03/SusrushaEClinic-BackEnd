"""
Management command to migrate existing patients to clinics based on their consultation history.
This is a one-time migration script to populate the ClinicPatient table.
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Count

from authentication.models import User
from eclinic.models import Clinic, ClinicPatient
from consultations.models import Consultation


class Command(BaseCommand):
    help = 'Migrate existing patients to clinics based on their consultation history'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be migrated without actually doing it',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        self.stdout.write(self.style.NOTICE('Starting patient-to-clinic migration...'))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get all patients
        patients = User.objects.filter(role='patient')
        total_patients = patients.count()
        self.stdout.write(f'Found {total_patients} patients to process')
        
        # Get all clinics
        clinics = Clinic.objects.all()
        self.stdout.write(f'Found {clinics.count()} clinics')
        
        migrated_count = 0
        already_exists_count = 0
        no_clinic_count = 0
        
        with transaction.atomic():
            for patient in patients:
                # Find all clinics this patient has had consultations with
                patient_consultations = Consultation.objects.filter(
                    patient=patient,
                    clinic__isnull=False
                ).values('clinic').annotate(
                    consultation_count=Count('id')
                ).order_by('-consultation_count')
                
                if not patient_consultations:
                    no_clinic_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'  Patient {patient.id} ({patient.name}) has no consultations with any clinic')
                    )
                    continue
                
                for consultation_data in patient_consultations:
                    clinic_id = consultation_data['clinic']
                    consultation_count = consultation_data['consultation_count']
                    
                    try:
                        clinic = Clinic.objects.get(id=clinic_id)
                        
                        # Check if already exists
                        existing = ClinicPatient.objects.filter(
                            clinic=clinic,
                            patient=patient
                        ).exists()
                        
                        if existing:
                            already_exists_count += 1
                            self.stdout.write(
                                f'  Patient {patient.id} already registered to clinic {clinic.name}'
                            )
                        else:
                            if not dry_run:
                                ClinicPatient.objects.create(
                                    clinic=clinic,
                                    patient=patient,
                                    registration_source='migrated',
                                    registered_by=None,
                                    is_active=True
                                )
                            migrated_count += 1
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'  Migrated patient {patient.id} ({patient.name}) to clinic {clinic.name} '
                                    f'({consultation_count} consultations)'
                                )
                            )
                    except Clinic.DoesNotExist:
                        self.stdout.write(
                            self.style.ERROR(f'  Clinic {clinic_id} not found for patient {patient.id}')
                        )
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.NOTICE('=' * 50))
        self.stdout.write(self.style.NOTICE('MIGRATION SUMMARY'))
        self.stdout.write(self.style.NOTICE('=' * 50))
        self.stdout.write(f'Total patients processed: {total_patients}')
        self.stdout.write(self.style.SUCCESS(f'Patients migrated to clinics: {migrated_count}'))
        self.stdout.write(f'Already registered (skipped): {already_exists_count}')
        self.stdout.write(self.style.WARNING(f'Patients with no clinic consultations: {no_clinic_count}'))
        
        if dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('This was a DRY RUN. Run without --dry-run to apply changes.'))
