from django.urls import path
from .views_ui import (
    register, user_login, user_logout,
    service_list, doctor_list, doctor_schedule,
    history, leave_review, cancel_appointment
)
urlpatterns = [
    path('register/', register, name='register'),
    path('login/', user_login, name='login'),
    path('logout/', user_logout, name='logout'),
    path('', service_list, name='service_list'),
    path('doctors/', doctor_list, name='doctor_list'),
    path('doctors/<int:pk>/', doctor_schedule, name='doctor_schedule'),
    path('history/', history, name='history'),
    path('history/cancel/<int:pk>/', cancel_appointment, name='cancel_appointment'),
    path('review/<int:pk>/', leave_review, name='leave_review'),
]