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
import datetime

from clinic.models import (
    Service, Doctor, Appointment,
    TelegramProfile, Patient
)

# стадии диалогов
ASK_PHONE, ASK_FIRST, ASK_LAST, ASK_REG_PASS = range(4)
ASK_LOGIN_PHONE, ASK_LOGIN_PASS = 4, 5
ASK_DOCTOR, ASK_SERVICE = 6, 7
ASK_DATE, ASK_TIME = 8, 9
ASK_CANCEL = 10  # ← новая стадия для отмены

class Command(BaseCommand):
    help = "Запускает Telegram-бота стоматологии"

    def handle(self, *args, **options):
        updater = Updater(
            settings.TELEGRAM_BOT_TOKEN,
            use_context=True,
            request_kwargs={'read_timeout':20,'connect_timeout':10}
        )
        dp = updater.dispatcher

        login_menu = ReplyKeyboardMarkup(
            [['Войти', 'Зарегистрироваться']],
            resize_keyboard=True
        )
        auth_menu = ReplyKeyboardMarkup([
            ['Услуги', 'Врачи', 'Записаться'],
            ['Мои записи', 'Отменить запись'],
            ['Профиль', 'Помощь']
        ], resize_keyboard=True)

        def start(update: Update, ctx: CallbackContext):
            update.message.reply_text(
                "👋 Добро пожаловать! Выберите действие:",
                reply_markup=login_menu
            )

        # — ЛОГИН —
        def login_start(update, ctx):
            update.message.reply_text(
                "🔑 Вход: пришлите телефон:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Поделиться номером", request_contact=True)]],
                    one_time_keyboard=True, resize_keyboard=True
                )
            )
            return ASK_LOGIN_PHONE

        def login_phone(update, ctx):
            if update.effective_message.contact:
                phone = update.effective_message.contact.phone_number
            else:
                phone = update.message.text.strip()
            ctx.user_data['login_phone'] = phone
            update.message.reply_text("Введите пароль:", reply_markup=ReplyKeyboardRemove())
            return ASK_LOGIN_PASS

        def login_pass(update, ctx):
            pw = update.message.text.strip()
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(phone=ctx.user_data['login_phone'])
            except User.DoesNotExist:
                update.message.reply_text("❌ Пользователь не найден.", reply_markup=login_menu)
                return ConversationHandler.END
            if not user.check_password(pw):
                update.message.reply_text("❌ Неправильный пароль.", reply_markup=login_menu)
                return ConversationHandler.END

            TelegramProfile.objects.update_or_create(
                chat_id=str(update.effective_chat.id),
                defaults={'user': user}
            )
            update.message.reply_text(f"✅ Вы вошли как {user.first_name} {user.last_name}",
                                      reply_markup=auth_menu)
            return ConversationHandler.END

        # — РЕГИСТРАЦИЯ —
        def register_start(update, ctx):
            update.message.reply_text(
                "🖊 Регистрация: пришлите телефон:",
                reply_markup=ReplyKeyboardMarkup(
                    [[KeyboardButton("Поделиться номером", request_contact=True)]],
                    one_time_keyboard=True, resize_keyboard=True
                )
            )
            return ASK_PHONE

        def register_phone(update, ctx):
            if update.effective_message.contact:
                phone = update.effective_message.contact.phone_number
            else:
                phone = update.message.text.strip()
            ctx.user_data['reg_phone'] = phone
            update.message.reply_text("Введите имя:", reply_markup=ReplyKeyboardRemove())
            return ASK_FIRST

        def register_first(update, ctx):
            ctx.user_data['reg_first'] = update.message.text.strip()
            update.message.reply_text("Введите фамилию:")
            return ASK_LAST

        def register_last(update, ctx):
            ctx.user_data['reg_last'] = update.message.text.strip()
            update.message.reply_text("Придумайте пароль:")
            return ASK_REG_PASS

        def register_pass(update, ctx):
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
            TelegramProfile.objects.create(chat_id=str(update.effective_chat.id), user=user)
            update.message.reply_text("✅ Вы зарегистрированы!", reply_markup=auth_menu)
            return ConversationHandler.END

        # — ОБЩИЕ КОМАНДЫ —
        def services_cmd(update, ctx):
            items = Service.objects.all()
            text = "\n".join(f"– {s.name} ({s.price}₸)" for s in items)
            update.message.reply_text("📋 Наши услуги:\n" + text, reply_markup=auth_menu)

        def doctors_cmd(update, ctx):
            docs = Doctor.objects.select_related('user').all()
            lines = [f"{d.user.first_name} {d.user.patronymic} — {d.specialization}" for d in docs]
            update.message.reply_text("👩‍⚕️ Наши врачи:\n" + "\n".join(lines), reply_markup=auth_menu)

        # — ЗАПИСЬ (flow) —
        def book_start(update, ctx):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                update.message.reply_text("Сначала войдите или зарегистрируйтесь.", reply_markup=login_menu)
                return ConversationHandler.END

            ctx.user_data['tp'] = tp
            docs = Doctor.objects.select_related('user').all()
            doctor_map = {}
            kb = []
            for d in docs:
                name = f"{d.user.first_name} {d.user.patronymic}"
                doctor_map[name] = d.pk
                kb.append([name])
            ctx.user_data['doctor_map'] = doctor_map
            update.message.reply_text("Выберите врача:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True))
            return ASK_DOCTOR

        def book_doctor(update, ctx):
            sel = update.message.text.strip()
            doctor_pk = ctx.user_data['doctor_map'].get(sel)
            if not doctor_pk:
                update.message.reply_text("Нажмите кнопку с именем врача.")
                return ASK_DOCTOR
            ctx.user_data['doctor_pk'] = doctor_pk

            svcs = Service.objects.all()
            svc_map = {}
            kb = []
            for s in svcs:
                svc_map[s.name] = s.pk
                kb.append([s.name])
            ctx.user_data['svc_map'] = svc_map
            update.message.reply_text("Выберите услугу:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True))
            return ASK_SERVICE

        def book_service(update, ctx):
            sel = update.message.text.strip()
            svc_pk = ctx.user_data['svc_map'].get(sel)
            if not svc_pk:
                update.message.reply_text("Нажмите кнопку с названием услуги.")
                return ASK_SERVICE
            ctx.user_data['service_pk'] = svc_pk

            today = datetime.date.today()
            doctor_pk = ctx.user_data['doctor_pk']
            dates = []
            for i in range(7):
                d = today + datetime.timedelta(days=i)
                if d.weekday() == 6:
                    continue
                start, end = (9,17) if d.weekday()<5 else (9,13)
                if Appointment.objects.filter(doctor_id=doctor_pk, date_time__date=d).count() < (end-start):
                    dates.append(d)
            if not dates:
                update.message.reply_text("Нет свободных приёмов на неделю.", reply_markup=auth_menu)
                return ConversationHandler.END

            kb = [[d.strftime("%d.%m.%Y")] for d in dates]
            update.message.reply_text("Выберите дату:", reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True))
            return ASK_DATE

        def book_date(update, ctx):
            ds = update.message.text.strip()
            try:
                date = datetime.datetime.strptime(ds, "%d.%m.%Y").date()
            except ValueError:
                update.message.reply_text("Нажмите кнопку с датой.", reply_markup=auth_menu)
                return ASK_DATE
            ctx.user_data['date'] = ds
            wd = date.weekday()
            start, end = (9,17) if wd<5 else (9,13)

            busy = [
                timezone.localtime(a.date_time).hour
                for a in Appointment.objects.filter(
                    doctor_id=ctx.user_data['doctor_pk'],
                    date_time__date=date
                )
            ]
            slots = [f"{h:02d}:00" for h in range(start,end) if h not in busy]
            if not slots:
                update.message.reply_text("Все слоты заняты.", reply_markup=auth_menu)
                return ASK_DATE

            kb = [[t] for t in slots]
            update.message.reply_text(f"Выберите время для {ds}:",
                                      reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True))
            return ASK_TIME

        def book_time(update, ctx):
            ts = update.message.text.strip()
            ds = ctx.user_data['date']
            try:
                dt_naive = datetime.datetime.strptime(f"{ds} {ts}", "%d.%m.%Y %H:%M")
            except ValueError:
                update.message.reply_text("Нажмите кнопку с временем.", reply_markup=auth_menu)
                return ASK_TIME

            dt = timezone.make_aware(dt_naive)
            Appointment.objects.create(
                patient=ctx.user_data['tp'].user.patient,
                doctor=Doctor.objects.get(pk=ctx.user_data['doctor_pk']),
                service=Service.objects.get(pk=ctx.user_data['service_pk']),
                date_time=dt
            )
            update.message.reply_text("✅ Запись создана!", reply_markup=auth_menu)
            return ConversationHandler.END

        # — Мои записи —
        def myappointments_cmd(update, ctx):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                return update.message.reply_text("Сначала войдите.", reply_markup=login_menu)

            appts = Appointment.objects.filter(patient=tp.user.patient)
            if not appts:
                return update.message.reply_text("У вас нет записей.", reply_markup=auth_menu)

            lines = [
                f"{a.pk}. {a.service.name} — {timezone.localtime(a.date_time).strftime('%d.%m.%Y %H:%M')}"
                for a in appts
            ]
            update.message.reply_text(
                "Ваши записи:\n" + "\n".join(lines) + 
                "\n\nНажмите «Отменить запись», чтобы удалить одну из них.",
                reply_markup=auth_menu
            )

        # — ОТМЕНА записи через отдельный flow —
        def cancel_start(update, ctx):
            # выводим список и переходим в ASK_CANCEL
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                return update.message.reply_text("Сначала войдите.", reply_markup=login_menu)

            appts = Appointment.objects.filter(patient=tp.user.patient)
            if not appts:
                return update.message.reply_text("У вас нет записей.", reply_markup=auth_menu)

            lines = [
                f"{a.pk}. {a.service.name} у Dr. {a.doctor.user.last_name} — "
                f"{timezone.localtime(a.date_time).strftime('%d.%m.%Y %H:%M')}"
                for a in appts
            ]
            update.message.reply_text(
                "Ваши записи:\n" + "\n".join(lines) +
                "\n\nВведите номер записи для отмены:",
                reply_markup=ReplyKeyboardRemove()
            )
            return ASK_CANCEL

        def cancel_confirm(update, ctx):
            text = update.message.text.strip()
            if not text.isdigit():
                update.message.reply_text("Пожалуйста, введите цифру № записи.")
                return ASK_CANCEL
            pk = int(text)
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
                appt = Appointment.objects.get(pk=pk, patient=tp.user.patient)
            except (TelegramProfile.DoesNotExist, Appointment.DoesNotExist):
                update.message.reply_text("Запись с таким номером не найдена.")
                return ASK_CANCEL

            appt.delete()
            update.message.reply_text("❌ Запись отменена.", reply_markup=auth_menu)
            return ConversationHandler.END

        def profile_cmd(update, ctx):
            tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            u = tp.user
            update.message.reply_text(
                f"👤 Профиль:\nИмя: {u.first_name}\nФамилия: {u.last_name}\nТелефон: {u.phone}",
                reply_markup=auth_menu
            )

        def help_cmd(update, ctx):
            update.message.reply_text(
                "Доступные действия:\n"
                "Услуги | Врачи | Записаться | Мои записи | Отменить запись | Профиль | Помощь",
                reply_markup=auth_menu
            )

        # ConversationHandler-ы
        conv_login = ConversationHandler(
            entry_points=[
                CommandHandler('login', login_start),
                MessageHandler(Filters.regex('^Войти$'), login_start)
            ],
            states={
                ASK_LOGIN_PHONE: [MessageHandler(Filters.contact | (Filters.text & ~Filters.command), login_phone)],
                ASK_LOGIN_PASS:  [MessageHandler(Filters.text & ~Filters.command, login_pass)],
            },
            fallbacks=[]
        )
        dp.add_handler(conv_login)

        conv_register = ConversationHandler(
            entry_points=[
                CommandHandler('register', register_start),
                MessageHandler(Filters.regex('^Зарегистрироваться$'), register_start)
            ],
            states={
                ASK_PHONE:    [MessageHandler(Filters.contact | (Filters.text & ~Filters.command), register_phone)],
                ASK_FIRST:    [MessageHandler(Filters.text & ~Filters.command, register_first)],
                ASK_LAST:     [MessageHandler(Filters.text & ~Filters.command, register_last)],
                ASK_REG_PASS: [MessageHandler(Filters.text & ~Filters.command, register_pass)],
            },
            fallbacks=[]
        )
        dp.add_handler(conv_register)

        conv_book = ConversationHandler(
            entry_points=[
                MessageHandler(Filters.regex('^Записаться$'), book_start),
                CommandHandler('book', book_start)
            ],
            states={
                ASK_DOCTOR:  [MessageHandler(Filters.text & ~Filters.command, book_doctor)],
                ASK_SERVICE: [MessageHandler(Filters.text & ~Filters.command, book_service)],
                ASK_DATE:    [MessageHandler(Filters.text & ~Filters.command, book_date)],
                ASK_TIME:    [MessageHandler(Filters.text & ~Filters.command, book_time)],
            },
            fallbacks=[]
        )
        dp.add_handler(conv_book)

        # новый ConversationHandler для отмены
        conv_cancel = ConversationHandler(
            entry_points=[MessageHandler(Filters.regex('^Отменить запись$'), cancel_start)],
            states={ASK_CANCEL: [MessageHandler(Filters.text & ~Filters.command, cancel_confirm)]},
            fallbacks=[]
        )
        dp.add_handler(conv_cancel)

        # простые кнопки после авторизации
        dp.add_handler(MessageHandler(Filters.regex('^Услуги$'), services_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Врачи$'), doctors_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Мои записи$'), myappointments_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Профиль$'), profile_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Помощь$'), help_cmd))

        # одиночные команды
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("help", help_cmd))

        # глобальный обработчик ошибок
        import logging
        from telegram.error import NetworkError, TimedOut as PTBTimeout
        logger = logging.getLogger(__name__)
        dp.add_error_handler(lambda u,c: logger.warning(c.error) 
                             if isinstance(c.error,(NetworkError,PTBTimeout)) 
                             else logger.exception(c.error))

        self.stdout.write(self.style.SUCCESS("Бот запущен, polling..."))
        updater.start_polling()
        updater.idle()
