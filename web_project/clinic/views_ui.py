from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .forms import RegistrationForm, LoginForm, AppointmentForm, ReviewForm
from .models import Service, Doctor, Appointment, Review
from django.contrib import messages
from django.db.models import Q, Avg
from django.utils import timezone
import datetime


# Общее контекстное меню
def navbar_context(request):
    return {"user": request.user}


# Регистрация


def register(request):
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("service_list")
    return render(request, "clinic/register.html", {"form": form})


# Логин


def user_login(request):
    form = LoginForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        login(request, form.cleaned_data["user"])
        return redirect("service_list")
    return render(request, "clinic/login.html", {"form": form})


# Logout


def user_logout(request):
    logout(request)
    return redirect("login")


# Список услуг
@login_required
def service_list(request):
    q = request.GET.get("q", "")
    if q:
        services = Service.objects.filter(name__icontains=q)
    else:
        services = Service.objects.all()
    return render(request, "clinic/service_list.html", {"services": services, "q": q})


# Список врачей
@login_required
def doctor_list(request):
    q = request.GET.get("q", "")
    spec = request.GET.get("spec", "")
    doctors = Doctor.objects.select_related("user").annotate(
        avg_rating=Avg("appointment__review__rating")
    )
    if q:
        doctors = doctors.filter(
            Q(user__first_name__icontains=q) | Q(user__last_name__icontains=q)
        )
    if spec:
        doctors = doctors.filter(specialization__icontains=spec)
    return render(
        request, "clinic/doctor_list.html", {"doctors": doctors, "q": q, "spec": spec}
    )


# Расписание врача
@login_required
def doctor_schedule(request, pk):
    doctor = get_object_or_404(Doctor, pk=pk)
    appointments = Appointment.objects.filter(doctor=doctor)
    services = Service.objects.all()
    avg_rating = (
        Review.objects.filter(appointment__doctor=doctor).aggregate(avg=Avg("rating"))[
            "avg"
        ]
        or 0
    )

    upcoming = appointments.filter(date_time__gte=timezone.now()).order_by("date_time")

    if request.method == "POST":
        # получаем данные из формы
        service_id = request.POST.get("service")
        date_time = request.POST.get("date_time")  # формат: YYYY-MM-DDTHH:MM
        service = Service.objects.get(pk=service_id)
        # преобразуем в datetime
        dt = datetime.datetime.fromisoformat(date_time)
        # создаём запись
        Appointment.objects.create(
            patient=request.user.patient, doctor=doctor, service=service, date_time=dt
        )
        return redirect("history")
    return render(
        request,
        "clinic/doctor_schedule.html",
        {
            "doctor": doctor,
            "appointments": appointments,
            "services": services,
            "upcoming": upcoming,
            'avg_rating': avg_rating,
        },
    )


# История приёмов
@login_required
def history(request):
    appts = Appointment.objects.filter(patient=request.user.patient)
    return render(request, "clinic/history.html", {"appointments": appts})


@login_required
def cancel_appointment(request, pk):
    # Убеждаемся, что запись именно этого пациента
    appt = get_object_or_404(Appointment, pk=pk, patient=request.user.patient)
    if request.method == "POST":
        appt.delete()
        messages.success(request, "Ваша запись была успешно отменена.")
    return redirect("history")


# Оставить отзыв
@login_required
def leave_review(request, pk):
    # Находим приём, гарантируя, что пациент свой
    appt = get_object_or_404(Appointment, pk=pk, patient=request.user.patient)

    # Пытаемся загрузить уже существующий отзыв, но не создаём его заранее
    try:
        review = Review.objects.get(appointment=appt)
    except Review.DoesNotExist:
        review = None

    if request.method == "POST":
        # Если отзыв есть, редактируем, иначе создаём новый
        form = ReviewForm(request.POST, instance=review)
        if form.is_valid():
            rev = form.save(commit=False)
            rev.appointment = appt
            rev.save()
            return redirect("history")
    else:
        # GET: заполняем форму существующим отзывом или пустой
        form = ReviewForm(instance=review)

    return render(
        request,
        "clinic/review_form.html",
        {
            "form": form,
            "appt": appt,
        },
    )
