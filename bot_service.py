import telebot
from datetime import datetime, timedelta
import psycopg2
from apscheduler.schedulers.background import BackgroundScheduler
import pytz
import logging
from telebot import types
import signal
import sys

logging.basicConfig(level=logging.INFO)

timezone = pytz.timezone('Asia/Bishkek')

API_TOKEN = '7370432818:AAELlwGFnwnq0J7flE1gZsDhyG3wnJRuaCY'
bot = telebot.TeleBot(API_TOKEN)

user_states = {}

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
    button_add = types.KeyboardButton("/add")
    button_remove = types.KeyboardButton("/remove")
    button_check = types.KeyboardButton("/certificate")
    button_update = types.KeyboardButton("/update")
    button_help = types.KeyboardButton("/help")

    markup.add(button_add, button_remove, button_check, button_update, button_help)
    bot.send_message(message.chat.id, "Выберите команду:", reply_markup=markup)

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = (
        "Вот доступные команды:\n"
        "/add - Добавить новый сертификат\n"
        "/remove - Удалить сертификат\n"
        "/certificate - Проверить сертификаты\n"
        "/update - Обновить сертификат\n"
        "/help - Показать это сообщение"
    )
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['add'])
def start_add_certificate(message):
    user_states[message.from_user.id] = {'step': 1}
    bot.reply_to(message, "Введите название сертификата в кавычках:", reply_markup=cancel_keyboard())

def cancel_keyboard():
    markup = types.InlineKeyboardMarkup()
    button_cancel = types.InlineKeyboardButton("Отмена", callback_data="cancel")
    markup.add(button_cancel)
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "cancel")
def cancel_command(call):
    user_id = call.from_user.id
    if user_id in user_states:
        del user_states[user_id]
        bot.answer_callback_query(call.id, "✅ Процесс добавления сертификата отменён.")
        bot.send_message(user_id, "Вы можете использовать другие команды.")
    else:
        bot.answer_callback_query(call.id, "🚫 У вас нет активного процесса добавления сертификата.")

@bot.message_handler(func=lambda message: message.from_user.id in user_states)
def handle_add_certificate_input(message):
    user_id = message.from_user.id
    step = user_states[user_id]['step']

    if step == 1:
        if message.text.startswith('"') and message.text.endswith('"'):
            user_states[user_id]['certificate_name'] = message.text.strip('"')
            user_states[user_id]['step'] = 2
            bot.reply_to(message, "Введите ключ сертификата в кавычках:", reply_markup=cancel_keyboard())
        else:
            bot.reply_to(message, "❌ Пожалуйста, введите название сертификата в кавычках.", reply_markup=cancel_keyboard())
    elif step == 2:
        if message.text.startswith('"') and message.text.endswith('"'):
            user_states[user_id]['certificate_key'] = message.text.strip('"')
            user_states[user_id]['step'] = 3
            bot.reply_to(message, "Введите дату истечения в формате YYYY-MM-DD:", reply_markup=cancel_keyboard())
        else:
            bot.reply_to(message, "❌ Пожалуйста, введите ключ сертификата в кавычках.", reply_markup=cancel_keyboard())
    elif step == 3:
        try:
            expiration_date = datetime.strptime(message.text, '%Y-%m-%d').date()
            cursor.execute(
                "INSERT INTO certificates (user_id, user_name, certificate_name, certificate_key, expiration_date) VALUES (%s, %s, %s, %s, %s)",
                (user_id, message.from_user.full_name, user_states[user_id]['certificate_name'],
                 user_states[user_id]['certificate_key'], expiration_date)
            )
            conn.commit()
            bot.reply_to(message,
                         f"✅ Сертификат *'{user_states[user_id]['certificate_name']}'* с ключом *'{user_states[user_id]['certificate_key']}'* добавлен с датой истечения {message.text}.")
            logging.info(
                f"Сертификат '{user_states[user_id]['certificate_name']}' с ключом '{user_states[user_id]['certificate_key']}' добавлен для пользователя {message.from_user.full_name}.")
        except ValueError:
            bot.reply_to(message, "❌ Неверный формат даты. Пожалуйста, используйте формат YYYY-MM-DD.", reply_markup=cancel_keyboard())
        finally:
            del user_states[user_id]
    else:
        bot.reply_to(message, "⚠️ Произошла ошибка. Попробуйте снова.")

@bot.message_handler(commands=['remove'])
def remove_certificate(message):
    if message.from_user.id in user_states:
        bot.reply_to(message, "❗ Вы всё еще находитесь в процессе добавления сертификата. Используйте кнопку отмены.", reply_markup=cancel_keyboard())
        return

    logging.info(f"Команда удаления получена от пользователя {message.from_user.full_name}: {message.text}")
    
    try:
        if '"' in message.text:
            name = message.text.split('"')[1]  
        else:
            bot.reply_to(message, "Использование: /remove \"Название сертификата\"", reply_markup=cancel_keyboard())
            return

        cursor.execute("DELETE FROM certificates WHERE user_id = %s AND certificate_name = %s", 
                       (message.from_user.id, name))
        conn.commit()
        if cursor.rowcount > 0:
            bot.reply_to(message, f"✅ Сертификат *'{name}'* удалён.", parse_mode='Markdown')
            logging.info(f"Сертификат '{name}' удалён для пользователя {message.from_user.full_name}.")
        else:
            bot.reply_to(message, f"🚫 Сертификат *'{name}'* не найден.", parse_mode='Markdown')
            logging.info(f"Сертификат '{name}' не найден для пользователя {message.from_user.full_name}.")
    
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка: {e}", reply_markup=cancel_keyboard())
        logging.error(f"Ошибка при удалении сертификата: {e}")

