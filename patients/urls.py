from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

app_name = 'patients'

# Create router for ViewSets
router = DefaultRouter()
router.register(r'', views.PatientProfileViewSet, basename='patient-profile')

urlpatterns = [
    # Patient-specific endpoints for dashboard
    path('medical-records/', views.PatientMedicalRecordsView.as_view(), name='patient-medical-records'),
    
    # Patient search and statistics
    path('search/', views.PatientSearchView.as_view(), name='patient-search'),
    path('stats/', views.PatientStatsView.as_view(), name='patient-stats'),
    
    # Patient-specific nested resources
    path('<str:patient_id>/medical-records/', 
         views.PatientMedicalRecordViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='patient-medical-records'),
    path('<str:patient_id>/medical-records/bulk/', 
         views.PatientMedicalRecordViewSet.as_view({'post': 'bulk_create'}), 
         name='patient-medical-records-bulk'),
    path('<str:patient_id>/medical-records/<int:pk>/', 
         views.PatientMedicalRecordViewSet.as_view({
             'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
         }), 
         name='patient-medical-record-detail'),
    
    path('<str:patient_id>/documents/', 
         views.PatientDocumentViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='patient-documents'),
    path('<str:patient_id>/documents/<int:pk>/', 
         views.PatientDocumentViewSet.as_view({
             'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
         }), 
         name='patient-document-detail'),
    
    path('<str:patient_id>/notes/', 
         views.PatientNoteViewSet.as_view({'get': 'list', 'post': 'create'}), 
         name='patient-notes'),
    path('<str:patient_id>/notes/<int:pk>/', 
         views.PatientNoteViewSet.as_view({
             'get': 'retrieve', 'put': 'update', 'patch': 'partial_update', 'delete': 'destroy'
         }), 
         name='patient-note-detail'),
    
    # Patient consultations
    path('<str:patient_id>/consultations/', 
         views.PatientConsultationView.as_view(), 
         name='patient-consultations'),
    
    # Include router URLs for main patient profile operations
    path('', include(router.urls)),
]

