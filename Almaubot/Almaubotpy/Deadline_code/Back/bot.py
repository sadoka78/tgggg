import requests
from telegram import Bot

import speech_recognition as sr
from telegram import Update,  ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ConversationHandler, filters, ContextTypes

from datetime import datetime
import re

from pydub import AudioSegment

from telegram.ext import CallbackQueryHandler
from calendar import monthrange
import tracemalloc
tracemalloc.start()


import os

import aiomysql
import logging
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# Получение значений из переменных окружения
bot_token = os.getenv("BOT_TOKEN")
mysql_host = os.getenv("MYSQL_HOST")
mysql_port = int(os.getenv("MYSQL_PORT", 3306))
mysql_user = os.getenv("MYSQL_USER")
mysql_password = os.getenv("MYSQL_PASSWORD")
mysql_db = os.getenv("MYSQL_DB")

# Логирование
logging.basicConfig(level=logging.INFO)

# Глобальные переменные для пула
db_pool = None

# Настройка пула соединений с базой данных
# Настройка пула соединений с базой данных
async def create_db_pool():
    global db_pool
    try:
        db_pool = await aiomysql.create_pool(
            host=os.getenv("MYSQL_HOST"),
            port=int(os.getenv("MYSQL_PORT", 3306)),
            user=os.getenv("MYSQL_USER"),
            password=os.getenv("MYSQL_PASSWORD"),
            db=os.getenv("MYSQL_DB"),
            minsize=1,  # Минимальный размер пула
            maxsize=10,  # Максимальный размер пула
            # loop=asyncio.get_event_loop(),  # Удалено
            autocommit=True  # Включение автокоммита для немедленного сохранения изменений
        )
        logging.info("Bot: Пул соединений к базе данных создан успешно.")
    except Exception as e:
        logging.error(f"Bot: Ошибка при создании пула соединений: {e}")
        db_pool = None  # В случае ошибки пул остается None

# Функция для выполнения асинхронных запросов
async def execute_query(query, params=None):
    if db_pool is None:
        logging.error("Bot: Пул соединений не инициализирован.")
        return None

    async with db_pool.acquire() as connection:  # Получаем соединение из пула
        async with connection.cursor(aiomysql.DictCursor) as cursor:
            await cursor.execute(query, params)
            result = await cursor.fetchall()
            return result

