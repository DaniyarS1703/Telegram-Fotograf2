from flask import Flask, render_template, request, redirect, url_for, jsonify
from models import db, Photographer, Client  # Предполагается, что модели UnavailableDate и Booking тоже присутствуют в models.py
import json
import cloudinary
import cloudinary.uploader
import cloudinary.api
from decimal import Decimal  # Для корректной работы с Numeric
from datetime import datetime   # Для работы с датами

app = Flask(__name__)

# --- Конфигурация Cloudinary ---
cloudinary.config(
    cloud_name="dshbfmrk6",  # Ваш cloud_name
    api_key="195559331354929",
    api_secret="xNrSk5vxRoVWZLzUSJvl4rCjOl0"
)

# При необходимости можно ограничить размер загружаемых файлов:
# app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB

# Настройка подключения к базе данных
app.config['SQLALCHEMY_DATABASE_URI'] = (
    "postgresql://telegram_gallery_db_0fzy_user:"
    "P4lxKsxTCWWuAZZUU6acovYiRbdyVAnv@dpg-cv5j92aj1k6c73d2enu0-a."
    "frankfurt-postgres.render.com:5432/telegram_gallery_db_0fzy"
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'my-very-secret-key'

db.init_app(app)

# Инициализация Flask-Migrate для поддержки миграций
from flask_migrate import Migrate
migrate = Migrate(app, db)

# Создаем таблицы, если они ещё не созданы (миграции обновляют уже существующие таблицы)
with app.app_context():
    db.create_all()

def load_cities_grouped():
    """
    Загружает список городов из файла data/cities.json и группирует их по стране,
    используя поле 'country_name' для страны.
    """
    try:
        with open('data/cities.json', 'r', encoding='utf-8') as f:
            cities_list = json.load(f)
        grouped = {}
        for city in cities_list:
            country = city.get('country_name', 'Неизвестно')
            if country not in grouped:
                grouped[country] = []
            grouped[country].append(city)
        return grouped
    except Exception as e:
        print("Ошибка загрузки городов:", e)
        return {"Россия": [{"name": "Москва"}, {"name": "Санкт-Петербург"}]}

@app.route('/', methods=['GET', 'HEAD'])
def index():
    if request.method == 'HEAD':
        return '', 200

    tg_id = request.args.get('tg_id')
    first_name = request.args.get('first_name', 'Клиент')
    cities_grouped = load_cities_grouped()

    if tg_id:
        client = Client.query.filter_by(telegram_id=tg_id).first()
        if not client:
            client = Client(
                telegram_id=tg_id,
                name=first_name,
                email="",
                phone="",
                description="",
                city="Москва",      # город по умолчанию
                country="Россия"    # страна по умолчанию
            )
            db.session.add(client)
            db.session.commit()
        else:
            if not client.country:
                client.country = "Россия"
                db.session.commit()
        orders = []  # Здесь можно получить заказы клиента
    else:
        client = None
        orders = []

    return render_template('index.html', client=client, orders=orders, cities_grouped=cities_grouped)

@app.route('/gallery')
def gallery():
    selected_city = request.args.get('city', 'Москва')
    tg_id = request.args.get('tg_id')
    client = None
    if tg_id:
        client = Client.query.filter_by(telegram_id=tg_id).first()
    photographers = Photographer.query.filter_by(city=selected_city).order_by(
        Photographer.rating.desc(), db.func.random()
    ).all()
    for p in photographers:
        p.portfolio_list = p.get_portfolio()
    cities_grouped = load_cities_grouped()
    return render_template('gallery.html', photographers=photographers,
                           selected_city=selected_city, cities_grouped=cities_grouped, client=client)

@app.route('/profile/<int:id>')
def profile(id):
    photographer = Photographer.query.get_or_404(id)
    photographer.portfolio_list = photographer.get_portfolio()
    # Извлекаем занятые даты фотографа из связанной модели UnavailableDate
    unavailable_dates = []
    for ud in photographer.unavailable_dates:
        unavailable_dates.append(ud.date.strftime("%d-%m-%Y"))
    unavailable_dates_str = ", ".join(unavailable_dates)
    
    tg_id = request.args.get('tg_id')
    client = None
    if tg_id:
        client = Client.query.filter_by(telegram_id=tg_id).first()
    
    return render_template('profile.html', 
                           photographer=photographer, 
                           unavailable_dates=unavailable_dates_str,
                           client=client)

@app.route('/update_city', methods=['POST'])
def update_city():
    data = request.get_json()
    tg_id = data.get('tg_id')
    city = data.get('city')
    if not tg_id or not city:
        return jsonify({'success': False}), 400
    client = Client.query.filter_by(telegram_id=tg_id).first()
    if client:
        client.city = city
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

@app.route('/update_country', methods=['POST'])
def update_country():
    data = request.get_json()
    tg_id = data.get('tg_id')
    country = data.get('country')
    if not tg_id or not country:
        return jsonify({'success': False}), 400
    client = Client.query.filter_by(telegram_id=tg_id).first()
    if client:
        client.country = country
        db.session.commit()
        return jsonify({'success': True})
    return jsonify({'success': False}), 404

# --- Новый маршрут для обновления аватара клиента ---
@app.route('/update_avatar', methods=['POST'])
def update_avatar():
    if 'avatar' not in request.files:
        return jsonify(success=False, error="Файл не найден"), 400
    file = request.files['avatar']
    if file.filename == '':
        return jsonify(success=False, error="Имя файла пустое"), 400
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    if '.' not in file.filename or file.filename.rsplit('.', 1)[1].lower() not in ALLOWED_EXTENSIONS:
        return jsonify(success=False, error="Недопустимый тип файла"), 400
    tg_id = request.form.get('tg_id')
    if not tg_id:
        return jsonify(success=False, error="tg_id не указан"), 400
    try:
        result = cloudinary.uploader.upload(file)
    except Exception as e:
        return jsonify(success=False, error=str(e)), 500
    avatar_url = result.get('secure_url')
    public_id = result.get('public_id')
    client = Client.query.filter_by(telegram_id=tg_id).first()
    if client:
        client.avatar = avatar_url
        client.avatar_public_id = public_id
        db.session.commit()
        return jsonify(success=True, avatar_url=avatar_url)
    else:
        return jsonify(success=False, error="Клиент не найден"), 404

@app.route('/switch_role', methods=['GET', 'POST'])
def switch_role():
    tg_id = request.args.get('tg_id')
    if not tg_id:
        return "Telegram данные не получены", 400

    client = Client.query.filter_by(telegram_id=tg_id).first()
    if not client:
        return "Клиент не найден", 404

    # Если фотограф уже существует, перенаправляем на профиль
    existing_photographer = Photographer.query.filter_by(telegram_id=client.telegram_id).first()
    if existing_photographer:
        return redirect(url_for('profile', id=existing_photographer.id))

    if request.method == 'POST':
        # Получаем поля формы
        about = request.form.get('about', '')
        experience = request.form.get('experience', '')
        equipment = request.form.get('equipment', '')

        # Загружаем аватар (если выбран)
        avatar_url = None
        avatar_public_id = None
        if 'avatar_file' in request.files:
            avatar_file = request.files['avatar_file']
            if avatar_file and avatar_file.filename:
                result = cloudinary.uploader.upload(avatar_file)
                avatar_url = result.get('secure_url')
                avatar_public_id = result.get('public_id')

        # Загружаем файлы портфолио (если выбрано несколько)
        portfolio_urls = []
        if 'portfolio_files' in request.files:
            portfolio_files = request.files.getlist('portfolio_files')
            for file in portfolio_files:
                if file and file.filename:
                    result = cloudinary.uploader.upload(file)
                    file_url = result.get('secure_url')
                    portfolio_urls.append(file_url)

        # Формируем описание, объединяя about и experience
        description = about
        if experience:
            description += f"\nОпыт: {experience}"

        new_photographer = Photographer(
            name=client.name,
            telegram_id=client.telegram_id,  # Связываем фотографа с Telegram ID клиента
            avatar=avatar_url if avatar_url else client.avatar,
            avatar_public_id=avatar_public_id if avatar_public_id else None,
            description=description,
            city=client.city,
            rating=Decimal("0.0"),
            portfolio=json.dumps(portfolio_urls) if portfolio_urls else json.dumps([])
        )
        db.session.add(new_photographer)
        db.session.commit()

        return redirect(url_for('profile', id=new_photographer.id))

    dummy_photographer = {
        "name": client.name,
        "avatar": None,  # Здесь можно указать путь к дефолтному аватару, если требуется
        "city": client.city,
        "rating": "0",
        "description": ""
    }
    return render_template('switch_role.html', client=client, photographer=dummy_photographer)

@app.route('/edit_profile/<int:id>', methods=['GET', 'POST'])
def edit_profile(id):
    photographer = Photographer.query.get_or_404(id)
    
    # Загружаем список городов
    cities_grouped = load_cities_grouped()
    cities = []
    for country, city_list in cities_grouped.items():
        for city in city_list:
            cities.append(city["name"])
    cities = sorted(set(cities))
    
    if request.method == 'POST':
        # Если пользователь отметил старые фото для удаления, удаляем их
        remove_list = request.form.getlist('remove_images')
        if remove_list:
            existing_portfolio = photographer.get_portfolio()
            updated_portfolio = [img for img in existing_portfolio if img not in remove_list]
            photographer.portfolio = json.dumps(updated_portfolio)
        
        # Обновляем текстовые поля
        photographer.name = request.form.get('name', photographer.name)
        photographer.city = request.form.get('city', photographer.city)
        photographer.description = request.form.get('description', photographer.description)
        
        # Если выбран новый аватар, обновляем его
        if 'avatar_file' in request.files:
            avatar_file = request.files['avatar_file']
            if avatar_file and avatar_file.filename:
                result = cloudinary.uploader.upload(avatar_file)
                photographer.avatar = result.get('secure_url')
                photographer.avatar_public_id = result.get('public_id')
        
        # Обработка новых файлов портфолио
        portfolio_files = request.files.getlist('portfolio_files')
        if portfolio_files:
            new_portfolio_urls = []
            for file in portfolio_files:
                if file and file.filename:
                    result = cloudinary.uploader.upload(file)
                    secure_url = result.get('secure_url')
                    if secure_url:
                        new_portfolio_urls.append(secure_url)
            if new_portfolio_urls:
                existing_portfolio = photographer.get_portfolio()
                updated_portfolio = existing_portfolio + new_portfolio_urls
                photographer.portfolio = json.dumps(updated_portfolio)
        
        db.session.commit()
        return redirect(url_for('profile', id=photographer.id))
    
    photographer.portfolio_list = photographer.get_portfolio()
    return render_template('edit_profile.html', photographer=photographer, cities=cities)

@app.route('/edit_calendar/<int:photographer_id>', methods=['POST'])
def edit_calendar(photographer_id):
    from models import UnavailableDate  # Убедитесь, что модель UnavailableDate определена в models.py
    photographer = Photographer.query.get_or_404(photographer_id)
    
    # Получаем строку дат, переданную из формы
    dates_str = request.form.get('unavailable_dates', '')
    
    # Удаляем все существующие записи занятых дат для этого фотографа
    UnavailableDate.query.filter_by(photographer_id=photographer.id).delete()
    
    if dates_str.strip():
        for d in dates_str.split(","):
            d = d.strip()
            if d:
                try:
                    date_obj = datetime.strptime(d, "%d-%m-%Y").date()
                    new_date = UnavailableDate(photographer_id=photographer.id, date=date_obj)
                    db.session.add(new_date)
                except ValueError:
                    pass
    
    db.session.commit()
    return jsonify({"success": True, "message": "Calendar updated"}), 200

@app.route('/book', methods=['POST'])
def book():
    photographer_id = request.form.get('photographer_id')
    client_id = request.form.get('client_id')
    booking_date_str = request.form.get('booking_date')  # Формат "дд-мм-гггг"
    booking_time_str = request.form.get('booking_time')  # Формат "чч:мм" (опционально)

    if not photographer_id or not client_id or not booking_date_str:
        return "Недостаточно данных для бронирования", 400

    try:
        booking_date = datetime.strptime(booking_date_str, "%d-%m-%Y").date()
        booking_time = None
        if booking_time_str:
            booking_time = datetime.strptime(booking_time_str, "%H:%M").time()
    except Exception as e:
        return f"Неверный формат даты или времени: {e}", 400

    from models import Booking  # Предполагается, что модель Booking уже добавлена в models.py
    new_booking = Booking(
        photographer_id=photographer_id,
        client_id=client_id,
        booking_date=booking_date,
        booking_time=booking_time,
        status='pending'
    )
    db.session.add(new_booking)
    db.session.commit()

    return redirect(url_for('profile', id=photographer_id))

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['GET', 'POST'])
def upload_file():
    if request.method == 'POST':
        if 'file' not in request.files:
            return "Файл не выбран", 400
        file = request.files['file']
        if file.filename == '':
            return "Имя файла пустое", 400
        if not allowed_file(file.filename):
            return "Недопустимый тип файла", 400
        try:
            result = cloudinary.uploader.upload(file)
            file_url = result.get("secure_url")
            return f"Файл успешно загружен: <a href='{file_url}' target='_blank'>{file_url}</a>"
        except Exception as e:
            return f"Ошибка при загрузке файла: {e}", 500
    return render_template('upload.html')

@app.route('/delete_avatar', methods=['POST'])
def delete_avatar():
    data = request.get_json()
    photographer_id = data.get('photographer_id')
    if not photographer_id:
        return jsonify({'success': False, 'error': 'Не указан идентификатор фотографа'}), 400
    photographer = Photographer.query.get(photographer_id)
    if not photographer:
        return jsonify({'success': False, 'error': 'Фотограф не найден'}), 404
    if not photographer.avatar_public_id:
        return jsonify({'success': False, 'error': 'Аватар отсутствует или не может быть удалён'}), 400
    try:
        result = cloudinary.uploader.destroy(photographer.avatar_public_id)
        if result.get('result') == 'ok':
            photographer.avatar = None
            photographer.avatar_public_id = None
            db.session.commit()
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Ошибка удаления на Cloudinary'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView

admin = Admin(app, name='Админ-панель', template_mode='bootstrap3')
admin.add_view(ModelView(Photographer, db.session))
admin.add_view(ModelView(Client, db.session))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
