from django.shortcuts import render, redirect
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .forms import RegistrationForm, LoginForm, AppointmentForm, ReviewForm
from .models import Service, Doctor, Appointment, Review

# Общее контекстное меню
def navbar_context(request):
    return {'user': request.user}

# Регистрация

def register(request):
    form = RegistrationForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('service_list')
    return render(request,'clinic/register.html',{'form':form})

# Логин

def user_login(request):
    form = LoginForm(request.POST or None)
    if request.method=='POST' and form.is_valid():
        login(request, form.cleaned_data['user'])
        return redirect('service_list')
    return render(request,'clinic/login.html',{'form':form})

# Logout

def user_logout(request):
    logout(request)
    return redirect('login')

# Список услуг
@login_required
def service_list(request):
    services = Service.objects.all()
    return render(request,'clinic/service_list.html',{'services':services})

# Список врачей
@login_required
def doctor_list(request):
    doctors = Doctor.objects.select_related('user').all()
    return render(request,'clinic/doctor_list.html',{'doctors':doctors})

# Расписание врача
@login_required
def doctor_schedule(request, pk):
    doctor = Doctor.objects.get(pk=pk)
    appointments = Appointment.objects.filter(doctor=doctor)
    form = AppointmentForm(initial={'doctor':doctor})
    if request.method=='POST':
        form = AppointmentForm(request.POST)
        if form.is_valid():
            appt = form.save(commit=False)
            appt.patient = request.user.patient
            appt.save()
            return redirect('history')
    return render(request,'clinic/doctor_schedule.html',{ 'doctor':doctor,'appointments':appointments,'form':form })

# История приёмов
@login_required
def history(request):
    appts = Appointment.objects.filter(patient=request.user.patient)
    return render(request,'clinic/history.html',{'appointments':appts})

# Оставить отзыв
@login_required
def leave_review(request, pk):
    appt = Appointment.objects.get(pk=pk, patient=request.user.patient)
    review, created = Review.objects.get_or_create(appointment=appt)
    form = ReviewForm(request.POST or None, instance=review)
    if request.method=='POST' and form.is_valid():
        form.save()
        return redirect('history')
    return render(request,'clinic/review_form.html',{'form':form,'appt':appt})