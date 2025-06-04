from django.urls import path
from .views import ServiceListCreateView, DoctorListView, AppointmentCreateView

urlpatterns = [
    path('api/services/', ServiceListCreateView.as_view(), name='service-list-create'),
    path('doctors/', DoctorListView.as_view(), name='doctor-list'),
    path('appointments/', AppointmentCreateView.as_view(), name='appointment-create'),
]
