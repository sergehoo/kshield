"""URLs enrôlement RFID temps réel — montées sous /api/v1/rfid/."""
from django.urls import path

from .views_enrollment import (EnrollmentConfirmView, EnrollmentIngestScanView,
                                EnrollmentSessionDetailView,
                                EnrollmentSessionExportView, EnrollmentStartView,
                                EnrollmentStopView)

urlpatterns = [
    path("enrollment/start/",                              EnrollmentStartView.as_view(),         name="rfid-enroll-start"),
    path("enrollment/<uuid:session_id>/stop/",             EnrollmentStopView.as_view(),          name="rfid-enroll-stop"),
    path("enrollment/<uuid:session_id>/confirm/",          EnrollmentConfirmView.as_view(),       name="rfid-enroll-confirm"),
    path("enrollment/sessions/<uuid:session_id>/",         EnrollmentSessionDetailView.as_view(), name="rfid-enroll-session"),
    path("enrollment/sessions/<uuid:session_id>/export/",  EnrollmentSessionExportView.as_view(), name="rfid-enroll-export"),
    path("enrollment/ingest/",                             EnrollmentIngestScanView.as_view(),    name="rfid-enroll-ingest"),
]
