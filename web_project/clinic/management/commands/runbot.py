from django.core.management.base import BaseCommand
from django.conf import settings
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters,
    ConversationHandler, CallbackContext
)
from telegram.error import TimedOut
from clinic.models import (
    Service, Doctor, Appointment,
    TelegramProfile, Review, Patient
)
import datetime, pytz
from django.utils import timezone   # <-- добавили импорт

# этапы разговоров
ASK_PHONE, ASK_FIRST, ASK_LAST, ASK_REG_PASS = range(4)
ASK_LOGIN_PHONE, ASK_LOGIN_PASS = 4, 5
ASK_DOCTOR, ASK_SERVICE = 6, 7
ASK_DATE, ASK_TIME = 8, 9

class Command(BaseCommand):
    help = "Запускает Telegram-бота стоматологии"

    def handle(self, *args, **options):
        updater = Updater(
            settings.TELEGRAM_BOT_TOKEN,
            use_context=True,
            request_kwargs={'read_timeout':20,'connect_timeout':10}
        )
        dp = updater.dispatcher

        # /start
        def start(update: Update, ctx: CallbackContext):
            update.message.reply_text(
                "👋 Добро пожаловать! Войти — /login, зарегистрироваться — /register"
            )

        # ===== ЛОГИН =====
        def login_start(update: Update, ctx: CallbackContext):
            kb = [[KeyboardButton("Поделиться номером", request_contact=True)]]
            update.message.reply_text(
                "Для входа пришлите телефон (кнопка или вручную):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_LOGIN_PHONE

        def login_phone(update: Update, ctx: CallbackContext):
            phone = (update.effective_message.contact.phone_number
                     if update.effective_message.contact
                     else update.message.text.strip())
            ctx.user_data['login_phone'] = phone
            update.message.reply_text(
                "Введите пароль:",
                reply_markup=ReplyKeyboardMarkup([[]], remove_keyboard=True)
            )
            return ASK_LOGIN_PASS

        def login_pass(update: Update, ctx: CallbackContext):
            pw = update.message.text.strip()
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(phone=ctx.user_data['login_phone'])
            except User.DoesNotExist:
                update.message.reply_text("❌ Пользователь не найден. Сначала /register")
                return ConversationHandler.END

            if not user.check_password(pw):
                update.message.reply_text("❌ Неправильный пароль.")
                return ConversationHandler.END

            TelegramProfile.objects.update_or_create(
                chat_id=str(update.effective_chat.id),
                defaults={'user': user}
            )
            update.message.reply_text(f"✅ Вы вошли как {user.first_name} {user.last_name}")
            return ConversationHandler.END

        # ===== РЕГИСТРАЦИЯ =====
        def register_start(update: Update, ctx: CallbackContext):
            kb = [[KeyboardButton("Поделиться номером", request_contact=True)]]
            update.message.reply_text(
                "Пришлите свой телефон (кнопка или вручную):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_PHONE

        def register_phone(update: Update, ctx: CallbackContext):
            phone = (update.effective_message.contact.phone_number
                     if update.effective_message.contact
                     else update.message.text.strip())
            ctx.user_data['reg_phone'] = phone
            update.message.reply_text(
                "Введите имя:",
                reply_markup=ReplyKeyboardMarkup([[]], remove_keyboard=True)
            )
            return ASK_FIRST

        def register_first(update: Update, ctx: CallbackContext):
            ctx.user_data['reg_first'] = update.message.text.strip()
            update.message.reply_text("Введите фамилию:")
            return ASK_LAST

        def register_last(update: Update, ctx: CallbackContext):
            ctx.user_data['reg_last'] = update.message.text.strip()
            update.message.reply_text("Придумайте пароль:")
            return ASK_REG_PASS

        def register_pass(update: Update, ctx: CallbackContext):
            pw = update.message.text.strip()
            from django.contrib.auth import get_user_model
            User = get_user_model()
            user = User.objects.create_user(
                phone=ctx.user_data['reg_phone'],
                password=pw,
                first_name=ctx.user_data['reg_first'],
                last_name=ctx.user_data['reg_last']
            )
            # сразу создаём запись в таблице Patient
            Patient.objects.create(user=user)
            TelegramProfile.objects.create(
                chat_id=str(update.effective_chat.id),
                user=user
            )
            update.message.reply_text(
                "✅ Регистрация завершена! Теперь вы – пациент.\n"
                "Команды:\n"
                "/login, /services, /doctors, /book, /myappointments, /profile, /help"
            )
            return ConversationHandler.END

        # ===== ПРОСМОТР УСЛУГ И ВРАЧЕЙ =====
        def services_cmd(update: Update, ctx: CallbackContext):
            items = Service.objects.all()
            text = "\n".join(f"– {s.name} ({s.price}₸)" for s in items)
            update.message.reply_text("📋 Наши услуги:\n" + text)

        def doctors_cmd(update: Update, ctx: CallbackContext):
            docs = Doctor.objects.select_related('user').all()
            lines = [f"{d.pk}. Dr. {d.user.last_name} ({d.specialization})" for d in docs]
            txt = "👩‍⚕️ Наши врачи:\n" + "\n".join(lines)
            try:
                update.message.reply_text(txt)
            except TimedOut:
                update.message.reply_text("Сервер занят, попробуйте позже.")

        # ===== ЗАПИСЬ НА ПРИЁМ =====
        def book_start(update: Update, ctx: CallbackContext):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
                ctx.user_data['tp'] = tp
            except TelegramProfile.DoesNotExist:
                update.message.reply_text("Сначала /register")
                return ConversationHandler.END

            docs = Doctor.objects.select_related('user').all()
            kb = [[str(d.pk)] for d in docs]
            update.message.reply_text(
                "Выберите врача (номер):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_DOCTOR

        def book_doctor(update: Update, ctx: CallbackContext):
            ctx.user_data['doctor_pk'] = int(update.message.text.strip())
            services = Service.objects.all()
            kb = [[str(s.pk)] for s in services]
            update.message.reply_text(
                "Выберите услугу (номер):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_SERVICE

        def book_service(update: Update, ctx: CallbackContext):
            ctx.user_data['service_pk'] = int(update.message.text.strip())
            today = datetime.date.today()
            dates = [
                today + datetime.timedelta(days=i)
                for i in range(7)
                if (today + datetime.timedelta(days=i)).weekday() != 6
            ]
            kb = [[d.strftime("%d.%m.%Y")] for d in dates]
            update.message.reply_text(
                "Выберите дату:",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
            )
            return ASK_DATE

        def book_date(update: Update, ctx: CallbackContext):
            ds = update.message.text.strip()
            try:
                date = datetime.datetime.strptime(ds, "%d.%m.%Y").date()
            except:
                update.message.reply_text("Неверная дата, выберите кнопкой.")
                return ASK_DATE
            ctx.user_data['date'] = ds

            wd = date.weekday()
            start, end = (9, 17) if wd < 5 else (9, 13)
            slots = [f"{h:02d}:00" for h in range(start, end)]
            kb = [[t] for t in slots]
            update.message.reply_text(
                f"Выберите время для {ds}:",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
            )
            return ASK_TIME

        def book_time(update: Update, ctx: CallbackContext):
            ts = update.message.text.strip()   # "10:00"
            ds = ctx.user_data['date']         # "07.05.2025"
            try:
                dt_naive = datetime.datetime.strptime(f"{ds} {ts}", "%d.%m.%Y %H:%M")
            except ValueError:
                update.message.reply_text("Неверное время, выберите кнопку заново.")
                return ASK_TIME

            # делаем aware в локальном часовом поясе
            dt = timezone.make_aware(dt_naive)

            tp  = ctx.user_data['tp']
            doc = Doctor.objects.get(pk=ctx.user_data['doctor_pk'])
            svc = Service.objects.get(pk=ctx.user_data['service_pk'])
            Appointment.objects.create(
                patient=tp.user.patient,
                doctor=doc,
                service=svc,
                date_time=dt
            )
            update.message.reply_text("✅ Запись создана! /myappointments")
            return ConversationHandler.END

        # ===== МОИ ЗАПИСИ И ОТМЕНА =====
        def myappointments_cmd(update: Update, ctx: CallbackContext):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                return update.message.reply_text("Сначала /register")

            appts = Appointment.objects.filter(patient=tp.user.patient)
            if not appts:
                return update.message.reply_text("У вас нет записей.")

            lines = []
            for a in appts:
                # конвертируем из UTC в локальный Asia/Almaty
                local_dt = timezone.localtime(a.date_time)
                lines.append(
                    f"{a.pk}. {a.service.name} у Dr. {a.doctor.user.last_name} — "
                    f"{local_dt.strftime('%d.%m.%Y %H:%M')}"
                )

            update.message.reply_text(
                "Ваши записи:\n" + "\n".join(lines) + "\nОтменить: /cancel <номер>"
            )

        def cancel_cmd(update: Update, ctx: CallbackContext):
            parts = update.message.text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                return update.message.reply_text("Используйте: /cancel <номер>")
            pk = int(parts[1])
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
                Appointment.objects.get(pk=pk, patient=tp.user.patient).delete()
                update.message.reply_text("❌ Запись отменена.")
            except:
                update.message.reply_text("Не нашли запись.")

        # ===== ПРОФИЛЬ =====
        def profile_cmd(update: Update, ctx: CallbackContext):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                return update.message.reply_text("Сначала /register")
            u = tp.user
            update.message.reply_text(
                f"👤 Профиль:\nИмя: {u.first_name}\nФамилия: {u.last_name}\nТелефон: {u.phone}"
            )

        # ===== ПОМОЩЬ =====
        def help_cmd(update: Update, ctx: CallbackContext):
            update.message.reply_text(
                "/login\n/register\n/services\n/doctors\n/book\n"
                "/myappointments\n/cancel <номер>\n/profile\n/help"
            )

        # Регистрируем хендлеры
        dp.add_handler(ConversationHandler(
            entry_points=[CommandHandler('login', login_start)],
            states={
                ASK_LOGIN_PHONE: [MessageHandler(Filters.contact | (Filters.text & ~Filters.command), login_phone)],
                ASK_LOGIN_PASS:  [MessageHandler(Filters.text & ~Filters.command, login_pass)]
            },
            fallbacks=[]
        ))
        dp.add_handler(ConversationHandler(
            entry_points=[CommandHandler('register', register_start)],
            states={
                ASK_PHONE:      [MessageHandler(Filters.contact | (Filters.text & ~Filters.command), register_phone)],
                ASK_FIRST:      [MessageHandler(Filters.text & ~Filters.command, register_first)],
                ASK_LAST:       [MessageHandler(Filters.text & ~Filters.command, register_last)],
                ASK_REG_PASS:   [MessageHandler(Filters.text & ~Filters.command, register_pass)]
            },
            fallbacks=[]
        ))
        dp.add_handler(ConversationHandler(
            entry_points=[CommandHandler('book', book_start)],
            states={
                ASK_DOCTOR:  [MessageHandler(Filters.text & ~Filters.command, book_doctor)],
                ASK_SERVICE: [MessageHandler(Filters.text & ~Filters.command, book_service)],
                ASK_DATE:    [MessageHandler(Filters.text & ~Filters.command, book_date)],
                ASK_TIME:    [MessageHandler(Filters.text & ~Filters.command, book_time)]
            },
            fallbacks=[]
        ))

        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("help", help_cmd))
        dp.add_handler(CommandHandler("services", services_cmd))
        dp.add_handler(CommandHandler("doctors", doctors_cmd))
        dp.add_handler(CommandHandler("myappointments", myappointments_cmd))
        dp.add_handler(CommandHandler("cancel", cancel_cmd))
        dp.add_handler(CommandHandler("profile", profile_cmd))

        # Глобальный обработчик ошибок
        import logging
        from telegram.error import NetworkError, TimedOut as PTBTimeout
        logger = logging.getLogger(__name__)
        def error_handler(update, context):
            err = context.error
            if isinstance(err, (NetworkError, PTBTimeout)):
                logger.warning(f"Network issue: {err}")
                return
            logger.exception("Unexpected error:")

        dp.add_error_handler(error_handler)

        self.stdout.write(self.style.SUCCESS("Бот запущен, polling..."))
        updater.start_polling()
        updater.idle()
