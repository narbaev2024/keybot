import telebot
from datetime import datetime
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import logging
from telebot import types  # Импортируем types для кнопок

logging.basicConfig(level=logging.INFO)

timezone = pytz.timezone('Asia/Bishkek')

API_TOKEN = '7370432818:AAELlwGFnwnq0J7flE1gZsDhyG3wnJRuaCY'
bot = telebot.TeleBot(API_TOKEN)

user_states = {}

# Подключение к базе данных
try:
    conn = psycopg2.connect(
        dbname='keybot',
        user='postgres',
        password='adminadmin',
        host='localhost',
        port='5432'
    )
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS certificates (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            user_name TEXT,
            certificate_name TEXT,
            certificate_key TEXT,
            expiration_date DATE
        );
    ''')
    conn.commit()
    logging.info("Успешное подключение к базе данных и создание таблицы.")
except Exception as e:
    logging.error(f"Ошибка подключения к базе данных: {e}")
    exit()


@bot.message_handler(commands=['start'])
def start_command(message):
    show_menu(message)


def show_menu(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    button_add = types.KeyboardButton("/добавить")
    button_remove = types.KeyboardButton("/удалить")
    button_check = types.KeyboardButton("/сертификаты")
    button_help = types.KeyboardButton("/help")

    markup.add(button_add, button_remove, button_check, button_help)
    bot.send_message(message.chat.id, "Выберите команду:", reply_markup=markup)


@bot.message_handler(commands=['добавить'])
def start_add_certificate(message):
    user_states[message.from_user.id] = {'step': 1}
    bot.reply_to(message, "Введите название сертификата:")


@bot.message_handler(func=lambda message: message.from_user.id in user_states)
def handle_add_certificate_input(message):
    user_id = message.from_user.id
    step = user_states[user_id]['step']

    if step == 1:
        user_states[user_id]['certificate_name'] = message.text
        user_states[user_id]['step'] = 2
        bot.reply_to(message, "Введите ключ сертификата:")
    elif step == 2:  # Ввод ключа сертификата
        user_states[user_id]['certificate_key'] = message.text
        user_states[user_id]['step'] = 3
        bot.reply_to(message, "Введите дату истечения в формате YYYY-MM-DD:")
    elif step == 3:  # Ввод даты истечения
        try:
            expiration_date = datetime.strptime(message.text, '%Y-%m-%d').date()
            cursor.execute(
                "INSERT INTO certificates (user_id, user_name, certificate_name, certificate_key, expiration_date) VALUES (%s, %s, %s, %s, %s)",
                (user_id, message.from_user.full_name, user_states[user_id]['certificate_name'],
                 user_states[user_id]['certificate_key'], expiration_date)
            )
            conn.commit()
            bot.reply_to(message,
                         f"Сертификат '{user_states[user_id]['certificate_name']}' с ключом '{user_states[user_id]['certificate_key']}' добавлен с датой истечения {message.text}.")
            logging.info(
                f"Сертификат '{user_states[user_id]['certificate_name']}' с ключом '{user_states[user_id]['certificate_key']}' добавлен для пользователя {message.from_user.full_name}.")
        except ValueError:
            bot.reply_to(message, "Неверный формат даты. Пожалуйста, используйте формат YYYY-MM-DD.")
        finally:
            del user_states[user_id]
    else:
        bot.reply_to(message, "Произошла ошибка. Попробуйте снова.")


@bot.message_handler(commands=['удалить'])
def remove_certificate(message):
    logging.info(f"Команда удаления получена от пользователя {message.from_user.full_name}: {message.text}")
    try:
        if len(message.text.split()) < 2:
            bot.reply_to(message, "Использование: /удалить <название сертификата>")
            return

        name = message.text.split(maxsplit=1)[1]
        cursor.execute("DELETE FROM certificates WHERE user_id = %s AND certificate_name = %s",
                       (message.from_user.id, name))
        conn.commit()

        if cursor.rowcount > 0:
            bot.reply_to(message, f"Сертификат '{name}' удален.")
            logging.info(f"Сертификат '{name}' удален для пользователя {message.from_user.full_name}.")
        else:
            bot.reply_to(message, f"Сертификат '{name}' не найден.")
            logging.info(f"Сертификат '{name}' не найден для пользователя {message.from_user.full_name}.")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        logging.error(f"Ошибка при удалении сертификата: {e}")


@bot.message_handler(commands=['сертификаты'])
def check_certificates(message):
    logging.info(f"Команда проверки получена от пользователя {message.from_user.full_name}: {message.text}")
    try:
        cursor.execute("SELECT certificate_name, certificate_key, expiration_date FROM certificates WHERE user_id = %s",
                       (message.from_user.id,))
        rows = cursor.fetchall()

        if rows:
            response = "Ваши сертификаты:\n"
            for name, certificate_key, expiration_date in rows:
                expiration_date_str = expiration_date.strftime('%d-%m-%Y')
                response += f"Сертификат '{name}', ключ: '{certificate_key}', дата истечения: {expiration_date_str}\n"
        else:
            response = "У вас нет добавленных сертификатов."

        bot.reply_to(message, response)
        logging.info(f"Информация о сертификатах отправлена пользователю {message.from_user.full_name}.")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        logging.error(f"Ошибка при проверке сертификатов: {e}")


# Обработчик для команды /help
@bot.message_handler(commands=['help'])
def help_command(message):
    bot.reply_to(message, "Доступные команды:\n"
                          "/добавить - Добавить сертификат\n"
                          "/удалить - Удалить сертификат\n"
                          "/сертификаты - Проверить сертификаты")


def send_reminders():
    try:
        today = datetime.now(timezone).date()
        now = datetime.now(timezone)
        cursor.execute("SELECT user_id, user_name, certificate_name, expiration_date FROM certificates")
        rows = cursor.fetchall()
        for user_id, user_name, name, expiration_date in rows:
            expiration_date = expiration_date.date() if isinstance(expiration_date, datetime) else expiration_date

            days_left = (expiration_date - today).days
            hours_left = (expiration_date - now).total_seconds() // 3600

            if days_left == 7 or days_left == 3 or (days_left == 0 and hours_left <= 5):
                bot.send_message(user_id,
                                 f"{user_name}, сертификат '{name}' истекает {expiration_date}. Осталось {days_left} {'день' if days_left == 1 else 'дня' if days_left < 5 else 'дней'} и {int(hours_left % 24)} {'час' if hours_left % 24 == 1 else 'часа' if hours_left % 24 < 5 else 'часов'}. Пожалуйста, обновите его!")
                logging.info(
                    f"Напоминание отправлено пользователю {user_name} о сертификате '{name}' за {days_left} {'день' if days_left == 1 else 'дня' if days_left < 5 else 'дней'} и {int(hours_left % 24)} {'час' if hours_left % 24 == 1 else 'часа' if hours_left % 24 < 5 else 'часов'}.")

    except Exception as e:
        logging.error(f"Ошибка отправки напоминаний: {e}")


scheduler = BackgroundScheduler(timezone=timezone)
scheduler.add_job(send_reminders, 'interval', days=1)
scheduler.start()

try:
    logging.info("Бот запущен и ожидает команды...")
    bot.polling(none_stop=True)
except Exception as e:
    logging.error(f"Ошибка при запуске бота: {e}")
