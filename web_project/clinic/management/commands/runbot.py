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
from django.utils import timezone
import datetime

from clinic.models import (
    Service, ServiceCategory, Doctor, Appointment,
    TelegramProfile, Patient
)

# стадии диалогов
ASK_PHONE, ASK_FIRST, ASK_LAST, ASK_REG_PASS = range(4)
ASK_LOGIN_PHONE, ASK_LOGIN_PASS = 4, 5
ASK_DOCTOR, ASK_CATEGORY_OR_SERVICE, ASK_SERVICE_IN_CATEGORY = 6, 7, 8
ASK_DATE, ASK_TIME = 9, 10
ASK_CANCEL = 11  # новая стадия для отмены

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
            update.message.reply_text(
                f"✅ Вы вошли как {user.first_name} {user.last_name}",
                reply_markup=auth_menu
            )
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

        # — КОМАНДА: УСЛУГИ —
        def services_cmd(update, ctx):
            categories = ServiceCategory.objects.prefetch_related('services').order_by('name')
            lines = []

            uncategorized = Service.objects.filter(category__isnull=True).order_by('name')
            if uncategorized.exists():
                for s in uncategorized:
                    lines.append(f"– {s.name} ({s.price}₸)")
                lines.append("")

            for cat in categories:
                svc_list = cat.services.all().order_by('name')
                if not svc_list:
                    continue
                lines.append(f"🦷 {cat.name}:")
                for s in svc_list:
                    lines.append(f"– {s.name} ({s.price}₸)")
                lines.append("")

            text = "\n".join(lines).strip()
            if not text:
                text = "Услуг нет."
            update.message.reply_text("📋 Наши услуги:\n\n" + text, reply_markup=auth_menu)

        # — КОМАНДА: ВРАЧИ —
        def doctors_cmd(update, ctx):
            docs = Doctor.objects.select_related('user').all()
            lines = [f"{d.user.first_name} {d.user.patronymic} — {d.specialization}" for d in docs]
            if not lines:
                update.message.reply_text("Врачи не найдены.", reply_markup=auth_menu)
            else:
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
            if not docs:
                update.message.reply_text("Врачи пока не добавлены.", reply_markup=auth_menu)
                return ConversationHandler.END

            doctor_map = {}
            kb = []
            for d in docs:
                name = f"{d.user.first_name} {d.user.patronymic}"
                doctor_map[name] = d.pk
                kb.append([name])
            kb.append(["Отмена"])

            ctx.user_data['doctor_map'] = doctor_map
            update.message.reply_text(
                "Выберите врача:",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_DOCTOR

        def book_doctor(update, ctx):
            sel = update.message.text.strip()
            if sel == "Отмена":
                update.message.reply_text(
                    "❌ Отменено. Возвращаю вас в главное меню.",
                    reply_markup=auth_menu
                )
                return ConversationHandler.END

            doctor_pk = ctx.user_data['doctor_map'].get(sel)
            if not doctor_pk:
                update.message.reply_text("Нажмите кнопку с именем врача (или «Отмена»).")
                return ASK_DOCTOR
            ctx.user_data['doctor_pk'] = doctor_pk

            # подготавливаем uncategorized и категории
            uncategorized = Service.objects.filter(category__isnull=True).order_by('name')
            categories = ServiceCategory.objects.prefetch_related('services').filter(services__isnull=False).distinct().order_by('name')

            svc_map = {}
            kb = []
            # 1) сразу все услуги без категории
            for s in uncategorized:
                svc_map[s.name] = s.pk
                kb.append([s.name])
            # 2) кнопки категорий
            for cat in categories:
                kb.append([cat.name])
            kb.append(["Отмена"])

            # сохраняем обе карты
            ctx.user_data['svc_map_uncat'] = {s.name: s.pk for s in uncategorized}
            ctx.user_data['category_map'] = {cat.name: cat.pk for cat in categories}
            ctx.user_data['svc_map'] = svc_map  # для uncategorized
            update.message.reply_text(
                "Выберите услугу:",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_CATEGORY_OR_SERVICE

        def book_category_or_service(update, ctx):
            sel = update.message.text.strip()
            # если отмена
            if sel == "Отмена":
                update.message.reply_text(
                    "❌ Отменено. Возвращаю вас в главное меню.",
                    reply_markup=auth_menu
                )
                return ConversationHandler.END

            # если выбрали услугу без категории
            unc_map = ctx.user_data.get('svc_map_uncat', {})
            if sel in unc_map:
                ctx.user_data['service_pk'] = unc_map[sel]
                return go_to_date_stage(update, ctx)

            # иначе проверяем – выбрана ли категория?
            cat_map = ctx.user_data.get('category_map', {})
            cat_pk = cat_map.get(sel)
            if not cat_pk:
                update.message.reply_text("Нажмите кнопку с названием услуги или категории (или «Отмена»).")
                return ASK_CATEGORY_OR_SERVICE

            # если выбрана категория — показываем её услуги
            svc_qs = Service.objects.filter(category_id=cat_pk).order_by('name')
            if not svc_qs.exists():
                update.message.reply_text("В этой категории нет услуг.", reply_markup=auth_menu)
                return ConversationHandler.END

            svc_map = {}
            kb = []
            for s in svc_qs:
                svc_map[s.name] = s.pk
                kb.append([s.name])
            kb.append(["Назад", "Отмена"])

            ctx.user_data['svc_map_cat'] = svc_map
            update.message.reply_text(
                f"Услуги категории «{sel}» (или «Назад»/«Отмена»):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_SERVICE_IN_CATEGORY

        def book_service_in_category(update, ctx):
            sel = update.message.text.strip()
            # кнопка «Назад» возвращает к выбору uncategorized+категорий
            if sel == "Назад":
                return back_to_category_prompt(update, ctx)
            # кнопка «Отмена» завершает
            if sel == "Отмена":
                update.message.reply_text(
                    "❌ Отменено. Возвращаю вас в главное меню.",
                    reply_markup=auth_menu
                )
                return ConversationHandler.END

            svc_map_cat = ctx.user_data.get('svc_map_cat', {})
            svc_pk = svc_map_cat.get(sel)
            if not svc_pk:
                update.message.reply_text("Нажмите кнопку с названием услуги, «Назад» или «Отмена».")
                return ASK_SERVICE_IN_CATEGORY

            ctx.user_data['service_pk'] = svc_pk
            return go_to_date_stage(update, ctx)

        def go_to_date_stage(update, ctx):
            # Универсальная часть — выбор даты
            today = datetime.date.today()
            doctor_pk = ctx.user_data['doctor_pk']
            dates = []
            for i in range(7):
                d = today + datetime.timedelta(days=i)
                if d.weekday() == 6:  # воскресенье пропускаем
                    continue
                start, end = (9, 17) if d.weekday() < 5 else (9, 13)
                taken = Appointment.objects.filter(doctor_id=doctor_pk, date_time__date=d).count()
                if taken < (end - start):
                    dates.append(d)

            if not dates:
                update.message.reply_text("Нет свободных приёмов на неделю.", reply_markup=auth_menu)
                return ConversationHandler.END

            kb = [[d.strftime("%d.%m.%Y")] for d in dates]
            kb.append(["Отмена"])
            ctx.user_data['date_options'] = [d.strftime("%d.%m.%Y") for d in dates]
            update.message.reply_text(
                "Выберите дату (или «Отмена»):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_DATE

        def back_to_category_prompt(update, ctx):
            # возвращает клавиатуру uncategorized + категории
            uncategorized = Service.objects.filter(category__isnull=True).order_by('name')
            categories = ServiceCategory.objects.prefetch_related('services').filter(services__isnull=False).distinct().order_by('name')

            kb = []
            for s in uncategorized:
                kb.append([s.name])
            for cat in categories:
                kb.append([cat.name])
            kb.append(["Отмена"])

            ctx.user_data['svc_map_uncat'] = {s.name: s.pk for s in uncategorized}
            ctx.user_data['category_map'] = {cat.name: cat.pk for cat in categories}
            ctx.user_data['svc_map'] = {}  # сбрасываем
            update.message.reply_text(
                "Выберите услугу без категории или категорию (или «Отмена»):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_CATEGORY_OR_SERVICE

        def book_date(update, ctx):
            ds = update.message.text.strip()
            if ds == "Отмена":
                update.message.reply_text(
                    "❌ Отменено. Возвращаю вас в главное меню.",
                    reply_markup=auth_menu
                )
                return ConversationHandler.END

            if ds not in ctx.user_data.get('date_options', []):
                update.message.reply_text("Нажмите кнопку с датой (или «Отмена»).")
                return ASK_DATE
            ctx.user_data['date'] = ds

            # Получаем выбранную дату и определяем рабочие часы
            date = datetime.datetime.strptime(ds, "%d.%m.%Y").date()
            wd = date.weekday()
            start, end = (9, 17) if wd < 5 else (9, 13)

            # Список занятых часов у врача на эту дату
            busy = [
                timezone.localtime(a.date_time).hour
                for a in Appointment.objects.filter(
                    doctor_id=ctx.user_data['doctor_pk'],
                    date_time__date=date
                )
            ]

            # — ИЗМЕНЕНИЕ: убираем прошедшие слоты, если date == сегодня
            now_local = timezone.localtime(timezone.now())
            if date == now_local.date():
                # Берём только часы строго позже текущего часа
                available_hours = [
                    h for h in range(start, end)
                    if h not in busy and h > now_local.hour
                ]
            else:
                available_hours = [
                    h for h in range(start, end)
                    if h not in busy
                ]

            slots = [f"{h:02d}:00" for h in available_hours]

            if not slots:
                update.message.reply_text("Все слоты заняты (или уже прошли).", reply_markup=auth_menu)
                return ConversationHandler.END

            kb = [[t] for t in slots]
            kb.append(["Отмена"])
            ctx.user_data['time_options'] = slots
            update.message.reply_text(
                f"Выберите время для {ds} (или «Отмена»):",
                reply_markup=ReplyKeyboardMarkup(kb, one_time_keyboard=True)
            )
            return ASK_TIME

        def book_time(update, ctx):
            ts = update.message.text.strip()
            if ts == "Отмена":
                update.message.reply_text(
                    "❌ Отменено. Возвращаю вас в главное меню.",
                    reply_markup=auth_menu
                )
                return ConversationHandler.END

            if ts not in ctx.user_data.get('time_options', []):
                update.message.reply_text("Нажмите кнопку с временем (или «Отмена»).")
                return ASK_TIME

            ds = ctx.user_data['date']
            dt_naive = datetime.datetime.strptime(f"{ds} {ts}", "%d.%m.%Y %H:%M")
            dt = timezone.make_aware(dt_naive)

            Appointment.objects.create(
                patient=ctx.user_data['tp'].user.patient,
                doctor=Doctor.objects.get(pk=ctx.user_data['doctor_pk']),
                service=Service.objects.get(pk=ctx.user_data['service_pk']),
                date_time=dt
            )
            update.message.reply_text("✅ Запись создана!", reply_markup=auth_menu)
            return ConversationHandler.END

        # — МОИ ЗАПИСИ —
        def myappointments_cmd(update, ctx):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                return update.message.reply_text("Сначала войдите.", reply_markup=login_menu)

            # — ИЗМЕНЕНИЕ: показываем только будущие приёмы (>= сейчас)
            now = timezone.now()
            appts = Appointment.objects.filter(
                patient=tp.user.patient,
                date_time__gte=now
            ).order_by('date_time')

            if not appts:
                return update.message.reply_text("У вас нет предстоящих записей.", reply_markup=auth_menu)

            lines = [
                f"{a.pk}. {a.service.name} — {timezone.localtime(a.date_time).strftime('%d.%m.%Y %H:%M')}"
                for a in appts
            ]
            update.message.reply_text(
                "Ваши предстоящие записи:\n" + "\n".join(lines) +
                "\n\nНажмите «Отменить запись», чтобы удалить одну из них.",
                reply_markup=auth_menu
            )

        # — ОТМЕНА записи —
        def cancel_start(update, ctx):
            try:
                tp = TelegramProfile.objects.get(chat_id=str(update.effective_chat.id))
            except TelegramProfile.DoesNotExist:
                return update.message.reply_text("Сначала войдите.", reply_markup=login_menu)

            # — ИЗМЕНЕНИЕ: показываем только будущие приёмы
            now = timezone.now()
            appts = Appointment.objects.filter(
                patient=tp.user.patient,
                date_time__gte=now
            ).order_by('date_time')

            if not appts:
                return update.message.reply_text("У вас нет предстоящих записей для отмены.", reply_markup=auth_menu)

            lines = [
                f"{a.pk}. {a.service.name} у Dr. {a.doctor.user.last_name} — "
                f"{timezone.localtime(a.date_time).strftime('%d.%m.%Y %H:%M')}"
                for a in appts
            ]
            update.message.reply_text(
                "Ваши предстоящие записи:\n" + "\n".join(lines) +
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

            # — ИЗМЕНЕНИЕ: дополнительно проверяем, что запись ещё не прошла
            if appt.date_time < timezone.now():
                update.message.reply_text("❌ Нельзя отменить уже прошедший приём.", reply_markup=auth_menu)
                return ConversationHandler.END

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

        # Регистрация ConversationHandler-ов
        conv_login = ConversationHandler(
            entry_points=[
                CommandHandler('login', login_start),
                MessageHandler(Filters.regex('^Войти$'),    login_start)
            ],
            states={
                ASK_LOGIN_PHONE: [MessageHandler(Filters.contact | (Filters.text & ~Filters.command),    login_phone)],
                ASK_LOGIN_PASS:  [MessageHandler(Filters.text & ~Filters.command,    login_pass)],
            },
            fallbacks=[]
        )
        dp.add_handler(conv_login)

        conv_register = ConversationHandler(
            entry_points=[
                CommandHandler('register', register_start),
                MessageHandler(Filters.regex('^Зарегистрироваться$'),    register_start)
            ],
            states={
                ASK_PHONE:    [MessageHandler(Filters.contact | (Filters.text & ~Filters.command),    register_phone)],
                ASK_FIRST:    [MessageHandler(Filters.text & ~Filters.command,    register_first)],
                ASK_LAST:     [MessageHandler(Filters.text & ~Filters.command,    register_last)],
                ASK_REG_PASS: [MessageHandler(Filters.text & ~Filters.command,    register_pass)],
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
                ASK_DOCTOR:             [MessageHandler(Filters.text & ~Filters.command,    book_doctor)],
                ASK_CATEGORY_OR_SERVICE: [MessageHandler(Filters.text & ~Filters.command,    book_category_or_service)],
                ASK_SERVICE_IN_CATEGORY: [MessageHandler(Filters.text & ~Filters.command,    book_service_in_category)],
                ASK_DATE:               [MessageHandler(Filters.text & ~Filters.command,    book_date)],
                ASK_TIME:               [MessageHandler(Filters.text & ~Filters.command,    book_time)],
            },
            fallbacks=[]
        )
        dp.add_handler(conv_book)

        conv_cancel = ConversationHandler(
            entry_points=[MessageHandler(Filters.regex('^Отменить запись$'),    cancel_start)],
            states={ASK_CANCEL: [MessageHandler(Filters.text & ~Filters.command,    cancel_confirm)]},
            fallbacks=[]
        )
        dp.add_handler(conv_cancel)

        # Привязываем остальные команды-кнопки
        dp.add_handler(MessageHandler(Filters.regex('^Услуги$'),    services_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Врачи$'),    doctors_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Мои записи$'),    myappointments_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Профиль$'),    profile_cmd))
        dp.add_handler(MessageHandler(Filters.regex('^Помощь$'),    help_cmd))

        # Одиночные команды
        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("help", help_cmd))

        # Обработчик ошибок
        import logging
        from telegram.error import NetworkError, TimedOut as PTBTimeout
        logger = logging.getLogger(__name__)
        dp.add_error_handler(lambda u, c: logger.warning(c.error)
                             if isinstance(c.error, (NetworkError, PTBTimeout))
                             else logger.exception(c.error))

        self.stdout.write(self.style.SUCCESS("Бот запущен, polling..."))
        updater.start_polling()
        updater.idle()
