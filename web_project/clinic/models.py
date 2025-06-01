from django.db import models
from django.conf import settings
from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    PermissionsMixin,
)


class CustomUserManager(BaseUserManager):
    def create_user(self, phone, password=None, **extra_fields):
        if not phone:
            raise ValueError("Номер телефона обязателен")
        user = self.model(phone=phone, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(phone, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    phone = models.CharField(max_length=20, unique=True)
    first_name = models.CharField(max_length=100, verbose_name="Имя", blank=True)
    last_name = models.CharField(max_length=100, verbose_name="Фамилия", blank=True)
    patronymic = models.CharField(max_length=100, verbose_name="Отчество", blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS = ["first_name", "last_name", "patronymic"]

    def __str__(self):
        return f"{self.first_name} {self.last_name} {self.patronymic}".strip()

    class Meta:
        verbose_name = "Пользователь"
        verbose_name_plural = "Пользователи"


class Doctor(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    specialization = models.CharField(max_length=100)
    photo = models.ImageField(
       upload_to='doctors_photos/',
       blank=True,
       null=True,
       verbose_name='Фотография'
   )

    def __str__(self):
        return f"{self.user.first_name} {self.user.patronymic}"

    class Meta:
        verbose_name = "Врач"
        verbose_name_plural = "Врачи"


class Patient(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.user)

    class Meta:
        verbose_name = "Пациент"
        verbose_name_plural = "Пациенты"


class ServiceCategory(models.Model):
    """
    Категория для услуг: например, «Удаление зуба», «Лечение кариеса» и т. д.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        verbose_name="Категория услуги"
    )

    class Meta:
        verbose_name = "Категория услуги"
        verbose_name_plural = "Категории услуг"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Service(models.Model):
    """
    Модель услуги, привязанная (необязательно) к категории.
    """
    category = models.ForeignKey(
        ServiceCategory,
        verbose_name="Категория",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="services"
    )
    name = models.CharField("Название услуги", max_length=255)
    price = models.DecimalField("Цена", max_digits=10, decimal_places=2)

    class Meta:
        verbose_name = "Услуга"
        verbose_name_plural = "Услуги"
        ordering = ["category__name", "name"]

    def __str__(self):
        return self.name


class Appointment(models.Model):
    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    doctor = models.ForeignKey(Doctor, on_delete=models.CASCADE)
    service = models.ForeignKey(Service, on_delete=models.CASCADE)
    date_time = models.DateTimeField()

    def __str__(self):
        return f"{self.patient} - {self.service} - {self.date_time}"

    class Meta:
        verbose_name = "Запись"
        verbose_name_plural = "Записи"


class Review(models.Model):
    appointment = models.OneToOneField(Appointment, on_delete=models.CASCADE)
    rating = models.IntegerField(
        choices=[(i, f"{i} звёзд{'ы' if i>1 else ''}") for i in range(1, 6)],
        verbose_name="Оценка"
    )
    pros = models.TextField(blank=True, verbose_name="Плюсы")
    cons = models.TextField(blank=True, verbose_name="Минусы")
    created = models.DateTimeField(auto_now_add=True, verbose_name="Дата отзыва")

    def __str__(self):
        return f"Отзыв к {self.appointment} — {self.rating}"

    class Meta:
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"

class TelegramProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE
    )
    chat_id = models.CharField(max_length=64, unique=True)

    def __str__(self):
        return f"{self.user} ↔ {self.chat_id}"