@bot.message_handler(commands=['certificate'])
def check_certificates(message):
    if message.from_user.id in user_states:
        bot.reply_to(message, "❗ Вы всё еще находитесь в процессе добавления сертификата. Используйте кнопку отмены.", reply_markup=cancel_keyboard())
        return

    logging.info(f"Команда проверки получена от пользователя {message.from_user.full_name}: {message.text}")
    try:
        cursor.execute("SELECT certificate_name, certificate_key, expiration_date FROM certificates WHERE user_id = %s",
                       (message.from_user.id,))
        rows = cursor.fetchall()
        if rows:
            response = "*Ваши сертификаты:*\n"
            for name, certificate_key, expiration_date in rows:
                expiration_date_str = expiration_date.strftime('%d-%m-%Y')
                response += f"🔖 Сертификат: *\"{name}\"*\n" \
                            f"🔑 Ключ: \"{certificate_key}\"\n" \
                            f"📅 Дата истечения: {expiration_date_str}\n\n"
        else:
            response = "🚫 У вас нет добавленных сертификатов."
        bot.reply_to(message, response, parse_mode='Markdown')
        logging.info(f"Информация о сертификатах отправлена пользователю {message.from_user.full_name}.")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка: {e}")
        logging.error(f"Ошибка при проверке сертификатов: {e}")
@bot.message_handler(commands=['update'])
def start_update_certificate(message):
    user_id = message.from_user.id
    if user_id in user_states:
        bot.reply_to(message, "❗ Вы уже находитесь в процессе другой операции. Завершите его перед обновлением.", reply_markup=cancel_keyboard())
        return   
    user_states[user_id] = {'step': 1}
    bot.reply_to(message, "Введите название сертификата, который хотите обновить, в кавычках:", reply_markup=cancel_keyboard())

@bot.message_handler(func=lambda message: message.from_user.id in user_states)
def handle_update_certificate_input(message):
    user_id = message.from_user.id
    step = user_states[user_id]['step']
    
    if step == 1:
        if message.text.startswith('"') and message.text.endswith('"'):
            certificate_name = message.text.strip('"')
            cursor.execute("SELECT certificate_key, expiration_date FROM certificates WHERE user_id = %s AND certificate_name = %s", 
                           (user_id, certificate_name))
            row = cursor.fetchone()
            
            if row:
                user_states[user_id]['certificate_name'] = certificate_name
                user_states[user_id]['certificate_key'] = row[0]
                user_states[user_id]['expiration_date'] = row[1]
                user_states[user_id]['step'] = 2
                bot.reply_to(message, "Введите новый ключ сертификата в кавычках (или введите 'пропустить' для сохранения старого):", reply_markup=cancel_keyboard())
            else:
                bot.reply_to(message, "🚫 Сертификат не найден. Пожалуйста, попробуйте еще раз.", reply_markup=cancel_keyboard())
                del user_states[user_id]  
        else:
            bot.reply_to(message, "❌ Пожалуйста, введите название сертификата в кавычках.", reply_markup=cancel_keyboard())

    elif step == 2:
        new_certificate_key = message.text.strip('"')
        if new_certificate_key.lower() == 'пропустить':
            new_certificate_key = user_states[user_id]['certificate_key']  
        user_states[user_id]['new_certificate_key'] = new_certificate_key
        user_states[user_id]['step'] = 3
        bot.reply_to(message, "Введите новую дату истечения в формате YYYY-MM-DD (или введите 'пропустить' для сохранения старой):", reply_markup=cancel_keyboard())

    elif step == 3:
        new_expiration_date = message.text.strip('"')
        if new_expiration_date.lower() == 'пропустить':
            new_expiration_date = user_states[user_id]['expiration_date']
        else:
            try:
                new_expiration_date = datetime.strptime(new_expiration_date, '%Y-%m-%d').date()
            except ValueError:
                bot.reply_to(message, "❌ Неверный формат даты. Пожалуйста, используйте формат YYYY-MM-DD.", reply_markup=cancel_keyboard())
                return

        cursor.execute(
            "UPDATE certificates SET certificate_key = %s, expiration_date = %s WHERE user_id = %s AND certificate_name = %s",
            (user_states[user_id]['new_certificate_key'], new_expiration_date, user_id, user_states[user_id]['certificate_name'])
        )
        conn.commit()

        bot.reply_to(message,
                     f"✅ Сертификат *'{user_states[user_id]['certificate_name']}'* обновлён. Новый ключ: *'{user_states[user_id]['new_certificate_key']}'*, новая дата истечения: {new_expiration_date}.")
        logging.info(
            f"Сертификат '{user_states[user_id]['certificate_name']}' обновлён для пользователя {message.from_user.full_name}.")
        del user_states[user_id]  

    else:
        bot.reply_to(message, "⚠️ Произошла ошибка. Попробуйте снова.")

def schedule_expiration_check():
    cursor.execute("SELECT user_id, user_name, certificate_name, expiration_date FROM certificates")
    rows = cursor.fetchall()

    today = datetime.now(timezone).date()
    for row in rows:
        user_id, user_name, certificate_name, expiration_date = row

        if expiration_date == today:
            bot.send_message(user_id, f"📅 Ваш сертификат *'{certificate_name}'* истекает сегодня!", parse_mode='Markdown')

scheduler = BackgroundScheduler()
scheduler.add_job(schedule_expiration_check, 'cron', hour=8, minute=0, timezone=timezone)
scheduler.start()

def exit_gracefully(signum, frame):
    logging.info("Завершение работы бота...")
    cursor.close()
    conn.close()
    scheduler.shutdown()
    sys.exit(0)

signal.signal(signal.SIGINT, exit_gracefully)

if __name__ == '__main__':
    bot.polling()
