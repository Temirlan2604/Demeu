from django.core.management.base import BaseCommand
from django.conf import settings
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, CallbackContext

class Command(BaseCommand):
    help = "Запускает Telegram-бота стоматологии"

    def handle(self, *args, **options):
        token = settings.TELEGRAM_BOT_TOKEN
        updater = Updater(token, use_context=True)
        dp = updater.dispatcher

        # /start
        def start(update: Update, context: CallbackContext):
            update.message.reply_text(
                "👋 Привет! Я бот клиники «Демеу Ер-тіс». "
                "Я могу показать список услуг (/services) и врачей (/doctors)."
            )

        # /services
        def services(update: Update, context: CallbackContext):
            from clinic.models import Service
            items = Service.objects.all()
            text = "\n".join(f"– {s.name} ({s.price} ₸)" for s in items)
            update.message.reply_text(f"Наши услуги:\n{text}")

        # /doctors
        def doctors(update: Update, context: CallbackContext):
            from clinic.models import Doctor
            items = Doctor.objects.select_related('user').all()
            text = "\n".join(
                f"– Dr. {d.user.last_name} ({d.specialization})"
                for d in items
            )
            update.message.reply_text(f"Наши врачи:\n{text}")

        dp.add_handler(CommandHandler("start", start))
        dp.add_handler(CommandHandler("services", services))
        dp.add_handler(CommandHandler("doctors", doctors))

        self.stdout.write(self.style.SUCCESS("Бот запущен, ждём сообщений…"))
        updater.start_polling()
        updater.idle()
