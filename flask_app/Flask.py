from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from dotenv import load_dotenv
import os
import asyncio
import aiomysql

# Загрузка переменных из .env файла
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")

# Конфигурация MySQL
MYSQL_HOST = os.getenv('MYSQL_HOST')
MYSQL_USER = os.getenv('MYSQL_USER')
MYSQL_PASSWORD = os.getenv('MYSQL_PASSWORD')
MYSQL_DB = os.getenv('MYSQL_DB')


# Асинхронное подключение к базе данных
async def get_db_connection():
    return await aiomysql.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        db=MYSQL_DB
    )


@app.route('/', methods=['GET', 'POST'])
async def index():
    if request.method == 'POST':
        data = request.get_json()
        user_id = data.get('login')
        if user_id:
            session["user_id"] = user_id
            print(f"Login: user_id set in session = {session['user_id']}")
            return redirect(url_for('index'))

    user_id = session.get("user_id")
    print(f"Index: user_id from session = {user_id}")

    if not user_id:
        return redirect(url_for('receive_login'))

    subjects = await get_all_subjects(user_id)
    schedule = create_schedule(subjects)

    return render_template('register.html', schedule=schedule, user_id=user_id)


@app.route('/login', methods=['GET', 'POST'])
async def receive_login():
    if request.method == 'POST':
        data = request.get_json()
        user_id = data.get('login')

        if user_id:
            session["user_id"] = user_id
            print(f"Login: user_id set in session = {session['user_id']}")
            return jsonify({"status": "success", "message": "Login successful"}), 200
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401


@app.route('/register', methods=['GET', 'POST'])
async def register():
    if request.method == 'GET':
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({"status": "error", "message": "Не указан ID пользователя!"}), 400

        subjects = await get_all_subjects(user_id)
        schedule = create_schedule(subjects)

        return render_template('register.html', schedule=schedule, user_id=user_id)

    if request.method == 'POST':
        data = request.get_json()
        student_id = data.get('student_id')
        subject_id = data.get('subject_id')

        if not all([student_id, subject_id]):
            return jsonify({"status": "error", "message": "Не все данные предоставлены!"}), 400

        conn = await get_db_connection()
        async with conn.cursor() as cursor:
            try:
                # Проверяем, зарегистрирован ли уже студент на предмет
                await cursor.execute("""
                    SELECT COUNT(*) FROM student_registration 
                    WHERE student_id = %s AND subject_id = %s
                """, (student_id, subject_id))
                count = (await cursor.fetchone())[0]
                if count == 0:
                    # Если студент еще не зарегистрирован, добавляем запись
                    await cursor.execute("""
                                        INSERT INTO student_registration (student_id, subject_id)
                                        VALUES (%s, %s)
                                    """, (student_id, subject_id))
                    await conn.commit()
                    subjects = await get_all_subjects(student_id)  # Получение актуальных данных
                    print(subjects)  # Лог для проверки актуальности данных
                    return jsonify({"status": "success", "message": "Студент успешно зарегистрирован на предмет!"})
                else:
                    return jsonify({"status": "info", "message": "Студент уже зарегистрирован на этот предмет."})
            except Exception as e:
                print(f"Error during registration: {e}")
                await conn.rollback()
                return jsonify({"status": "error", "message": "Ошибка регистрации предмета"}), 500
            finally:
                conn.close()


@app.route('/unregister', methods=['POST'])
async def unregister():
    data = request.get_json()  # Без await, как вы уже сделали
    student_id = data.get('student_id')
    subject_id = data.get('subject_id')

    if not all([student_id, subject_id]):
        return jsonify({"status": "error", "message": "Не все данные предоставлены!"}), 400
    conn = await get_db_connection()
    async with conn.cursor() as cursor:
        try:
            # Логирование перед выполнением
            print(f"Attempting to unregister: student_id={student_id}, subject_id={subject_id}")

            await cursor.execute("""
                        DELETE FROM student_registration 
                        WHERE student_id = %s AND subject_id = %s
                    """, (student_id, subject_id))

            await conn.commit()
            subjects = await get_all_subjects(student_id)  # Получение актуальных данных
            print(subjects)  # Лог для проверки актуальности данных
            # Лог успешного удаления
            print(f"Successfully unregistered student_id={student_id} from subject_id={subject_id}")
            return jsonify({"status": "success", "message": "Регистрация успешно удалена!"})
        except Exception as e:
            print("Error unregistering:", e)
            await conn.rollback()
            return jsonify({"status": "error", "message": "Ошибка удаления регистрации"}), 500
        finally:
            conn.close()


async def get_all_subjects(user_id):
    conn = await get_db_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("""
                    SELECT s.id, s.name, sch.time, sch.day, s.language, s.teacher,
                           (SELECT COUNT(*) FROM student_registration sr WHERE sr.student_id = %s AND sr.subject_id = s.id) AS registered
                    FROM subjects s
                    JOIN schedule sch ON s.id = sch.subject_id
                """, (user_id,))
        subjects = await cursor.fetchall()
    conn.close()
    print(f"Subjects fetched for user_id={user_id}: {subjects}")  # Логирование
    return subjects


def create_schedule(subjects):
    schedule = {}
    for subject in subjects:
        day = subject[3]
        if day not in schedule:
            schedule[day] = []
        schedule[day].append(subject)
    return schedule


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
