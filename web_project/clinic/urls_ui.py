from django.urls import path
from .views_ui import (
    home_view, register, user_login, user_logout,
    service_list, doctor_list, doctor_schedule,
    history, leave_review, cancel_appointment, edit_profile
)
urlpatterns = [
     # теперь корень сайта — home_view
    path('', home_view, name='home'),

    path('register/', register, name='register'),
    path('login/', user_login, name='login'),
    path('logout/', user_logout, name='logout'),
    path('services/', service_list, name='service_list'),
    path('doctors/', doctor_list, name='doctor_list'),
    path('doctors/<int:pk>/', doctor_schedule, name='doctor_schedule'),
    path('history/', history, name='history'),
    path('history/cancel/<int:pk>/', cancel_appointment, name='cancel_appointment'),
    path('review/<int:pk>/', leave_review, name='leave_review'),
    path('profile/edit/', edit_profile, name='edit_profile'),
]