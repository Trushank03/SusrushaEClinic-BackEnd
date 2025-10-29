import os
import hashlib
import tempfile
import glob
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from datetime import datetime
from django.conf import settings
import requests
from urllib.parse import urlparse

class WPDFGenerator:
    def __init__(self, prescription, filename="w_generated.pdf", logo_path=None):
        self.prescription = prescription
        self.filename = filename
        self.buffer = BytesIO()
        self.c = canvas.Canvas(self.buffer, pagesize=A4)
        self.width, self.height = A4
        
        # Use the correct logo URL or provided logo path
        if logo_path and os.path.exists(logo_path):
            # Validate that the file is actually an image
            try:
                from PIL import Image
                with Image.open(logo_path) as img:
                    # If we can open it, it's a valid image
                    self.logo_path = logo_path
                    print(f"✅ Valid logo file found: {logo_path}")
            except Exception as e:
                print(f"❌ Invalid logo file {logo_path}: {e}")
                self.logo_path = None
        else:
            self.logo_path = None
        
        # Set up fallback logo URLs
        self.fallback_logo_urls = [
            "https://edrspace.sgp1.digitaloceanspaces.com/edrcontainer1/clinic_logos/sushrusa_logo_WB.png",
            "https://sushrusaeclinic.com/media/clinic_logos/sushrusa_logo_WB.png",
            "https://sushrusaeclinic.com/static/clinic_logos/sushrusa_logo_WB.png",
            "https://sushrusaeclinic.com/sushrusa_logo_1-Photoroom.png"
        ]

        # Define colors based on image analysis
        self.line_color = colors.HexColor("#D3D3D3")  # Light gray for lines
        self.heading_color = colors.HexColor("#E17726") # Orange for headings (app theme)
        self.order_medicine_color = colors.HexColor("#E17726") # Orange for ORDER MEDICINE (app theme)

    def _download_logo(self, url):
        """Download logo from URL and save temporarily"""
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                # Create a temporary file with unique name
                import tempfile
                temp_fd, temp_path = tempfile.mkstemp(suffix='.png', prefix='sushrusa_logo_')
                os.close(temp_fd)
                with open(temp_path, 'wb') as f:
                    f.write(response.content)
                print(f"✅ Logo downloaded successfully to: {temp_path}")
                return temp_path
        except Exception as e:
            print(f"❌ Error downloading logo from {url}: {e}")
        return None

    def _cleanup_temp_files(self):
        """Clean up temporary logo files"""
        try:
            import glob
            import tempfile
            temp_dir = tempfile.gettempdir()
            pattern = os.path.join(temp_dir, 'sushrusa_logo_*')
            for temp_file in glob.glob(pattern):
                try:
                    os.remove(temp_file)
                    print(f"🧹 Cleaned up temporary file: {temp_file}")
                except Exception as e:
                    print(f"⚠️ Could not remove temporary file {temp_file}: {e}")
        except Exception as e:
            print(f"⚠️ Error during cleanup: {e}")

    def _create_text_logo(self, center_x, center_y):
        """Create a professional text-based logo"""
        # Draw a simple logo box - Increased size to match larger image logo
        logo_width = 220
        logo_height = 85
        logo_x = center_x - (logo_width / 2)
        logo_y = center_y - 20
        
        # Draw logo background rectangle
        self.c.setFillColor(colors.white)
        self.c.setStrokeColor(colors.white)
        self.c.rect(logo_x, logo_y, logo_width, logo_height, fill=True, stroke=True)
        
        # Draw logo text - Increased font sizes for even larger logo
        self.c.setFillColor(colors.HexColor("#E17726"))  # Orange color
        self.c.setFont("Helvetica-Bold", 24)
        self.c.drawCentredString(center_x, center_y + 25, "SUSHRUSA")
        self.c.setFont("Helvetica-Bold", 16)
        self.c.drawCentredString(center_x, center_y + 8, "eCLINIC")
        self.c.setFont("Helvetica", 12)
        self.c.drawCentredString(center_x, center_y - 8, "Healthcare Platform")
        
        # Draw a simple icon (medical cross) - Increased size for even larger logo
        self.c.setFillColor(colors.HexColor("#E17726"))
        self.c.setStrokeColor(colors.HexColor("#E17726"))
        self.c.setLineWidth(4)
        
        # Draw medical cross
        cross_size = 15
        cross_x = center_x - (cross_size / 2)
        cross_y = center_y - 40
        
        # Vertical line
        self.c.line(cross_x + cross_size/2, cross_y, cross_x + cross_size/2, cross_y + cross_size)
        # Horizontal line
        self.c.line(cross_x, cross_y + cross_size/2, cross_x + cross_size, cross_y + cross_size/2)
        
        # Reset line width
        self.c.setLineWidth(1)

    def _calculate_age(self, date_of_birth):
        """Calculate age from date of birth"""
        if not date_of_birth:
            return "N/A"
        
        today = datetime.now().date()
        age = today.year - date_of_birth.year
        if today.month < date_of_birth.month or (today.month == date_of_birth.month and today.day < date_of_birth.day):
            age -= 1
        return str(age)

    def _draw_header(self):
        # Header background bar
        header_height = 90
        self.c.setFillColor(colors.HexColor("#FFF3E0"))  # Light orange background
        self.c.rect(0, self.height - header_height, self.width, header_height, fill=True, stroke=False)
        self.c.setFillColor(colors.black)

        # Left side - Doctor info only
        left_x = 40
        left_y = self.height - 30
        self.c.setFont("Helvetica-Bold", 12)
        self.c.setFillColor(colors.black)
        doctor_name = getattr(self.prescription.doctor, 'name', 'Doctor')
        self.c.drawString(left_x, left_y, f"Dr. {doctor_name}")
        
        # Dynamic doctor details under name
        try:
            doctor_profile = self.prescription.doctor.doctor_profile
            qualifications = getattr(doctor_profile, 'qualification', getattr(self.prescription.doctor, 'qualifications', ''))
            specialization = getattr(doctor_profile, 'specialization', '')
            license_number = getattr(doctor_profile, 'license_number', '')
        except Exception:
            qualifications = getattr(self.prescription.doctor, 'qualifications', '')
            specialization = getattr(self.prescription.doctor, 'specialization', '')
            license_number = getattr(self.prescription.doctor, 'registration_number', '')
        
        self.c.setFont("Helvetica", 10)
        # Add doctor qualification, specialization and license number
        if qualifications:
            self.c.drawString(left_x, left_y - 14, qualifications)
        if specialization:
            self.c.drawString(left_x, left_y - 28, specialization)
        if license_number:
            self.c.drawString(left_x, left_y - 42, license_number)

        # Center: Sushrusa logo
        center_x = self.width / 2
        center_y = self.height - 50
        
        # Try multiple logo paths - use relative paths that work in both local and production
        logo_paths = []
        
        # Use the provided logo path if available
        if self.logo_path:
            logo_paths.append(self.logo_path)
        
        # Try relative paths from Django settings
        if settings.MEDIA_ROOT:
            logo_paths.extend([
                os.path.join(settings.MEDIA_ROOT, 'clinic_logos', 'sushrusa_logo_WB.png'),
                os.path.join(settings.MEDIA_ROOT, 'prescription_headers', 'test_prescription_header.png')
            ])
        
        # Try BASE_DIR paths
        if settings.BASE_DIR:
            logo_paths.extend([
                os.path.join(settings.BASE_DIR, 'media_cdn', 'clinic_logos', 'sushrusa_logo_WB.png'),
                os.path.join(settings.BASE_DIR, 'prescription_headers', 'test_prescription_header.png')
            ])
        
        # Fallback to static files if STATIC_ROOT is available
        if settings.STATIC_ROOT:
            logo_paths.append(os.path.join(settings.STATIC_ROOT, 'clinic_logos', 'sushrusa_logo_WB.png'))
        
        logo_displayed = False
        
        # First try local file paths
        for logo_path in logo_paths:
            if logo_path and os.path.exists(logo_path):
                try:
                    center_logo = ImageReader(logo_path)
                    # Increased logo size for better visibility
                    logo_width = 160
                    logo_height = 80
                    logo_x = center_x - (logo_width / 2)
                    logo_y = center_y - (logo_height / 2)
                    self.c.drawImage(center_logo, logo_x, logo_y, width=logo_width, height=logo_height, preserveAspectRatio=True, mask='auto')
                    print(f"✅ Using local logo: {logo_path}")
                    logo_displayed = True
                    break
                except Exception as e:
                    print(f"Local logo image error for {logo_path}: {e}")
                    continue
        
        # If no local logo found, try downloading from URLs
        if not logo_displayed:
            for logo_url in self.fallback_logo_urls:
                try:
                    print(f"🔍 Trying to download logo from: {logo_url}")
                    response = requests.get(logo_url, timeout=10)
                    if response.status_code == 200:
                        center_logo = ImageReader(BytesIO(response.content))
                        logo_width = 160
                        logo_height = 80
                        logo_x = center_x - (logo_width / 2)
                        logo_y = center_y - (logo_height / 2)
                        self.c.drawImage(center_logo, logo_x, logo_y, width=logo_width, height=logo_height, preserveAspectRatio=True, mask='auto')
                        print(f"✅ Using downloaded logo from: {logo_url}")
                        logo_displayed = True
                        break
                except Exception as e:
                    print(f"Failed to download logo from {logo_url}: {e}")
                    continue
        
        if not logo_displayed:
            # Create professional text logo as fallback - increased size
            self.c.setFillColor(colors.HexColor("#E17726"))  # Orange theme color
            self.c.setFont("Helvetica-Bold", 24)
            self.c.drawCentredString(center_x, center_y + 15, "SUSHRUSA")
            self.c.setFont("Helvetica-Bold", 14)
            self.c.drawCentredString(center_x, center_y - 5, "eCLINIC")
            self.c.setFont("Helvetica", 11)
            self.c.drawCentredString(center_x, center_y - 25, "Healthcare Platform")
        
        self.c.setFillColor(colors.black)

        # Right side: Sushrusa eCLINIC text and address
        right_x = self.width - 40
        right_y = self.height - 30
        self.c.setFont("Helvetica", 9)
        self.c.setFillColor(colors.black)
        
        # Add Sushrusa eCLINIC text above address
        self.c.setFont("Helvetica-Bold", 11)
        self.c.setFillColor(colors.HexColor("#E17726"))  # Orange theme color
        self.c.drawRightString(right_x, right_y, "Sushrusa eCLINIC")
        
        # Show address and contact info
        self.c.setFont("Helvetica", 9)
        self.c.setFillColor(colors.black)
        address_lines = [
            "HIG 11, AINIGIA HB COLONY",
            "PHASE 2, KHANDAGIRI",
            "BHUBANESWAR, PIN: 751030",
            "MOB: 6370511060"
        ]
        
        for i, line in enumerate(address_lines):
            self.c.drawRightString(right_x, right_y - 15 - (i * 12), line)

        # No underline below header - cleaner design

    def _draw_appointment_details(self):
        y_pos = self.height - 130 # Starting position after header
        
        # Add horizontal line between header and patient details - positioned with proper spacing
        self.c.setStrokeColor(self.line_color)
        self.c.setLineWidth(0.5)
        self.c.line(30, y_pos + 15, self.width - 30, y_pos + 15)
        
        self.c.setFillColor(self.heading_color)
        self.c.setFont("Helvetica-Bold", 10)  # Slightly increased font size
        self.c.drawString(30, y_pos, "PATIENT DETAILS")

        y_pos -= 18
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica", 9)  # Slightly increased font size for better readability
        
        # Formatted patient information with proper labels in single line
        patient_age = self._calculate_age(getattr(self.prescription.patient, 'date_of_birth', None))
        patient_sex = getattr(self.prescription.patient, 'gender', 'N/A')
        patient_id = f"P{str(self.prescription.patient.id).zfill(4)}"
        
        # Single line with labeled patient info
        patient_info = f"Patient Name: {self.prescription.patient.name} | Age: {patient_age} years | Sex: {patient_sex} | Date: {self.prescription.issued_date.strftime('%d/%m/%Y')} {self.prescription.issued_time.strftime('%H:%M')} | Patient ID: {patient_id}"
        self.c.drawString(30, y_pos, patient_info)

    def _draw_vital_signs(self):
        y_pos = self.height - 170 # Reduced spacing from appointment details
        
        # Add horizontal line between patient details and vital signs - positioned with proper spacing
        self.c.setStrokeColor(self.line_color)
        self.c.setLineWidth(0.5)
        self.c.line(30, y_pos + 15, self.width - 30, y_pos + 15)
        
        self.c.setFillColor(self.heading_color)
        self.c.setFont("Helvetica-Bold", 10)  # Slightly increased font size
        self.c.drawString(30, y_pos, "VITAL SIGNS")

        y_pos -= 18
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica", 8)  # Slightly increased font size for better readability
        
        # Collect only essential vital signs: Pulse rate, BP, height, weight
        vitals_parts = []
        
        # From prescription model
        if self.prescription.pulse:
            vitals_parts.append(f"Pulse: {self.prescription.pulse}bpm")
        if self.prescription.blood_pressure_systolic and self.prescription.blood_pressure_diastolic:
            vitals_parts.append(f"BP: {self.prescription.blood_pressure_systolic}/{self.prescription.blood_pressure_diastolic}mmHg")
        if self.prescription.weight:
            vitals_parts.append(f"Wt: {self.prescription.weight}kg")
        if self.prescription.height:
            vitals_parts.append(f"Ht: {self.prescription.height}cm")
        
        # From consultation vital signs if available and not already added
        if hasattr(self.prescription, 'consultation') and self.prescription.consultation and hasattr(self.prescription.consultation, 'vital_signs'):
            consultation_vitals = self.prescription.consultation.vital_signs
            if consultation_vitals:
                if consultation_vitals.heart_rate and not any('Pulse' in v for v in vitals_parts):
                    vitals_parts.append(f"Pulse: {consultation_vitals.heart_rate}bpm")
                if consultation_vitals.blood_pressure_systolic and consultation_vitals.blood_pressure_diastolic and not any('BP' in v for v in vitals_parts):
                    vitals_parts.append(f"BP: {consultation_vitals.blood_pressure_systolic}/{consultation_vitals.blood_pressure_diastolic}mmHg")
                if consultation_vitals.weight and not any('Wt' in v for v in vitals_parts):
                    vitals_parts.append(f"Wt: {consultation_vitals.weight}kg")
                if consultation_vitals.height and not any('Ht' in v for v in vitals_parts):
                    vitals_parts.append(f"Ht: {consultation_vitals.height}cm")
        
        # Display all vital signs in one line with separators
        if vitals_parts:
            vitals_line = " | ".join(vitals_parts)
            self.c.drawString(30, y_pos, vitals_line)
        else:
            self.c.drawString(30, y_pos, "No vital signs recorded")

    # def _draw_patient_history(self):
    #     """Draw patient medical history section"""
    #     y_pos = self.height - 210 # Reduced spacing from vital signs
    #     self.c.setFillColor(self.heading_color)
    #     self.c.setFont("Helvetica-Bold", 9)  # Slightly increased font size
    #     self.c.drawString(30, y_pos, "PATIENT MEDICAL HISTORY")
    #     y_pos -= 15  # Reduced spacing
    #     
    #     self.c.setFillColor(colors.black)
    #     self.c.setFont("Helvetica", 8)  # Slightly increased font size
    #     if self.prescription.patient_previous_history:
    #         # Truncate long history to fit in smaller space
    #         history_text = self.prescription.patient_previous_history[:120] + "..." if len(self.prescription.patient_previous_history) > 120 else self.prescription.patient_previous_history
    #         self.c.drawString(30, y_pos, history_text)
    #     else:
    #         self.c.drawString(30, y_pos, "No previous medical history recorded")
    #     y_pos -= 12  # Reduced spacing
    #     return y_pos

    def _draw_diagnosis(self):
        y_pos = self.height - 210 # Moved up to fill space left by removed patient history
        
        # Add horizontal line between vital signs and diagnosis - positioned with proper spacing
        self.c.setStrokeColor(self.line_color)
        self.c.setLineWidth(0.5)
        self.c.line(30, y_pos + 15, self.width - 30, y_pos + 15)
        
        self.c.setFillColor(self.heading_color)
        self.c.setFont("Helvetica-Bold", 9)  # Slightly increased font size
        self.c.drawString(30, y_pos, "DIAGNOSIS")

        y_pos -= 15  # Reduced spacing
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica", 8)  # Slightly increased font size
        
        # Compact diagnosis display
        diagnosis_parts = []
        
        # Primary Diagnosis
        if self.prescription.primary_diagnosis:
            diagnosis_parts.append(self.prescription.primary_diagnosis)
        
        # Clinical Classification
        if self.prescription.clinical_classification:
            diagnosis_parts.append(self.prescription.clinical_classification)
        
        # Display diagnosis in one line if possible
        if diagnosis_parts:
            diagnosis_text = " | ".join(diagnosis_parts)
            # Truncate if too long
            if len(diagnosis_text) > 100:
                diagnosis_text = diagnosis_text[:97] + "..."
            self.c.drawString(30, y_pos, diagnosis_text)
        else:
            self.c.drawString(30, y_pos, "No diagnosis recorded")
        return y_pos - 20

    def _draw_medication(self):
        y_pos = self.height - 250 # Moved up to fill space left by removed patient history
        
        # Add horizontal line between diagnosis and medications - positioned with proper spacing
        self.c.setStrokeColor(self.line_color)
        self.c.setLineWidth(0.5)
        self.c.line(30, y_pos + 15, self.width - 30, y_pos + 15)
        
        # Draw Rx symbol and heading
        self.c.setFillColor(self.heading_color)
        self.c.setFont("Helvetica-Bold", 14)  # Larger font for Rx
        self.c.drawString(30, y_pos, "Rx")
        self.c.setFont("Helvetica-Bold", 9)  # Slightly increased font size for medications
        self.c.drawString(60, y_pos, "MEDICATIONS")
        
        y_pos -= 25

        # Medications in tabular format with horizontal lines only (matching image design)
        medications = self.prescription.medications.all().order_by('order')
        print(f"🔍 PDF Generator - Total medications found: {medications.count()}")
        for i, med in enumerate(medications):
            print(f"🔍 Medication {i+1}: '{med.medicine_name}' | Composition: '{med.composition}' | ID: {med.id}, Order: {med.order}")
            print(f"🔍   Dosage: {med.morning_dose}-{med.afternoon_dose}-{med.evening_dose} | Timing: {med.timing}")
        
        if medications.exists():
            # Column positions (matching image layout)
            col1_x = 40   # Medicine Name (wider)
            col2_x = 170  # Dosage (M-A-E) - reduced to give more space
            col3_x = 230  # Duration-Freq-Instructions - reduced to give more space
            
            # Draw header row with horizontal line
            self.c.setFillColor(self.heading_color)
            self.c.setFont("Helvetica-Bold", 9)
            
            # Draw header text
            self.c.drawString(col1_x, y_pos, "Medicine")
            self.c.drawString(col2_x, y_pos, "Dosage")
            self.c.drawString(col3_x, y_pos, "Duration - Freq. - Instructions")
            
            # Draw horizontal line under header
            self.c.setStrokeColor(self.line_color)
            self.c.setLineWidth(0.5)
            self.c.line(col1_x, y_pos - 3, self.width - 40, y_pos - 3)
            
            y_pos -= 20
            
            # Draw medication rows with horizontal lines
            self.c.setFillColor(colors.black)
            self.c.setFont("Helvetica", 8)
            
            for idx, med in enumerate(medications, 1):
                # Medicine column - show medicine name only
                medicine_lines = []
                
                # Medicine name - clean up any duplicate text within the field itself
                medicine_name = med.medicine_name or 'Medicine'
                medicine_name_lines = medicine_name.split('\n')
                # Remove duplicates while preserving order
                seen = set()
                unique_lines = []
                for line in medicine_name_lines:
                    line = line.strip()
                    if line and line not in seen:
                        seen.add(line)
                        unique_lines.append(line)
                
                # Add first unique line only - no composition or other details
                if unique_lines:
                    medicine_lines.append(unique_lines[0])
                
                # Dosage column - M-A-E format
                dosage = f"{med.morning_dose}-{med.afternoon_dose}-{med.evening_dose}"
                
                # Duration-Freq-Instructions column - show duration, frequency, timing, and instructions
                duration_freq_instructions = []
                
                # Duration
                duration = ""
                if med.duration_days:
                    duration = f"{med.duration_days} days"
                elif med.duration_weeks:
                    duration = f"{med.duration_weeks} weeks"
                elif med.duration_months:
                    duration = f"{med.duration_months} months"
                elif med.is_continuous:
                    duration = "Continuous"
                
                if duration:
                    duration_freq_instructions.append(duration)
                
                # Frequency
                frequency = med.get_frequency_display() if hasattr(med, 'get_frequency_display') else (med.frequency or "")
                if frequency:
                    duration_freq_instructions.append(frequency)
                
                # Timing details (moved from medicine column)
                # Use timing_display_text if available, otherwise fall back to single timing
                if hasattr(med, 'timing_display_text') and med.timing_display_text:
                    duration_freq_instructions.append(med.timing_display_text)
                elif med.timing:
                    timing_display = med.get_timing_display() if hasattr(med, 'get_timing_display') else med.timing
                    if timing_display:
                        duration_freq_instructions.append(timing_display)
                
                # Special instructions
                if med.special_instructions:
                    duration_freq_instructions.append(med.special_instructions)
                
                # Draw medicine column (multi-line)
                medicine_y = y_pos
                for line in medicine_lines:
                    if len(line) > 45:  # Truncate long lines
                        line = line[:42] + "..."
                    self.c.drawString(col1_x, medicine_y, line)
                    medicine_y -= 10
                
                # Draw dosage column
                self.c.drawString(col2_x, y_pos, dosage)
                
                # Draw duration-freq-instructions column with wrapping instead of truncation
                def wrap_text(text, max_width, font_name="Helvetica", font_size=8):
                    self.c.setFont(font_name, font_size)
                    words = text.split(' ')
                    lines, current = [], ""
                    for w in words:
                        trial = (current + " " + w).strip()
                        if self.c.stringWidth(trial, font_name, font_size) <= max_width:
                            current = trial
                        else:
                            if current:
                                lines.append(current)
                            current = w
                    if current:
                        lines.append(current)
                    return lines

                duration_freq_instructions_text = " | ".join(duration_freq_instructions)
                max_text_width = (self.width - 40) - col3_x
                wrapped_lines = wrap_text(duration_freq_instructions_text, max_text_width)
                instr_y = y_pos
                for line in wrapped_lines:
                    self.c.drawString(col3_x, instr_y, line)
                    instr_y -= 10
                
                # Calculate row height first
                rows_needed = max(1, len(medicine_lines), len(wrapped_lines))
                row_height = rows_needed * 10
                
                # Move y_pos down to account for the content we just drew
                y_pos -= row_height
                
                # Add spacing below content before drawing line
                y_pos -= 8  # Space below content
                
                # Draw horizontal line centered between rows
                self.c.setStrokeColor(self.line_color)
                self.c.setLineWidth(0.5)
                line_y = y_pos
                self.c.line(col1_x, line_y, self.width - 40, line_y)
                
                # Add spacing below line for next row
                y_pos -= 8  # Space below line
                
                # Check for page break
                if y_pos < 150:
                    self.c.showPage()
                    self._draw_header()
                    y_pos = self.height - 120
        else:
            self.c.setFillColor(colors.black)
            self.c.setFont("Helvetica", 8)
            self.c.drawString(40, y_pos, "No medications prescribed")
            y_pos -= 15

        # Draw investigation tests inline
        y_pos = self._draw_investigation_tests_inline(y_pos - 10)
        
        # Then draw advice and instructions
        self._draw_advice_instructions(y_pos)

    def _draw_doctor_signature(self):
        """Draw doctor signature for single page prescriptions"""
        # Position signature at bottom right
        signature_y = 150  # Above footer
        
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica", 9)
        # Removed "Prescribed on" text as requested
        
        # Get doctor profile information
        try:
            doctor_profile = self.prescription.doctor.doctor_profile
            doctor_qualifications = getattr(doctor_profile, 'qualification', 'MBBS')
            doctor_specialization = getattr(doctor_profile, 'specialization', 'Family Physician')
            license_number = getattr(doctor_profile, 'license_number', 'Reg.No. TSMC/FMR/15345')
            
            # Removed qualifications and license number text as requested - showing only signature
            
            # Draw doctor's signature image if available
            if doctor_profile.signature:
                try:
                    from reportlab.lib.utils import ImageReader
                    import requests
                    from io import BytesIO
                    
                    # Try to get signature from cloud storage
                    signature_url = doctor_profile.signature.url
                    
                    # Download signature from cloud storage
                    response = requests.get(signature_url, timeout=10)
                    if response.status_code == 200:
                        # Create image from bytes
                        signature_data = BytesIO(response.content)
                        signature_img = ImageReader(signature_data)
                        
                        # Calculate signature dimensions (maintain aspect ratio)
                        img_width, img_height = signature_img.getSize()
                        max_width = 120
                        max_height = 60
                        
                        # Scale to fit within bounds while maintaining aspect ratio
                        scale = min(max_width / img_width, max_height / img_height)
                        scaled_width = img_width * scale
                        scaled_height = img_height * scale
                        
                        # Position signature above the signature text
                        signature_x = self.width - 200
                        signature_y_pos = signature_y - 60
                        
                        self.c.drawImage(signature_img, signature_x, signature_y_pos, width=scaled_width, height=scaled_height, preserveAspectRatio=True)
                        
                        # Add signature text below the image
                        self.c.setFont("Helvetica", 9)
                        self.c.drawString(signature_x, signature_y_pos - 20, "Doctor's Signature")
                        
                except Exception as e:
                    print(f"Error drawing doctor signature: {e}")
                    # Fallback to text signature
                    self.c.setFont("Helvetica-Bold", 12)
                    self.c.drawString(self.width - 200, signature_y - 60, "_________________")
                    self.c.setFont("Helvetica", 9)
                    self.c.drawString(self.width - 200, signature_y - 75, "Doctor's Signature")
            else:
                # No signature in profile - use text signature
                self.c.setFont("Helvetica-Bold", 12)
                self.c.drawString(self.width - 200, signature_y - 60, "_________________")
                self.c.setFont("Helvetica", 9)
                self.c.drawString(self.width - 200, signature_y - 75, "Doctor's Signature")
            
        except Exception as e:
            print(f"Error accessing doctor profile: {e}")
            # Fallback to basic signature - showing only signature without qualifications/license
            
            # Add signature line
            self.c.setFont("Helvetica-Bold", 12)
            self.c.drawString(self.width - 200, signature_y - 70, "_________________")
            self.c.setFont("Helvetica", 9)
            self.c.drawString(self.width - 200, signature_y - 85, "Doctor's Signature")

    def _draw_doctor_signature_page2(self):
        """Draw doctor signature for second page prescriptions"""
        # Position signature at center-right of page 2
        signature_y = self.height - 300
        
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica", 9)
        # Removed "Prescribed on" text as requested
        self.c.setFont("Helvetica-Bold", 10)
        self.c.drawString(self.width - 200, signature_y, f"Dr. {self.prescription.doctor.name}")
        self.c.setFont("Helvetica", 9)
        
        # Get doctor profile information
        try:
            doctor_profile = self.prescription.doctor.doctor_profile
            doctor_qualifications = getattr(doctor_profile, 'qualification', 'MBBS')
            doctor_specialization = getattr(doctor_profile, 'specialization', 'Family Physician')
            license_number = getattr(doctor_profile, 'license_number', 'Reg.No. TSMC/FMR/15345')
            
            # Removed qualifications and license number text as requested - showing only signature
            
            # Draw doctor's signature image if available
            if doctor_profile.signature:
                try:
                    from reportlab.lib.utils import ImageReader
                    import requests
                    from io import BytesIO
                    
                    # Try to get signature from cloud storage
                    signature_url = doctor_profile.signature.url
                    
                    # Download signature from cloud storage
                    response = requests.get(signature_url, timeout=10)
                    if response.status_code == 200:
                        # Create image from bytes
                        signature_data = BytesIO(response.content)
                        signature_img = ImageReader(signature_data)
                        
                        # Calculate signature dimensions (maintain aspect ratio)
                        img_width, img_height = signature_img.getSize()
                        max_width = 120
                        max_height = 60
                        
                        # Scale to fit within bounds while maintaining aspect ratio
                        scale = min(max_width / img_width, max_height / img_height)
                        scaled_width = img_width * scale
                        scaled_height = img_height * scale
                        
                        # Position signature above the signature text
                        signature_x = self.width - 200
                        signature_y_pos = signature_y - 60
                        
                        self.c.drawImage(signature_img, signature_x, signature_y_pos, width=scaled_width, height=scaled_height, preserveAspectRatio=True)
                        
                        # Add signature text below the image
                        self.c.setFont("Helvetica", 9)
                        self.c.drawString(signature_x, signature_y_pos - 20, "Doctor's Signature")
                        
                except Exception as e:
                    print(f"Error drawing doctor signature: {e}")
                    # Fallback to text signature
                    self.c.setFont("Helvetica-Bold", 12)
                    self.c.drawString(self.width - 200, signature_y - 60, "_________________")
                    self.c.setFont("Helvetica", 9)
                    self.c.drawString(self.width - 200, signature_y - 75, "Doctor's Signature")
            else:
                # No signature in profile - use text signature
                self.c.setFont("Helvetica-Bold", 12)
                self.c.drawString(self.width - 200, signature_y - 60, "_________________")
                self.c.setFont("Helvetica", 9)
                self.c.drawString(self.width - 200, signature_y - 75, "Doctor's Signature")
            
        except Exception as e:
            print(f"Error accessing doctor profile: {e}")
            # Fallback to basic signature - showing only signature without qualifications/license
            
            # Add signature line
            self.c.setFont("Helvetica-Bold", 12)
            self.c.drawString(self.width - 200, signature_y - 70, "_________________")
            self.c.setFont("Helvetica", 9)
            self.c.drawString(self.width - 200, signature_y - 85, "Doctor's Signature")



    def _draw_advice_instructions(self, start_y_pos=None):
        # FIXED: Check if we need a page break before drawing advice
        if start_y_pos is None:
            y_pos = self.height - 620 # Increased margin top for better spacing
        else:
            y_pos = start_y_pos - 40  # Add extra margin top
        
        # If we're too close to bottom, start new page
        if y_pos < 200:
            self.c.showPage()
            self._draw_header()  # Redraw header on new page
            y_pos = self.height - 200  # Reset position for new page
        
        # Add horizontal line between medications and advice/instructions - positioned with proper spacing
        self.c.setStrokeColor(self.line_color)
        self.c.setLineWidth(0.5)
        self.c.line(30, y_pos + 15, self.width - 30, y_pos + 15)
        
        self.c.setFillColor(self.heading_color)
        self.c.setFont("Helvetica-Bold", 10)
        self.c.drawString(30, y_pos, "ADVICE/ INSTRUCTIONS")

        # Enhanced advice and instructions display
        y_pos -= 20
        self.c.setFillColor(colors.black)
        self.c.setFont("Helvetica", 9)
        
        instructions_sections = []
        
        # General Instructions
        if self.prescription.general_instructions:
            instructions_sections.append(f"General Instructions: {self.prescription.general_instructions}")
        
        # Fluid Intake
        if self.prescription.fluid_intake:
            instructions_sections.append(f"Fluid Intake: {self.prescription.fluid_intake}")
        
        # Diet Instructions
        if self.prescription.diet_instructions:
            instructions_sections.append(f"Diet Instructions: {self.prescription.diet_instructions}")
        
        # Lifestyle Advice
        if self.prescription.lifestyle_advice:
            instructions_sections.append(f"Lifestyle Advice: {self.prescription.lifestyle_advice}")
        
        # Next Visit
        if self.prescription.next_visit:
            instructions_sections.append(f"Next Visit: {self.prescription.next_visit}")
        
        # Follow-up Notes
        if self.prescription.follow_up_notes:
            instructions_sections.append(f"Follow-up Notes: {self.prescription.follow_up_notes}")
        
        if instructions_sections:
            for instruction in instructions_sections:
                self.c.drawString(30, y_pos, instruction)
                y_pos -= 15
        else:
            self.c.drawString(30, y_pos, "General Instructions: Take regular medication as prescribed")
            y_pos -= 15

    def _draw_investigation_tests_inline(self, start_y_pos=None):
        """Draw investigation tests section inline with medications"""
        if start_y_pos is None:
            y_pos = self.height - 580
        else:
            y_pos = start_y_pos
        
        # If we're too close to bottom, start new page
        if y_pos < 150:
            self.c.showPage()
            self._draw_header()  # Redraw header on new page
            y_pos = self.height - 120  # Reset position for new page
        
        # Get investigation tests for this prescription
        try:
            investigations = self.prescription.investigations.all().order_by('order')
            print(f"🔍 PDF Generator - Total investigations found: {investigations.count()}")
            for i, inv in enumerate(investigations):
                print(f"🔍 Investigation {i+1}: {inv.test.name} (ID: {inv.id}, Order: {inv.order})")
            
            if investigations.exists():
                self.c.setFillColor(self.heading_color)
                self.c.setFont("Helvetica-Bold", 9)  # Slightly increased font size
                self.c.drawString(30, y_pos, "TEST PRESCRIBED")
                
                y_pos -= 15
                self.c.setFillColor(colors.black)
                self.c.setFont("Helvetica", 8)  # Slightly increased font size for better readability
                
                # Draw investigation tests in compact format
                for idx, investigation in enumerate(investigations, 1):
                    test_name = investigation.test.name
                    category_name = investigation.test.category.name
                    priority = investigation.priority.upper()
                    
                    # Compact format: "T1. Test Name (Category) - Priority" to distinguish from medications
                    test_line = f"T{idx}. {test_name} ({category_name})"
                    if priority != 'ROUTINE':
                        test_line += f" - {priority}"
                    
                    # Truncate if too long
                    if len(test_line) > 80:
                        test_line = test_line[:77] + "..."
                    
                    self.c.drawString(40, y_pos, test_line)
                    
                    # Special instructions on same line if short, otherwise next line
                    if investigation.special_instructions:
                        if len(investigation.special_instructions) < 40:
                            instruction_text = f" | {investigation.special_instructions}"
                            # Check if it fits on the same line
                            if len(test_line + instruction_text) <= 120:
                                self.c.drawString(40 + len(test_line) * 4, y_pos, instruction_text)
                            else:
                                y_pos -= 8
                                self.c.drawString(50, y_pos, f"Instructions: {investigation.special_instructions[:60]}")
                    
                    y_pos -= 10
                    
                    # Check if we need a page break
                    if y_pos < 120:
                        self.c.showPage()
                        self._draw_header()
                        y_pos = self.height - 120
                
                # Next Visit section removed - already shown in ADVICE/INSTRUCTIONS
                
                return y_pos  # Return the new y position
            else:
                # Next Visit section removed - already shown in ADVICE/INSTRUCTIONS
                return y_pos - 20  # Return original position
                
        except Exception as e:
            print(f"Error drawing investigation tests: {e}")
            return start_y_pos  # Return original position on error

    def _draw_footer(self, page_num, total_pages):
        # Simplified footer with just blank space at bottom
        # Add blank space at bottom
        self.c.setFillColor(colors.white)
        self.c.rect(0, 0, self.width, 80, fill=True, stroke=False)

    def generate_pdf(self):
        # Debug marker to confirm our generator is being used
        print("🚀 USING ENHANCED PDF GENERATOR - VERSION WITH FIXES")
        
        # Single page prescription - everything on one page
        self._draw_header()
        self._draw_appointment_details()
        self._draw_vital_signs()
        # self._draw_patient_history()
        diagnosis_y = self._draw_diagnosis()
        self._draw_medication()  # This now includes tests and next visit inline
        
        # Add footer and signature on same page
        self._draw_footer(1, 1)
        self._draw_doctor_signature()
        
        self.c.save()
        
        # Clean up temporary files
        self._cleanup_temp_files()
        
        # Get the PDF data from buffer
        pdf_data = self.buffer.getvalue()
        self.buffer.close()
        
        return pdf_data

    def generate_and_save(self, user):
        """Generate PDF and save to PrescriptionPDF model"""
        from .models import PrescriptionPDF
        
        # Generate PDF
        pdf_data = self.generate_pdf()
        
        # Calculate checksum
        checksum = hashlib.md5(pdf_data).hexdigest()
        
        # Create PrescriptionPDF instance
        pdf_instance = PrescriptionPDF(
            prescription=self.prescription,
            generated_by=user,
            file_size=len(pdf_data),
            checksum=checksum
        )
        
        # Save header image if provided
        if self.logo_path:
            pdf_instance.header_image = self.logo_path
        
        # Save the PDF file with timestamp to force regeneration
        import time
        timestamp = int(time.time())
        filename = f"prescription_{self.prescription.id}_v{pdf_instance.version_number or 1}_{timestamp}.pdf"
        pdf_instance.pdf_file.save(
            filename,
            BytesIO(pdf_data),
            save=False
        )
        
        pdf_instance.save()
        
        return pdf_instance


