from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from .forms import RegistrationForm, LoginForm, AppointmentForm, ReviewForm, PatientProfileForm
from .models import Service, Doctor, Appointment, Review , ServiceCategory
from django.contrib import messages
from django.db.models import Q, Avg, Prefetch
from django.utils import timezone
import datetime
from collections import defaultdict


def home_view(request):
    return render(request, 'clinic/home.html')

# Общее контекстное меню
def navbar_context(request):
    # Если пользователь не аутентифицирован, is_doctor всегда False
    is_doctor = False
    if request.user.is_authenticated:
        # проверяем, есть ли у текущего пользователя профиль врача
        is_doctor = Doctor.objects.filter(user=request.user).exists()

    return {
        "user": request.user,
        "is_doctor": is_doctor,
    }


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


# Список услуг: сначала – без категории, потом – по категориям
@login_required
def service_list(request):
    q = request.GET.get("q", "").strip()

    if q:
        # Если есть поисковый запрос, отбираем услуги без категории и в категориях, где имя услуги содержит q
        uncategorized = (
            Service.objects
            .filter(category__isnull=True, name__icontains=q)
            .order_by("name")
        )
        categories = (
            ServiceCategory.objects
            .filter(services__name__icontains=q)
            .distinct()
            .prefetch_related(
                Prefetch(
                    "services",
                    queryset=Service.objects.filter(name__icontains=q).order_by("name"),
                )
            )
            .order_by("name")
        )
    else:
        # Без поиска: грузим все услуги без категории и все категории с их услугами
        uncategorized = Service.objects.filter(category__isnull=True).order_by("name")
        categories = (
            ServiceCategory.objects
            .prefetch_related("services")
            .order_by("name")
        )

    return render(request, "clinic/service_list.html", {
        "uncategorized": uncategorized,
        "categories": categories,
        "q": q,
    })


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
    doctor       = get_object_or_404(Doctor, pk=pk)
    appointments = Appointment.objects.filter(doctor=doctor)
    services     = Service.objects.all()

    # Средний рейтинг
    avg_data = Review.objects.filter(
        appointment__doctor=doctor
    ).aggregate(avg=Avg("rating"))
    avg_rating = avg_data["avg"] or 0.0

    # Вычисляем, сколько «полных», полузвезда и пустых звёзд
    full_stars = int(avg_rating)  
    half_star  = 1 if (avg_rating - full_stars) >= 0.5 else 0
    empty_stars = 5 - full_stars - half_star
    # собираем список: ['full', 'full', ..., 'half?', 'empty'...]
    star_list = (
        ["full"] * full_stars
        + (["half"] if half_star else [])
        + ["empty"] * empty_stars
    )

   # Отфильтруем будущие приёмы только для текущего пациента:
    upcoming = appointments.filter(
        patient=request.user.patient,
        date_time__gte=timezone.now()
    ).order_by("date_time")

    # 1) Услуги, у которых нет категории (NULL)
    uncat_services = Service.objects.filter(category__isnull=True).order_by("name")

    # 2) Сами категории, у которых есть хотя бы по одной услуге. 
    #    Для каждой категории заранее "запуллим" связанные услуги.
    categories = (
        ServiceCategory.objects
        .filter(services__isnull=False)          # выбираем только те категории, у которых есть минимум одна услуга
        .distinct()                              # убираем дубликаты
        .order_by("name")                        # сортируем категории по имени
        .prefetch_related("services")            # чтобы в шаблоне не делать доп. запросов к БД
    )

    # Если пришёл POST (пользователь нажал "Подтвердить запись"), создаём новую Appointment
    if request.method == "POST":
        service_id = request.POST.get("service")
        date_time = request.POST.get("date_time")
        service = Service.objects.get(pk=service_id)
        dt = datetime.datetime.fromisoformat(date_time)
        Appointment.objects.create(
            patient=request.user.patient,
            doctor=doctor,
            service=service,
            date_time=dt
        )
        return redirect("history")

    return render(
        request,
        "clinic/doctor_schedule.html",
        {
            "doctor": doctor,
            "appointments": appointments,
            "uncat_services": uncat_services,  
            "categories": categories,           
            "upcoming": upcoming,
            "avg_rating": avg_rating,
            "star_list": star_list,
        },
    )


# История приёмов
@login_required
def history(request):
    # Получаем все приёмы текущего пациента
    appts = Appointment.objects.filter(patient=request.user.patient).order_by('-date_time')

    # Передаём в контекст не только записи, но и текущее время
    return render(request, "clinic/history.html", {
        "appointments": appts,
        "now": timezone.now(),
    })


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


@login_required
def edit_profile(request):
    user = request.user
    if request.method == 'POST':
        form = PatientProfileForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Профиль успешно обновлён.')
            return redirect('edit_profile')
    else:
        form = PatientProfileForm(instance=user)

    return render(request, 'clinic/edit_profile.html', {
        'form': form
    })


@login_required
def my_patients(request):
    try:
        # Предполагается, что в модели Doctor есть OneToOneField на User:
        doctor = request.user.doctor
    except Doctor.DoesNotExist:
        # Если у пользователя нет связанного объекта Doctor, перенаправляем на домашнюю
        return redirect("home")

    # Берём все записи к этому доктору (и пациенты через patient.user)
    all_appointments = Appointment.objects.filter(
        doctor=doctor
    ).select_related("patient__user", "service").order_by("date_time")

    # Группируем по чистой дате (без времени)
    patients_by_date = defaultdict(list)
    for appt in all_appointments:
        date_only = appt.date_time.date()  # например, datetime.date(2025, 6, 10)
        patients_by_date[date_only].append(appt)

    # Превращаем в список ( [ (date, [appt1, appt2]), ... ] ), отсортированный по дате
    grouped_list = sorted(patients_by_date.items(), key=lambda x: x[0])

    # Передаём is_doctor=True, чтобы базовый шаблон понимал, что это врач
    return render(request, "clinic/my_patients.html", {
        "doctor": doctor,
        "grouped_list": grouped_list,
        "is_doctor": True,
    })