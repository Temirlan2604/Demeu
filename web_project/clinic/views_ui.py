from django.shortcuts import render
from .models import Doctor

# Страница "О стоматологии"
def info_view(request):
    return render(request, 'clinic/info.html')

# Страница "Про врачей"
def doctors_view(request):
    doctors = Doctor.objects.select_related('user').all()
    return render(request, 'clinic/doctors.html', {'doctors': doctors})

# Страница регистрации (шаблон с fetch)
def register_view(request):
    return render(request, 'clinic/register.html')