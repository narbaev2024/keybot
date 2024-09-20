import telebot
from datetime import datetime
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Настройка часового пояса
timezone = pytz.timezone('Asia/Bishkek')

# Токен вашего бота
API_TOKEN = '7370432818:AAELlwGFnwnq0J7flE1gZsDhyG3wnJRuaCY'  # Замените на ваш токен
bot = telebot.TeleBot(API_TOKEN)

# Подключение к базе данных PostgreSQL
try:
    conn = psycopg2.connect(
        dbname='keybot',
        user='postgres',
        password='adminadmin',
        host='localhost',
        port='5432'
    )
    cursor = conn.cursor()
    # Создание таблицы для хранения сертификатов
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS certificates (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            user_name TEXT,
            certificate_name TEXT,
            expiration_date DATE
        );
    ''')
    conn.commit()
    logging.info("Успешное подключение к базе данных и создание таблицы.")
except Exception as e:
    logging.error(f"Ошибка подключения к базе данных: {e}")
    exit()

# Команда для добавления сертификата через чат
@bot.message_handler(commands=['add'])
def add_certificate(message):
    logging.info(f"Команда получена от пользователя {message.from_user.full_name}: {message.text}")
    try:
        args = message.text.split()[1:]  # Получение аргументов команды
        if len(args) != 2:
            bot.reply_to(message, "Использование: /add <название сертификата> <дата истечения в формате YYYY-MM-DD>")
            return

        name, date_str = args
        expiration_date = datetime.strptime(date_str, '%Y-%m-%d').date()

        # Сохранение данных о сертификате в базу данных
        cursor.execute(
            "INSERT INTO certificates (user_id, user_name, certificate_name, expiration_date) VALUES (%s, %s, %s, %s)",
            (message.from_user.id, message.from_user.full_name, name, expiration_date)
        )
        conn.commit()

        bot.reply_to(message, f"Сертификат '{name}' добавлен с датой истечения {date_str} для {message.from_user.full_name}")
        logging.info(f"Сертификат '{name}' добавлен для пользователя {message.from_user.full_name}.")

    except ValueError:
        bot.reply_to(message, "Неверный формат даты. Пожалуйста, используйте формат YYYY-MM-DD.")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        logging.error(f"Ошибка при добавлении сертификата: {e}")

# Команда для удаления сертификата через чат
@bot.message_handler(commands=['remove'])
def remove_certificate(message):
    logging.info(f"Команда удаления получена от пользователя {message.from_user.full_name}: {message.text}")
    try:
        name = message.text.split(maxsplit=1)[1]  # Получаем название сертификата
        cursor.execute("DELETE FROM certificates WHERE user_id = %s AND certificate_name = %s",
                       (message.from_user.id, name))
        conn.commit()

        if cursor.rowcount > 0:
            bot.reply_to(message, f"Сертификат '{name}' удален.")
            logging.info(f"Сертификат '{name}' удален для пользователя {message.from_user.full_name}.")
        else:
            bot.reply_to(message, f"Сертификат '{name}' не найден.")
            logging.info(f"Сертификат '{name}' не найден для пользователя {message.from_user.full_name}.")
    except IndexError:
        bot.reply_to(message, "Использование: /remove <название сертификата>")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        logging.error(f"Ошибка при удалении сертификата: {e}")

# Команда для проверки информации о сертификатах
@bot.message_handler(commands=['check'])
def check_certificates(message):
    logging.info(f"Команда проверки получена от пользователя {message.from_user.full_name}: {message.text}")
    try:
        cursor.execute("SELECT certificate_name, expiration_date FROM certificates WHERE user_id = %s",
                       (message.from_user.id,))
        rows = cursor.fetchall()

        if rows:
            response = "Ваши сертификаты:\n"
            for name, expiration_date in rows:
                response += f"Сертификат '{name}', дата истечения: {expiration_date}\n"
        else:
            response = "У вас нет добавленных сертификатов."

        bot.reply_to(message, response)
        logging.info(f"Информация о сертификатах отправлена пользователю {message.from_user.full_name}.")
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {e}")
        logging.error(f"Ошибка при проверке сертификатов: {e}")

# Функция для отправки напоминаний
def send_reminders():
    try:
        today = datetime.now(timezone).date()
        cursor.execute("SELECT user_id, user_name, certificate_name, expiration_date FROM certificates")
        rows = cursor.fetchall()
        for user_id, user_name, name, expiration_date in rows:
            expiration_date = expiration_date.date() if isinstance(expiration_date, datetime) else expiration_date
            days_left = (expiration_date - today).days
            if days_left <= 7:  # Напоминаем за 7 дней
                bot.send_message(user_id,
                                 f"{user_name}, сертификат '{name}' истекает {expiration_date}. Осталось {days_left} дней. Пожалуйста, обновите его!")
                logging.info(f"Напоминание отправлено пользователю {user_name} о сертификате '{name}'.")
    except Exception as e:
        logging.error(f"Ошибка отправки напоминаний: {e}")

# Планировщик для ежедневного напоминания
scheduler = BackgroundScheduler(timezone=timezone)
scheduler.add_job(send_reminders, 'interval', days=1)
scheduler.start()

# Запуск бота
try:
    logging.info("Бот запущен и ожидает команды...")
    bot.polling(none_stop=True)
except Exception as e:
    logging.error(f"Ошибка при запуске бота: {e}")