def generate_prescription_pdf(prescription, user, header_image_path=None, footer_image_path=None):
    """Generate a professional prescription PDF using the WPDFGenerator design"""
    generator = WPDFGenerator(
        prescription=prescription,
        logo_path=header_image_path
    )
    return generator.generate_and_save(user)


def test_pdf_generator():
    """Test function to verify PDF generation works correctly"""
    try:
        # Create a mock prescription object for testing
        class MockPrescription:
            def __init__(self):
                self.id = "TEST001"
                self.patient = MockPatient()
                self.doctor = MockDoctor()
                self.consultation = MockConsultation()
                self.issued_date = datetime.now()
                self.issued_time = datetime.now()
                self.primary_diagnosis = "Test Diagnosis"
                self.general_instructions = "Test Instructions"
                self.medications = MockMedicationManager()
                self.pulse = 72
                self.blood_pressure_systolic = 120
                self.blood_pressure_diastolic = 80
                self.temperature = 98.6
                self.weight = 70
                self.height = 170
        
        class MockPatient:
            def __init__(self):
                self.name = "Test Patient"
                self.date_of_birth = datetime(1990, 1, 1)
                self.gender = "Male"
                self.email = "test@example.com"
                self.mobile = "+919876543210"
        
        class MockDoctor:
            def __init__(self):
                self.name = "Dr. Test Doctor"
                self.qualifications = "MBBS, MD"
                self.specialization = "General Medicine"
                self.registration_number = "Reg.No. TEST123"
                self.mobile = "+919876543211"
                self.email = "doctor@example.com"
        
        class MockConsultation:
            def __init__(self):
                self.chief_complaint = "Test complaint"
                self.clinic = None
        
        class MockMedicationManager:
            def all(self):
                return []
            def exists(self):
                return False
            def count(self):
                return 0
        
        class MockUser:
            def __init__(self):
                self.id = "USER001"
        
        # Test the generator
        mock_prescription = MockPrescription()
        mock_user = MockUser()
        
        # Test with no logo (should use text logo)
        print("🧪 Testing PDF generation with text logo...")
        generator = WPDFGenerator(mock_prescription)
        pdf_data = generator.generate_pdf()
        
        print("✅ PDF generation test successful!")
        print(f"📄 Generated PDF size: {len(pdf_data)} bytes")
        
        # Test with a real logo if we can create one
        try:
            test_logo_path = create_test_logo()
            if test_logo_path:
                print("🧪 Testing PDF generation with real logo...")
                generator_with_logo = WPDFGenerator(mock_prescription, logo_path=test_logo_path)
                pdf_data_with_logo = generator_with_logo.generate_pdf()
                print("✅ PDF generation with logo test successful!")
                print(f"📄 Generated PDF with logo size: {len(pdf_data_with_logo)} bytes")
                
                # Clean up test logo
                try:
                    os.remove(test_logo_path)
                    print(f"🧹 Cleaned up test logo: {test_logo_path}")
                except:
                    pass
        except Exception as e:
            print(f"⚠️ Logo test failed: {e}")
        
        return True
        
    except Exception as e:
        print(f"❌ PDF generation test failed: {e}")
        return False


