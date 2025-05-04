# clinic/management/commands/runbot.py

from django.core.management.base import BaseCommand
from django.conf import settings
from telegram import (
    Update,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove
)
from telegram.ext import (
    Updater,
    CommandHandler,
    MessageHandler,
    Filters,
    ConversationHandler,
    CallbackContext
)
from telegram.error import TimedOut
from django.utils import timezone
import datetime, pytz

from clinic.models import (
    Service, Doctor, Appointment,
    TelegramProfile, Patient
)

# стадии диалогов
ASK_PHONE, ASK_FIRST, ASK_LAST, ASK_REG_PASS = range(4)
ASK_LOGIN_PHONE, ASK_LOGIN_PASS = 4, 5
ASK_DOCTOR, ASK_SERVICE = 6, 7
ASK_DATE, ASK_TIME = 8, 9


class Command(BaseCommand):
    help = "Запускает Telegram-бота стоматологии"

    def handle(self, *args, **options):
        # --- Настройка бота ---
        updater = Updater(
            settings.TELEGRAM_BOT_TOKEN,
            use_context=True,
            request_kwargs={'read_timeout':20, 'connect_timeout':10}
        )
        dp = updater.dispatcher

        # клавиатуры
        login_menu = ReplyKeyboardMarkup(
            [['Войти', 'Зарегистрироваться']],
            resize_keyboard=True
        )
        auth_menu = ReplyKeyboardMarkup([
            ['Услуги', 'Врачи', 'Записаться'],
            ['Мои записи', 'Отменить запись'],
            ['Профиль', 'Помощь']
        ], resize_keyboard=True)

        # --- /start ---
        def start(update: Update, ctx: CallbackContext):
            update.message.reply_text(
                "👋 Добро пожаловать! Выберите действие:",
                reply_markup=login_menu
            )

        # === ЛОГИН ===
        def login_start(update: Update, ctx: CallbackContext):
            update.message.reply_text(
                "🔑 Вход: пришлите телефон (кнопка или вручную):",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Поделиться номером", request_contact=True)]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return ASK_LOGIN_PHONE

        def login_phone(update: Update, ctx: CallbackContext):
            phone = (update.effective_message.contact.phone_number
                     if update.effective_message.contact else
                     update.message.text.strip())
            ctx.user_data['login_phone'] = phone
            update.message.reply_text("Введите пароль:", reply_markup=ReplyKeyboardRemove())
            return ASK_LOGIN_PASS

        def login_pass(update: Update, ctx: CallbackContext):
            pw = update.message.text.strip()
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(phone=ctx.user_data['login_phone'])
            except User.DoesNotExist:
                update.message.reply_text(
                    "❌ Пользователь не найден. Сначала зарегистрируйтесь.",
                    reply_markup=login_menu
                )
                return ConversationHandler.END

            if not user.check_password(pw):
                update.message.reply_text("❌ Неправильный пароль.", reply_markup=login_menu)
                return ConversationHandler.END

            TelegramProfile.objects.update_or_create(
                chat_id=str(update.effective_chat.id),
                defaults={'user': user}
            )
            update.message.reply_text(
                f"✅ Вы вошли как {user.first_name} {user.last_name}",
                reply_markup=auth_menu
            )
            return ConversationHandler.END

        # === РЕГИСТРАЦИЯ ===
        def register_start(update: Update, ctx: CallbackContext):
            update.message.reply_text(
                "🖊 Регистрация: пришлите телефон:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Поделиться номером", request_contact=True)]],
                    one_time_keyboard=True,
                    resize_keyboard=True
                )
            )
            return ASK_PHONE

        def register_phone(update: Update, ctx: CallbackContext):
            phone = (update.effective_message.contact.phone_number
                     if update.effective_message.contact else
                     update.message.text.strip())
            ctx.user_data['reg_phone'] = phone
            update.message.reply_text("Введите имя:", reply_markup=ReplyKeyboardRemove())
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
            Patient.objects.create(user=user)
            TelegramProfile.objects.create(
                chat_id=str(update.effective_chat.id),
                user=user
            )
            update.message.reply_text(
                "✅ Регистрация успешна! Теперь вы – пациент.",
                reply_markup=auth_menu
            )
            return ConversationHandler.END

        # === ОБЩИЕ КОМАНДЫ ===
        def services_cmd(update: Update, ctx: CallbackContext):
            items = Service.objects.all()
            text = "\n".join(f"– {s.name} ({s.price}₸)" for s in items)
            update.message.reply_text("📋 Наши услуги:\n" + text, reply_markup=auth_menu)

        def doctors_cmd(update: Update, ctx: CallbackContext):
            docs = Doctor.objects.select_related('user').all()
            lines = [f"{d.pk}. Dr. {d.user.last_name} ({d.specialization})" for d in docs]
            try:
                update.message.reply_text(
                    "👩‍⚕️ Наши врачи:\n" + "\n".join(lines),
                    reply_markup=auth_menu
                )
            except TimedOut:
                update.message.reply_text("Сервер занят, попробуйте позже.", reply_markup=auth_menu)

        # === ЗАПИСЬ (разговорный flow) ===
        def book_start(update: Update, ctx: CallbackContext):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                update.message.reply_text("Сначала зарегистрируйтесь.", reply_markup=login_menu)
                return ConversationHandler.END

            ctx.user_data['tp'] = tp
            docs = Doctor.objects.select_related('user').all()
            kb = [[str(d.pk)] for d in docs]
            update.message.reply_text(
                "Выберите врача (номер):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_DOCTOR

        def book_doctor(update: Update, ctx: CallbackContext):
            ctx.user_data['doctor_pk'] = int(update.message.text.strip())
            svcs = Service.objects.all()
            kb = [[str(s.pk)] for s in svcs]
            update.message.reply_text(
                "Выберите услугу (номер):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_SERVICE

        def book_service(update: Update, ctx: CallbackContext):
            ctx.user_data['service_pk'] = int(update.message.text.strip())
            today = datetime.date.today()
            doctor_pk = ctx.user_data['doctor_pk']

            # собираем даты следующей недели, исключая полностью занятые
            dates = []
            for i in range(7):
                d = today + datetime.timedelta(days=i)
                if d.weekday() == 6:
                    continue  # воскресенье
                start, end = (9, 17) if d.weekday() < 5 else (9, 13)
                total_slots = end - start
                busy_count = Appointment.objects.filter(
                    doctor_id=doctor_pk,
                    date_time__date=d
                ).count()
                if busy_count < total_slots:
                    dates.append(d)

            if not dates:
                update.message.reply_text(
                    "Увы, на неделю вперед нет свободных приёмов у этого врача. Попробуйте позже.",
                    reply_markup=auth_menu
                )
                return ConversationHandler.END

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
            except ValueError:
                update.message.reply_text("Неверная дата, выберите кнопкой.", reply_markup=auth_menu)
                return ASK_DATE
            ctx.user_data['date'] = ds
            doctor_pk = ctx.user_data['doctor_pk']

            wd = date.weekday()
            start, end = (9, 17) if wd < 5 else (9, 13)

            # исключаем занятые часы
            busy_hours = [
                timezone.localtime(a.date_time).hour
                for a in Appointment.objects.filter(
                    doctor_id=doctor_pk,
                    date_time__date=date
                )
            ]
            slots = [
                f"{h:02d}:00"
                for h in range(start, end)
                if h not in busy_hours
            ]

            if not slots:
                update.message.reply_text(
                    "На выбранную дату все слоты заняты, выберите другую дату.",
                    reply_markup=auth_menu
                )
                return ASK_DATE

            kb = [[t] for t in slots]
            update.message.reply_text(
                f"Выберите время для {ds}:",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True, resize_keyboard=True)
            )
            return ASK_TIME

        def book_time(update: Update, ctx: CallbackContext):
            ts = update.message.text.strip()
            ds = ctx.user_data['date']
            try:
                dt_naive = datetime.datetime.strptime(f"{ds} {ts}", "%d.%m.%Y %H:%M")
            except ValueError:
                update.message.reply_text("Неверное время, выберите заново.", reply_markup=auth_menu)
                return ASK_TIME

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
            update.message.reply_text("✅ Запись создана!", reply_markup=auth_menu)
            return ConversationHandler.END

        # === МОИ ЗАПИСИ И ОТМЕНА ===
        def myappointments_cmd(update: Update, ctx: CallbackContext):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                return update.message.reply_text("Сначала зарегистрируйтесь.", reply_markup=login_menu)

            appts = Appointment.objects.filter(patient=tp.user.patient)
            if not appts:
                return update.message.reply_text("У вас нет записей.", reply_markup=auth_menu)

            lines = []
            for a in appts:
                local_dt = timezone.localtime(a.date_time)
                lines.append(f"{a.pk}. {a.service.name} — {local_dt.strftime('%d.%m.%Y %H:%M')}")
            update.message.reply_text(
                "Ваши записи:\n" + "\n".join(lines) + "\nОтменить запись: Отменить запись <номер>",
                reply_markup=auth_menu
            )

        def cancel_cmd(update: Update, ctx: CallbackContext):
            parts = update.message.text.split()
            if len(parts) != 2 or not parts[1].isdigit():
                return update.message.reply_text("Используйте: Отменить запись <номер>", reply_markup=auth_menu)
            pk = int(parts[1])
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
                Appointment.objects.get(pk=pk, patient=tp.user.patient).delete()
                update.message.reply_text("❌ Запись отменена.", reply_markup=auth_menu)
            except Appointment.DoesNotExist:
                update.message.reply_text("Не нашли запись.", reply_markup=auth_menu)

        def profile_cmd(update: Update, ctx: CallbackContext):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                return update.message.reply_text("Сначала зарегистрируйтесь.", reply_markup=login_menu)
            u = tp.user
            update.message.reply_text(
                f"👤 Профиль:\nИмя: {u.first_name}\nФамилия: {u.last_name}\nТелефон: {u.phone}",
                reply_markup=auth_menu
            )

        def help_cmd(update: Update, ctx: CallbackContext):
            update.message.reply_text(
                "Доступные действия:\n"
                "Услуги | Врачи | Записаться | Мои записи | Отменить запись | Профиль | Помощь",
                reply_markup=auth_menu
            )

        # --- ConversationHandler для логина ---
        conv_login = ConversationHandler(
            entry_points=[
                CommandHandler('login', login_start),
                MessageHandler(Filters.regex('^Войти$'), login_start),
            ],
            states={
                ASK_LOGIN_PHONE: [MessageHandler(Filters.contact | (Filters.text & ~Filters.command), login_phone)],
                ASK_LOGIN_PASS:  [MessageHandler(Filters.text & ~Filters.command, login_pass)],
            },
            fallbacks=[],
        )
        dp.add_handler(conv_login)

        # --- ConversationHandler для регистрации ---
        conv_register = ConversationHandler(
            entry_points=[
                CommandHandler('register', register_start),
                MessageHandler(Filters.regex('^Зарегистрироваться$'), register_start),
            ],
            states={
                ASK_PHONE:      [MessageHandler(Filters.contact | (Filters.text & ~Filters.command), register_phone)],
                ASK_FIRST:      [MessageHandler(Filters.text & ~Filters.command, register_first)],
                ASK_LAST:       [MessageHandler(Filters.text & ~Filters.command, register_last)],
                ASK_REG_PASS:   [MessageHandler(Filters.text & ~Filters.command, register_pass)],
            },
            fallbacks=[],
        )
        dp.add_handler(conv_register)

        # --- ConversationHandler для записи ---
        conv_book = ConversationHandler(
            entry_points=[
                MessageHandler(Filters.regex('^Записаться$'), book_start),
                CommandHandler('book', book_start),
            ],
            states={
                ASK_DOCTOR:  [MessageHandler(Filters.text & ~Filters.command, book_doctor)],
                ASK_SERVICE: [MessageHandler(Filters.text & ~Filters.command, book_service)],
                ASK_DATE:    [MessageHandler(Filters.text & ~Filters.command, book_date)],
                ASK_TIME:    [MessageHandler(Filters.text & ~Filters.command, book_time)],
            },
            fallbacks=[],
        )
        dp.add_handler(conv_book)

        # --- Простые кнопки после авторизации ---
        dp.add_handler(MessageHandler(Filters.regex('^Услуги$'), services_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Врачи$'), doctors_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Мои записи$'), myappointments_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Отменить запись'), cancel_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Профиль$'), profile_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Помощь$'), help_cmd))

        # --- Одиночные команды на всякий случай ---
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("help", help_cmd))
        dp.add_handler(CommandHandler("services", services_cmd))
        dp.add_handler(CommandHandler("doctors", doctors_cmd))
        dp.add_handler(CommandHandler("myappointments", myappointments_cmd))
        dp.add_handler(CommandHandler("cancel", cancel_cmd))
        dp.add_handler(CommandHandler("profile", profile_cmd))

        # глобальный обработчик ошибок
        import logging
        from telegram.error import NetworkError, TimedOut as PTBTimeout
        logger = logging.getLogger(__name__)

        def error_handler(update, context):
            err = context.error
            if isinstance(err, (NetworkError, PTBTimeout)):
                logger.warning(f"Network issue: {err}")
            else:
                logger.exception("Unexpected error:")

        dp.add_error_handler(error_handler)

        # запускаем
        self.stdout.write(self.style.SUCCESS("Бот запущен, polling..."))
        updater.start_polling()
        updater.idle()
