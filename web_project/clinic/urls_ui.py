from django.urls import path
from .views_ui import info_view, doctors_view, register_view

urlpatterns = [
    path('', info_view, name='info_ui'),
    path('doctors/', doctors_view, name='doctors_ui'),
    path('register/', register_view, name='register_ui'),
]