ROLE, CODE, FULLNAME, REGISTER_FOR_SUBJECTS, GROUP, DAY_SELECTION, TIME_SELECTION, RECORD_VOICE, CONFIRM_DEADLINE = range(9)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    logging.info(f"Пользователь {user_id} вызвал команду /start.")

    try:
        # Проверка, является ли пользователь студентом
        student_result = await execute_query("SELECT fullname FROM students WHERE id = %s", (user_id,))
        logging.debug(f"Результат запроса для студента: {student_result}")
        if student_result:
            student = student_result[0]['fullname']
            logging.info(f"Пользователь {user_id} идентифицирован как студент: {student}.")
        else:
            student = None

        # Проверка, является ли пользователь преподавателем
        teacher_result = await execute_query("SELECT fullname FROM teachers WHERE telegram_id = %s", (user_id,))
        logging.debug(f"Результат запроса для преподавателя: {teacher_result}")
        if teacher_result:
            teacher = teacher_result[0]['fullname']
            logging.info(f"Пользователь {user_id} идентифицирован как преподаватель: {teacher}.")
        else:
            teacher = None

        # Ответ в зависимости от роли пользователя
        if student:
            await update.message.reply_text(f"Добро пожаловать, {student}! Вы уже зарегистрированы как студент.")
            await show_main_menu(update, context)
        elif teacher:
            await update.message.reply_text(f"Добро пожаловать, {teacher}! Вы уже зарегистрированы как преподаватель.")
            await show_teacher_menu(update, context)
        else:
            # Клавиатура для выбора роли
            keyboard = [
                [
                    InlineKeyboardButton("Преподаватель", callback_data='teacher'),
                    InlineKeyboardButton("Студент", callback_data='student')
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await update.message.reply_text(
                "Привет! Я бот для отслеживания дедлайнов. Выберите вашу роль для регистрации:",
                reply_markup=reply_markup
            )
            return ROLE

    except Exception as e:
        logging.error(f"Ошибка в функции start для пользователя {user_id}: {e}")
        await update.message.reply_text("Произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже.")
        return ConversationHandler.END

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Регистрация на дисциплины", callback_data="register_subjects")],
        [InlineKeyboardButton("Текущие дисциплины", callback_data="current_deadlines")],
        [InlineKeyboardButton("Текущие дедлайны", callback_data="deadlines_messages")],
        [InlineKeyboardButton("Помощь", callback_data="help")]

    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.message.reply_text("Главное меню:", reply_markup=reply_markup)
    else:
        await update.message.reply_text("Главное меню:", reply_markup=reply_markup)


async def handle_main_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query and query.data == "resume_for_teacher":
        await query.answer()
        return

    if query and query.data == "continue_to_menu":
        await query.answer()
        await show_main_menu(update, context)
        return

        # Process other choices
    if query:
        await query.answer()
        selection = query.data
    else:
        await update.message.reply_text("Пожалуйста, сначала зарегистрируйтесь.")
        return

    if selection == "register_subjects":
        await handle_register_for_subjects(update, context)
    elif selection == "current_deadlines":
        await show_current_deadlines(update, context)
    elif selection == "help":
        await show_help(update, context)
    elif selection == "deadlines_messages":
        await deadlines_messages(update, context)
    elif selection == "back_to_main_menu":
        await show_main_menu(update, context)


import asyncio




async def auto_delete_expired_deadlines():
    while True:
        current_datetime = datetime.now()

        async with db_pool.acquire() as connection:
            async with connection.cursor() as cursor:
                try:
                    # Сначала удаляем связанные записи в таблице active_deadlines
                    delete_active_deadlines_query = """
                    DELETE FROM active_deadlines 
                    WHERE deadline_id IN (
                        SELECT id FROM deadlines 
                        WHERE CONCAT(full_date, ' ', time) < %s
                    )
                    """
                    await cursor.execute(delete_active_deadlines_query,
                                         (current_datetime.strftime('%Y-%m-%d %H:%M:%S'),))
                    await connection.commit()

                    # Затем удаляем просроченные дедлайны из таблицы deadlines
                    delete_deadlines_query = """
                    DELETE FROM deadlines 
                    WHERE CONCAT(full_date, ' ', time) < %s
                    """
                    await cursor.execute(delete_deadlines_query, (current_datetime.strftime('%Y-%m-%d %H:%M:%S'),))
                    await connection.commit()

                    logging.info("Просроченные дедлайны и связанные записи успешно удалены")
                except Exception as e:
                    logging.error(f"Ошибка при удалении просроченных дедлайнов: {e}")

        # Ждать 24 часа перед следующим запуском
        await asyncio.sleep(86400)


async def show_current_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    async with db_pool.acquire() as connection:
        async with connection.cursor() as cursor:
            db_query = """
            SELECT 
                s.name AS Предмет,
                sch.time AS Время,
                sch.day AS День,
                s.teacher AS Преподаватель,
                s.language AS Язык
            FROM 
                student_registration sr
            JOIN 
                schedule sch ON sr.subject_id = sch.subject_id
            JOIN 
                subjects s ON sch.subject_id = s.id
            WHERE 
                sr.student_id = %s
            ORDER BY s.name, sch.day, sch.time;
            """
            await cursor.execute(db_query, (user_id,))
            subjects = await cursor.fetchall()

    # Формирование сообщения происходит на основе свежих данных
    subject_dict = {}
    for subject in subjects:
        subject_name = subject[0]
        subject_details = {
            "day": subject[2],
            "time": subject[1]
        }
        if subject_name not in subject_dict:
            subject_dict[subject_name] = {
                "details": [],
                "teacher": subject[3],
                "language": subject[4]
            }
        subject_dict[subject_name]["details"].append(subject_details)

    # Формируем сообщение
    if subject_dict:
        message = "Ваши текущие дисциплины:\n\n"
        for subject_name, data in subject_dict.items():
            message += f"📘 Предмет: {subject_name}\n"
            message += f"👤 Преподаватель: {data['teacher']}\n"
            message += f"🌐 Язык: {data['language']}\n"
            for detail in data["details"]:
                message += f"📅 День: {detail['day']}\n"
                message += f"🕒 Время: {detail['time']}\n"
            message += "\n"
    else:
        message = "У вас нет текущих дисциплин."

    await query.message.reply_text(message)
    await show_main_menu(update, context)




async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text("Помощь. Напишите пользователю @sadokasik или @nurkhaidarovbeks,если возникли вопросы по боту. ")

    keyboard = [[InlineKeyboardButton("Назад в главное меню", callback_data="back_to_main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Что хотите сделать?", reply_markup=reply_markup)

async def deadlines_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    async with db_pool.acquire() as connection:
        async with connection.cursor() as cursor:
            db_query = """
            SELECT 
                s.name AS Предмет,
                d.full_date AS Дата,
                d.time AS Время,
                d.text AS Дедлайн
            FROM 
                active_deadlines ad
            JOIN 
                deadlines d ON ad.deadline_id = d.id
            JOIN 
                subjects s ON d.subject_id = s.id
            WHERE 
                ad.student_id = %s
            ORDER BY 
                s.name, d.full_date, d.time;
            """

            await cursor.execute(db_query, (user_id,))
            deadlines = await cursor.fetchall()

    if deadlines:
        from collections import defaultdict

        # Создаём словарь, где ключ — название предмета, а значение — список дедлайнов
        deadlines_by_subject = defaultdict(list)
        for deadline in deadlines:
            subject = deadline[0]
            deadline_info = {
                "Дата": deadline[1],
                "Время": deadline[2],
                "Дедлайн": deadline[3]
            }
            deadlines_by_subject[subject].append(deadline_info)

        message = "Текущие дедлайны:\n\n"
        for subject, deadlines_list in deadlines_by_subject.items():
            message += f"📘 {subject}\n"
            for dl in deadlines_list:
                message += f"📅 {dl['Дата']}\n"
                message += f"🕒 {dl['Время']}\n"
                message += f"📖 {dl['Дедлайн']}\n\n"
        # Удаляем последние лишние переносы строк
        message = message.strip()
    else:
        message = "У вас нет текущих дедлайнов."

    await query.message.reply_text(message)
    await show_main_menu(update, context)


async def role_selected(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_role = query.data

    if user_role == "teacher":
        await query.message.reply_text("Введите код чтобы зарегистрироваться.")
        return CODE
    elif user_role == "student":
        await query.message.reply_text("Пожалуйста, введите ваше полное имя.")
        return FULLNAME


async def handle_role_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await role_selected(update, context)


async def enter_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id  # Получаем Telegram ID пользователя
    code = update.message.text.strip()  # Получаем введённый уникальный код

    # Проверяем, зарегистрирован ли пользователь
    if context.user_data.get("registered"):
        await update.message.reply_text("Вы уже зарегистрированы.")
        return ConversationHandler.END  # Завершение, чтобы не запрашивать снова

    async with db_pool.acquire() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute("SELECT * FROM teachers WHERE unique_code1 = %s", (code,))
            teacher = await cursor.fetchone()

            if teacher:
                # Устанавливаем флаг о регистрации
                context.user_data["registered"] = True
                # Сохраняем Telegram ID
                await cursor.execute("UPDATE teachers SET telegram_id = %s WHERE unique_code1 = %s", (user_id, code))
                await connection.commit()

                # Приветственное сообщение
                await update.message.reply_text(f"Добро пожаловать, {teacher[2]}!")
                await show_teacher_menu(update, context)  # Показать меню учителя
                return ConversationHandler.END  # Завершаем разговор

            else:
                await update.message.reply_text("Неверный код. Пожалуйста, попробуйте еще раз.")
                return CODE  # Оставляем пользователя в состоянии CODE для повторной проверки


async def reset_registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["registered"] = False
    await update.message.reply_text("Вы можете зарегистрироваться заново.")

async def handle_day_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    day = update.effective_message.text
    if day.isdigit() and 1 <= int(day) <= 31:
        now = datetime.now()
        full_date = f"{day}.{now.month}.{now.year}"
        weekday = now.replace(day=int(day)).strftime('%A')
        context.user_data['full_date'] = full_date
        context.user_data['day'] = int(day)
        context.user_data['weekday'] = weekday
        await update.effective_message.reply_text(f"Вы выбрали: {full_date}")

        # Переходим к выбору времени
        time_buttons = [
            [InlineKeyboardButton('08:00', callback_data='08:00')],
            [InlineKeyboardButton('09:00', callback_data='09:00')],
            [InlineKeyboardButton('10:00', callback_data='10:00')],
            [InlineKeyboardButton('11:10', callback_data='11:10')],
            [InlineKeyboardButton('12:10', callback_data='12:10')],
            [InlineKeyboardButton('13:10', callback_data='13:10')],
            [InlineKeyboardButton('14:20', callback_data='14:20')],
            [InlineKeyboardButton('15:20', callback_data='15:20')],
            [InlineKeyboardButton('16:20', callback_data='16:20')],
            [InlineKeyboardButton('17:20', callback_data='17:20')],
            [InlineKeyboardButton('18:20', callback_data='18:20')],
            [InlineKeyboardButton('19:20', callback_data='19:20')],
            [InlineKeyboardButton('20:00', callback_data='20:00')],
            [InlineKeyboardButton('21:00', callback_data='21:00')],
            [InlineKeyboardButton('22:00', callback_data='22:00')],
            [InlineKeyboardButton('23:00', callback_data='23:00')],
            [InlineKeyboardButton('23:59', callback_data='23:59')]

        ]
        reply_markup = InlineKeyboardMarkup(time_buttons)
        await update.effective_message.reply_text(
            "Выберите время, до которого студент должен выполнить задание:",
            reply_markup=reply_markup
        )


async def handle_time_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_time = query.data
    context.user_data['time'] = selected_time
    await query.message.reply_text(
        f"Вы выбрали время: {selected_time}. Теперь запишите голосовое сообщение."
    )

    context.user_data['waiting_for_voice'] = True


from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

async def show_teacher_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Создаем клавиатуру для учителей
    keyboard = [
        [InlineKeyboardButton("Установить дедлайны", callback_data="teacher_set_deadlines")],
        [InlineKeyboardButton("Просмотреть установленные дедлайны", callback_data="teacher_view_all_deadlines")],
        [InlineKeyboardButton("Помощь", callback_data="teacher_help")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Если запрос пришел через callback (кнопка нажата)
    if update.callback_query:
        query = update.callback_query
        await query.answer()  # Ответ на запрос callback (обязателен для предотвращения тайм-аутов)
        await query.message.reply_text("Меню для учителей:", reply_markup=reply_markup)
    else:
        # Если это обычное сообщение (например, /start или команда), отправляем сообщение
        await update.message.reply_text("Меню для учителей:", reply_markup=reply_markup)



async def handle_teacher_menu_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    if query and query.data == "resume_for_teacher":
        await query.answer()
        await show_teacher_menu(update, context)  # Show the teacher menu here.
        return

    if query:
        await query.answer()
        selection = query.data
    else:
        await update.message.reply_text("Пожалуйста, сначала зарегистрируйтесь.")
        return

    if selection == "teacher_set_deadlines":
        await handle_set_deadlines(update, context)
    elif selection == "teacher_view_all_deadlines":
        await show_all_deadlines(update, context)
    elif selection == "teacher_help":
        await show_teacher_help(update, context)
    elif selection == "back_to_teacher_menu":
        await show_teacher_menu(update, context)


async def handle_set_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("Вы можете установить дедлайны на даты:")
    return await show_calendar(update, context)

async def show_all_deadlines(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    # Получаем Telegram ID текущего пользователя (преподавателя)
    telegram_id = query.from_user.id
    print(f"Telegram ID преподавателя: {telegram_id}")  # Отладка для проверки правильности ID

    # Формируем начальное сообщение
    message = "Ваши установленные дедлайны:\n\n"

    # Извлекаем дедлайны из базы данных
    async with db_pool.acquire() as connection:
        async with connection.cursor() as cursor:
            # Проверяем, есть ли соответствующий преподаватель в базе
            await cursor.execute("SELECT * FROM teachers WHERE telegram_id = %s", (telegram_id,))
            teacher_exists = await cursor.fetchone()
            print(f"Преподаватель найден в базе: {teacher_exists}")  # Отладка

            # Если преподаватель найден, продолжаем
            if teacher_exists:
                # Проверим, есть ли связанные предметы
                await cursor.execute("""
                    SELECT * FROM subjects WHERE teacher = %s
                """, (teacher_exists[2],))  # teacher_exists[2] — это имя преподавателя
                subjects = await cursor.fetchall()
                print(f"Предметы преподавателя: {subjects}")  # Отладка

                # Если есть предметы, продолжаем запрос дедлайнов
                if subjects:
                    subject_ids = [subject[0] for subject in subjects]  # Получаем все subject_id
                    subject_ids_tuple = tuple(subject_ids)  # Создаем кортеж для SQL IN

                    # Получаем дедлайны для этих предметов
                    await cursor.execute("""
                        SELECT d.id, d.full_date, d.time, d.text, s.name, t.fullname 
                        FROM deadlines d
                        JOIN subjects s ON d.subject_id = s.id
                        JOIN teachers t ON s.teacher = t.fullname
                        WHERE s.id IN %s  -- Используем IN для всех предметов преподавателя
                        ORDER BY d.full_date
                    """, (subject_ids_tuple,))
                    deadlines = await cursor.fetchall()
                    print(f"Полученные дедлайны: {deadlines}")  # Отладка

                    # Если дедлайны найдены, выводим их
                    if deadlines:
                        for deadline in deadlines:
                            deadline_id = deadline[0]
                            deadline_date = deadline[1]
                            deadline_time = deadline[2]
                            deadline_text = deadline[3]
                            subject_name = deadline[4]
                            teacher_name = deadline[5]

                            message += f"📘 {subject_name}\n"
                            message += f"🕒 Время: {deadline_time}\n"
                            message += f"📅 Дата: {deadline_date}\n"
                            message += f"👤 Преподаватель: {teacher_name}\n"
                            message += f"Задание: {deadline_text}\n\n"
                    else:
                        message += "У вас нет активных дедлайнов."
                else:
                    message += "У вас нет предметов, привязанных к дедлайнам."
            else:
                message += "Преподаватель с таким ID не найден в базе."

    # Отправляем сообщение
    await query.message.reply_text(message)

    # Добавляем кнопки для дальнейших действий
    keyboard = [[InlineKeyboardButton("Назад в меню учителей", callback_data="back_to_teacher_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Что хотите сделать?", reply_markup=reply_markup)








async def show_teacher_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.message.reply_text("Помощь для учителей.")

    keyboard = [[InlineKeyboardButton("Назад в меню учителей", callback_data="back_to_teacher_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Что хотите сделать?", reply_markup=reply_markup)


async def enter_fullname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fullname = update.message.text.strip()
    user_id = update.message.from_user.id

    # Проверка формата полного имени (для кириллицы и латиницы)
    if re.match(r'^[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+$', fullname) or \
            re.match(r'^[A-Z][a-z]+\s[A-Z][a-z]+\s[A-Z][a-z]+$', fullname):
        fullname = ' '.join(part.capitalize() for part in fullname.split())
        context.user_data['fullname'] = fullname

        # Получаем подключение из пула
        async with db_pool.acquire() as connection:
            async with connection.cursor() as cursor:
                # Вставляем данные о студенте в базу
                await cursor.execute("INSERT INTO students (id, fullname) VALUES (%s, %s)", (user_id, fullname))
                await connection.commit()

        await update.message.reply_text("Вы успешно зарегистрированы.")

        # Отправляем кнопку для продолжения
        keyboard = [[InlineKeyboardButton("Продолжить", callback_data="continue_to_menu")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Нажмите 'Продолжить', чтобы перейти в главное меню:", reply_markup=reply_markup)

    else:
        await update.message.reply_text("Пожалуйста, введите полное имя в правильном формате.")


async def handle_register_for_subjects(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = 'http://127.0.0.1:5000'
    data = {'login': update.callback_query.from_user.id}
    requests.post(url, json=data)
    query = update.callback_query
    await query.answer()

    await query.message.reply_text("Регистрация на дисциплины.")

    await query.message.reply_text(
        "Пожалуйста, перейдите по ссылке для регистрации на дисциплины:\n"
        f"<a href='http://127.0.0.1:5000/register?user_id={update.callback_query.from_user.id}'>Регистрация на дисциплины</a>",
        parse_mode='HTML'
    )

    keyboard = [[InlineKeyboardButton("Назад в главное меню", callback_data="back_to_main_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.message.reply_text("Что хотите сделать?", reply_markup=reply_markup)


async def show_calendar(update: Update, context):
    now = datetime.now()
    month_days = monthrange(now.year, now.month)[1]
    first_weekday = monthrange(now.year, now.month)[0]

    days_of_week = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    buttons = [[days_of_week[i] for i in range(7)]]

    week = []
    for day in range(1, month_days + 1):
        if day == 1 and first_weekday > 0:
            week.extend([' '] * first_weekday)

        week.append(str(day))
        if len(week) == 7:
            buttons.append(week)
            week = []

    if week:
        week.extend([' '] * (7 - len(week)))
        buttons.append(week)

    reply_markup = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)
    await update.effective_message.reply_text(
        f"Выберите день из {now.strftime('%B')} {now.year}:",
        reply_markup=reply_markup
    )

    return await handle_day_selection(update, context)


async def record_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('waiting_for_voice'):
        voice = update.message.voice
        if voice:
            file_id = voice.file_id
            new_file = await context.bot.get_file(file_id)

            ogg_file_path = f"voice_{update.message.from_user.id}.ogg"
            wav_file_path = f"voice_{update.message.from_user.id}.wav"
            await new_file.download_to_drive(ogg_file_path)

            audio = AudioSegment.from_ogg(ogg_file_path)
            audio.export(wav_file_path, format="wav")

            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_file_path) as source:
                audio_data = recognizer.record(source)

            try:
                text = recognizer.recognize_google(audio_data, language="ru-RU")
                await update.message.reply_text(f"Вы сказали: {text}")

                context.user_data['deadline_text'] = text

                keyboard = [
                    [
                        InlineKeyboardButton("Да", callback_data="yes"),
                        InlineKeyboardButton("Нет", callback_data="no"),
                    ]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await update.message.reply_text(
                    f"Вы хотите установить следующий дедлайн: {text}?",
                    reply_markup=reply_markup
                )
                context.user_data['waiting_for_confirmation'] = True
            except sr.UnknownValueError:
                await update.message.reply_text("Не удалось распознать речь. Попробуйте еще раз.")
            except sr.RequestError as e:
                await update.message.reply_text(f"Ошибка сервиса распознавания: {e}")
        else:
            await update.message.reply_text("Пожалуйста, отправьте голосовое сообщение.")
    else:
        await update.message.reply_text("Сначала выберите время.")

async def handle_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()

    # Получаем подключение из пула
    async with db_pool.acquire() as connection:
        async with connection.cursor() as cursor:
            # Получаем subject_id преподавателя
            await cursor.execute("SELECT subject_id FROM teachers WHERE telegram_id = %s", (user_id,))
            subject_id_tuple = await cursor.fetchone()
            subject_id = subject_id_tuple[0] if subject_id_tuple else None

            # Получаем данные из контекста пользователя
            weekday = context.user_data.get("weekday")
            full_date = context.user_data.get("full_date")
            time = context.user_data.get("time")
            text = context.user_data.get("deadline_text")

            # Преобразуем дату из строки в формат datetime и отформатированную строку
            date_object = datetime.strptime(full_date, '%d.%m.%Y')
            formatted_date = date_object.strftime('%Y-%m-%d')

            # Логирование данных для отладки
            print(formatted_date, time, text, subject_id, weekday)

            if query.data == "yes":
                # Вставляем дедлайн в базу данных
                await cursor.execute("""
                    INSERT INTO deadlines (full_date, time, text, subject_id, day_of_week) 
                    VALUES (%s, %s, %s, %s, %s)
                """, (formatted_date, time, text, subject_id, weekday))
                await connection.commit()

                # Получаем ID добавленного дедлайна для дальнейшего использования
                deadline_id = cursor.lastrowid
                await query.edit_message_text(text="Дедлайн установлен и отправлен студентам!")

                # Получаем информацию о только что добавленном дедлайне для уведомления студентов
                await cursor.execute("SELECT * FROM deadlines WHERE id = %s", (deadline_id,))
                deadline_info = await cursor.fetchone()

                # Оповещаем студентов о новом дедлайне
                await notify_students(deadline_info)

                # Переход к меню учителя после завершения операции
                await show_teacher_menu(update, context)

            elif query.data == "no":
                # Повтор запроса голосового сообщения, если дедлайн не подтверждён
                await query.edit_message_text(text="Пожалуйста, запишите голосовое сообщение снова.")

            # Завершаем ожидание подтверждения
            context.user_data['waiting_for_confirmation'] = False

async def handle_add_deadline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Получаем telegram_id преподавателя
    user_id = update.effective_user.id
    query = update.callback_query
    await query.answer()

    # Получаем подключение к базе данных
    async with db_pool.acquire() as connection:
        async with connection.cursor() as cursor:
            # Получаем subject_id преподавателя
            await cursor.execute("SELECT subject_id FROM teachers WHERE telegram_id = %s", (user_id,))
            subject_id_tuple = await cursor.fetchone()
            subject_id = subject_id_tuple[0] if subject_id_tuple else None

            # Получаем дату, время и текст задания
            weekday = context.user_data.get("weekday")
            full_date = context.user_data.get("full_date")
            date_object = datetime.strptime(full_date, '%d.%m.%Y')
            formatted_date = date_object.strftime('%Y-%m-%d')
            time = context.user_data.get("time")
            text = context.user_data.get("deadline_text")

            # Вставляем дедлайн в базу данных
            if subject_id:
                await cursor.execute("""
                    INSERT INTO deadlines (full_date, time, text, subject_id, day_of_week)
                    VALUES (%s, %s, %s, %s, %s)
                """, (formatted_date, time, text, subject_id, weekday))
                await connection.commit()

                deadline_id = cursor.lastrowid
                await query.edit_message_text(text="Дедлайн установлен и сохранен в базе данных!")

                # Получаем информацию о добавленном дедлайне
                await cursor.execute("SELECT * FROM deadlines WHERE id = %s", (deadline_id,))
                deadline_info = await cursor.fetchone()

                # Оповещаем студентов, зарегистрированных на этот предмет
                await notify_students(deadline_info)

            else:
                await query.edit_message_text(text="Не удалось найти ваш предмет в базе данных.")

async def notify_students(deadline_info):
    deadline_id = deadline_info[0]  # Получаем ID дедлайна
    subject_id = deadline_info[4]   # Получаем subject_id из дедлайна

    # Получаем список студентов, зарегистрированных на предмет
    async with db_pool.acquire() as connection:
        async with connection.cursor() as cursor:
            # Получаем список студентов для данного предмета
            await cursor.execute("SELECT student_id FROM student_registration WHERE subject_id = %s", (subject_id,))
            students = await cursor.fetchall()

            # Получаем название предмета
            await cursor.execute("SELECT name FROM subjects WHERE id = %s", (subject_id,))
            subject_info = await cursor.fetchone()

            if not subject_info:
                print(f"Предмет с ID {subject_id} не найден.")
                return

            subject_name = subject_info[0]  # Название предмета

            if students:
                for student in students:
                    student_id = student[0]
                    # Вставляем в таблицу active_deadlines для каждого студента только один раз
                    await cursor.execute("""
                        INSERT INTO active_deadlines (deadline_id, student_id)
                        VALUES (%s, %s)
                    """, (deadline_id, student_id))

                await connection.commit()

                # Отправляем уведомления студентам
                for student in students:
                    student_id = student[0]
                    await send_deadline_notification(student_id, deadline_info, subject_name)
            else:
                print("Нет зарегистрированных студентов для отправки дедлайнов.")
async def send_deadline_notification(student_id, deadline_info, subject_name):
    # Формируем текст сообщения
    deadline_date = deadline_info[1]  # Дата дедлайна
    deadline_time = deadline_info[2]  # Время дедлайна
    deadline_text = deadline_info[3]  # Текст задания

    message_text = f"🔔 Новый дедлайн! \n\n" \
                   f"📚 Предмет: {subject_name} \n" \
                   f"📅 Дата: {deadline_date} \n" \
                   f"🕒 Время: {deadline_time} \n" \
                   f"📖 Задание: {deadline_text} \n\n" \
                   f"Пожалуйста, не забудьте выполнить задание!"

    # Отправляем сообщение студенту

    bot = Bot(token=bot_token)
    try:
        await bot.send_message(chat_id=student_id, text=message_text)
        print(f"Уведомление отправлено студенту {student_id}")
    except Exception as e:
        print(f"Ошибка при отправке уведомления студенту {student_id}: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("Cancel command triggered")  # Логирование
    await update.message.reply_text("Операция отменена. Вы вернулись в главное меню.")

    # Возвращаем пользователя в начальное состояние
    await show_main_menu(update, context)  # Функция, которая показывает главное меню (возможно, вам нужно её создать)

    return ConversationHandler.END  # Завершаем разговор



# Основная часть с конфигурацией бота
if __name__ == "__main__":
    import asyncio

    # Инициализация пула соединений
    loop = asyncio.get_event_loop()
    loop.run_until_complete(create_db_pool())  # Инициализация пула соединений
    loop.create_task(auto_delete_expired_deadlines())
    # Создание приложения и обработчиков
    app = ApplicationBuilder().token(bot_token).build()

    # Конфигурация ConversationHandler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ROLE: [CallbackQueryHandler(role_selected)],
            CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_code)],
            FULLNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_fullname)],
            REGISTER_FOR_SUBJECTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_register_for_subjects)],
            GROUP: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_role_selection)],
            DAY_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day_selection)],
            TIME_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_time_selection)],
            RECORD_VOICE: [MessageHandler(filters.VOICE, record_voice)]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True
    )

    # Добавление обработчиков
    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("show_calendar", show_calendar))
    app.add_handler(CallbackQueryHandler(show_calendar, pattern="^show_calendar$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_day_selection))
    app.add_handler(CallbackQueryHandler(handle_time_selection, pattern='^\\d{2}:\\d{2}$'))
    app.add_handler(MessageHandler(filters.VOICE, record_voice))
    app.add_handler(CallbackQueryHandler(handle_confirmation, pattern="^(yes|no)$"))
    app.add_handler(CallbackQueryHandler(handle_main_menu_selection,
                                         pattern="^continue_to_menu|register_subjects|current_deadlines|help|deadlines_messages|back_to_main_menu$"))
    app.add_handler(CallbackQueryHandler(handle_teacher_menu_selection,
                                         pattern="^resume_for_teacher|teacher_set_deadlines|teacher_view_all_deadlines|teacher_help|back_to_teacher_menu$"))
    app.add_handler(CommandHandler("reset_registration", reset_registration))


    # Запуск бота с поллингом

    loop.run_until_complete(app.run_polling())