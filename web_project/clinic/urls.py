from django.urls import path
from .views import ServiceListView, DoctorListView, AppointmentCreateView

urlpatterns = [
    path('services/', ServiceListView.as_view(), name='service-list'),
    path('doctors/', DoctorListView.as_view(), name='doctor-list'),
    path('appointments/', AppointmentCreateView.as_view(), name='appointment-create'),
]