def create_test_logo():
    """Create a simple test logo file for testing purposes"""
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        # Create a simple logo image - Increased size to match even larger dimensions
        width, height = 360, 144
        image = Image.new('RGB', (width, height), color='white')
        draw = ImageDraw.Draw(image)
        
        # Draw a simple logo design
        # Background rectangle
        draw.rectangle([18, 18, width-18, height-18], outline='#E17726', width=5)
        
        # Text
        try:
            # Try to use a default font
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        except:
            # Fallback to default
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()
        
        # Draw text - Adjusted for even larger logo
        draw.text((width//2, 40), "SUSHRUSA", fill='#E17726', anchor='mm', font=font_large)
        draw.text((width//2, 70), "eCLINIC", fill='#E17726', anchor='mm', font=font_small)
        draw.text((width//2, 95), "Healthcare", fill='#E17726', anchor='mm', font=font_small)
        
        # Draw a simple medical cross - Even larger for bigger logo
        cross_size = 25
        cross_x = width - 50
        cross_y = height//2 - cross_size//2
        
        # Vertical line
        draw.line([cross_x + cross_size//2, cross_y, cross_x + cross_size//2, cross_y + cross_size], fill='#E17726', width=2)
        # Horizontal line
        draw.line([cross_x, cross_y + cross_size//2, cross_x + cross_size, cross_y + cross_size//2], fill='#E17726', width=2)
        
        # Save the logo
        logo_path = "test_logo.png"
        image.save(logo_path)
        print(f"✅ Test logo created: {logo_path}")
        return logo_path
        
    except Exception as e:
        print(f"❌ Failed to create test logo: {e}")
        return None


def generate_mobile_prescription_pdf(prescription, prescription_image):
    """
    Generate a mobile prescription PDF with uploaded image displayed from vital signs to doctor signature
    """
    try:
        # Create a custom PDF generator for mobile with image
        generator = MobilePDFGenerator(prescription, prescription_image)
        return generator.generate_and_save()
        
    except Exception as e:
        print(f"Error generating mobile PDF: {e}")
        raise e


class MobilePDFGenerator(WPDFGenerator):
    """Mobile PDF Generator that includes uploaded image in the prescription"""
    
    def __init__(self, prescription, prescription_image):
        super().__init__(prescription, "mobile_prescription.pdf")
        self.prescription_image = prescription_image
    
    def _draw_mobile_image_section(self, start_y, end_y):
        """Draw the uploaded image section for mobile prescriptions, extending from start_y to within 20px of end_y"""
        try:
            # Check if image exists and is accessible
            if not self.prescription_image or not self.prescription_image.image_file:
                print(f"Prescription image not found or not accessible")
                return end_y
            
            # Load and draw the image using the file object
            from reportlab.lib.utils import ImageReader
            from django.core.files.base import ContentFile
            
            # Read the image file content
            image_file = self.prescription_image.image_file
            image_content = image_file.read()
            
            # Reset file pointer
            image_file.seek(0)
            
            # Create ImageReader from file content
            img = ImageReader(ContentFile(image_content))
            
            # Calculate available space for image
            available_height = start_y - end_y  # Space from start_y to end_y
            available_width = 500  # Max width to fit page
            
            # Get original image dimensions
            original_width, original_height = img.getSize()
            
            # Calculate scaling to fit available space while maintaining aspect ratio
            width_ratio = available_width / original_width
            height_ratio = available_height / original_height
            
            # Use the smaller ratio to ensure image fits in both dimensions
            scale_ratio = min(width_ratio, height_ratio)
            
            # Calculate final dimensions
            img_width = original_width * scale_ratio
            img_height = original_height * scale_ratio
            
            print(f"🔍 Mobile PDF Generator - Original: {original_width}x{original_height}")
            print(f"🔍 Mobile PDF Generator - Available space: {available_width}x{available_height}")
            print(f"🔍 Mobile PDF Generator - Final dimensions: {img_width}x{img_height}")
            
            # Center the image horizontally
            img_x = (self.width - img_width) / 2
            
            # Position image at start_y and extend down
            img_y = start_y - img_height
            
            # Draw image
            self.c.drawImage(img, img_x, img_y, width=img_width, height=img_height)
            
            # Return the bottom position of the image
            return img_y
            
        except Exception as e:
            print(f"Error drawing mobile image: {e}")
            return end_y
    
    def generate_pdf(self):
        """Generate simplified mobile PDF with just header, patient details, vital signs, and uploaded image"""
        print(f"🔍 Mobile PDF Generator - Creating simplified mobile PDF for prescription {self.prescription.id}")
        print(f"🔍 Mobile PDF Generator - Image: {self.prescription_image.image_file.name if self.prescription_image else 'None'}")
        
        # Draw only essential sections for mobile
        self._draw_header()
        self._draw_appointment_details()
        self._draw_vital_signs()
        
        # Calculate position for image: after vital signs with 20px gap
        # Vital signs end at y_pos around 282 (height - 170 - 18 - vital signs height)
        # Add 20px gap after vital signs
        image_start_y = self.height - 170 - 18 - 15 - 20  # 20px gap after vital signs
        
        # Calculate available space for image (extend to within 20px of doctor signature)
        # Doctor signature is at y=150, so image should end at y=150+20+signature_height = ~230
        image_end_y = 150 + 20 + 80  # 20px gap + signature height (~80px)
        
        print(f"🔍 Mobile PDF Generator - Image start y: {image_start_y}, end y: {image_end_y}")
        
        # Draw the uploaded image with calculated space
        final_y_pos = self._draw_mobile_image_section(image_start_y, image_end_y)
        
        # Draw doctor signature at the bottom
        self._draw_doctor_signature()
        
        # Add minimal footer
        self._draw_footer(1, 1)
        
        self.c.save()
        
        # Clean up temporary files
        self._cleanup_temp_files()
        
        # Get the PDF data from buffer
        pdf_data = self.buffer.getvalue()
        self.buffer.close()
        
        print(f"🔍 Mobile PDF Generator - PDF generated successfully, size: {len(pdf_data)} bytes")
        return pdf_data
    
    def generate_and_save(self):
        """Generate PDF and save to PrescriptionPDF model"""
        from .models import PrescriptionPDF
        from django.contrib.auth import get_user_model
        
        # Generate PDF
        pdf_data = self.generate_pdf()
        
        # Calculate checksum
        checksum = hashlib.md5(pdf_data).hexdigest()
        
        # Create PrescriptionPDF instance
        pdf_instance = PrescriptionPDF(
            prescription=self.prescription,
            generated_by=self.prescription.doctor,  # Use the prescription doctor
            file_size=len(pdf_data),
            checksum=checksum,
            is_mobile_generated=True
        )
        
        # Save the PDF file
        filename = f"mobile_prescription_{self.prescription.id}_v{pdf_instance.version_number or 1}.pdf"
        pdf_instance.pdf_file.save(
            filename,
            BytesIO(pdf_data),
            save=False
        )
        
        pdf_instance.save()
        
        return pdf_instance


def _draw_mobile_prescription_content(canvas, prescription, image_path, width, height):
    """
    Draw mobile prescription content with uploaded image
    """
    try:
        # Header
        canvas.setFillColor(colors.HexColor('#FFF3E0'))
        canvas.rect(0, height - 80, width, 80, fill=True, stroke=False)
        
        # Logo
        logo_path = os.path.join(settings.MEDIA_ROOT, "sushrusa_logo_1-Photoroom.png")
        if os.path.exists(logo_path):
            logo = ImageReader(logo_path)
            canvas.drawImage(logo, 30, height - 60, width=40, height=40)
        
        # Title
        canvas.setFillColor(colors.HexColor('#E17726'))
        canvas.setFont("Helvetica-Bold", 16)
        canvas.drawString(80, height - 45, "SUSHRUSA eCLINIC")
        canvas.drawString(80, height - 60, "PRESCRIPTION")
        
        # Doctor info
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(colors.black)
        doctor = prescription.doctor
        canvas.drawString(30, height - 100, f"Dr. {doctor.get('name', 'N/A')}")
        canvas.drawString(30, height - 115, f"{doctor.get('qualification', 'MBBS')} | {doctor.get('specialization', 'General Medicine')}")
        canvas.drawString(30, height - 130, f"Registration: {doctor.get('registration_number', 'N/A')}")
        
        # Prescribed date
        canvas.drawString(width - 150, height - 100, f"Prescribed on {prescription.issued_date}")
        
        # Patient details
        y_pos = height - 180
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.HexColor('#E17726'))
        canvas.drawString(30, y_pos, "PATIENT DETAILS")
        
        y_pos -= 20
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(colors.black)
        patient = prescription.patient
        canvas.drawString(30, y_pos, f"Name: {patient.get('name', 'N/A')}")
        y_pos -= 15
        canvas.drawString(30, y_pos, f"Age: {prescription.patient_age} years | Gender: {prescription.patient_gender}")
        y_pos -= 15
        canvas.drawString(30, y_pos, f"Mobile: {patient.get('phone', 'N/A')}")
        
        # Vital signs
        y_pos -= 30
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.HexColor('#E17726'))
        canvas.drawString(30, y_pos, "VITAL SIGNS")
        
        y_pos -= 20
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(colors.black)
        
        vital_signs = prescription.vital_signs
        if vital_signs:
            if vital_signs.get('pulse'):
                canvas.drawString(30, y_pos, f"Pulse: {vital_signs.pulse} bpm")
                y_pos -= 15
            if vital_signs.get('blood_pressure_systolic') and vital_signs.get('blood_pressure_diastolic'):
                canvas.drawString(30, y_pos, f"Blood Pressure: {vital_signs.blood_pressure_systolic}/{vital_signs.blood_pressure_diastolic} mmHg")
                y_pos -= 15
            if vital_signs.get('temperature'):
                canvas.drawString(30, y_pos, f"Temperature: {vital_signs.temperature}°F")
                y_pos -= 15
            if vital_signs.get('weight'):
                canvas.drawString(30, y_pos, f"Weight: {vital_signs.weight} kg")
                y_pos -= 15
            if vital_signs.get('height'):
                canvas.drawString(30, y_pos, f"Height: {vital_signs.height} cm")
                y_pos -= 15
        
        # Add uploaded image at the bottom of vital signs
        y_pos -= 20
        try:
            # Check if image exists
            full_image_path = os.path.join(settings.MEDIA_ROOT, image_path)
            if os.path.exists(full_image_path):
                # Add image title
                canvas.setFont("Helvetica-Bold", 12)
                canvas.setFillColor(colors.HexColor('#E17726'))
                canvas.drawString(30, y_pos, "PRESCRIPTION IMAGE")
                y_pos -= 20
                
                # Load and draw the image
                img = ImageReader(full_image_path)
                
                # Calculate image dimensions (max width 400px, maintain aspect ratio)
                img_width, img_height = img.getSize()
                max_width = 400
                if img_width > max_width:
                    ratio = max_width / img_width
                    img_width = max_width
                    img_height = img_height * ratio
                
                # Draw image
                canvas.drawImage(img, 30, y_pos - img_height, width=img_width, height=img_height)
                y_pos -= img_height + 20
            else:
                canvas.setFont("Helvetica", 10)
                canvas.setFillColor(colors.red)
                canvas.drawString(30, y_pos, "Image not found")
                y_pos -= 20
        except Exception as e:
            canvas.setFont("Helvetica", 10)
            canvas.setFillColor(colors.red)
            canvas.drawString(30, y_pos, f"Error loading image: {str(e)}")
            y_pos -= 20
        
        # Doctor signature area
        y_pos -= 30
        canvas.setFont("Helvetica-Bold", 12)
        canvas.setFillColor(colors.HexColor('#E17726'))
        canvas.drawString(30, y_pos, "DOCTOR'S SIGNATURE")
        
        y_pos -= 40
        canvas.setFont("Helvetica", 10)
        canvas.setFillColor(colors.black)
        canvas.drawString(30, y_pos, f"Dr. {doctor.get('name', 'N/A')}")
        canvas.drawString(30, y_pos - 15, f"{doctor.get('qualification', 'MBBS')} | {doctor.get('specialization', 'General Medicine')}")
        
    except Exception as e:
        print(f"Error drawing mobile prescription content: {e}")
        raise e

