from flask import Flask, request, jsonify, render_template, redirect, url_for, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import os
import json
import csv
from io import StringIO
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_

from models import db, Item

app = Flask(__name__)

# Получаем абсолютный путь к текущей директории
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Создаем папку instance, если её нет
INSTANCE_DIR = os.path.join(BASE_DIR, 'instance')
try:
    os.makedirs(INSTANCE_DIR)
except FileExistsError:
    pass

# Создаем полный путь к файлу базы данных
DATABASE_PATH = os.path.join(INSTANCE_DIR, 'sklad.db')

# Конфигурация базы данных
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + DATABASE_PATH
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
migrate = Migrate(app, db)

# Создаем таблицы базы данных, если их нет (ВНЕ обработчиков запросов!)
with app.app_context():
    db.create_all()

# Маршрут для добавления товара (POST /items)
@app.route('/items', methods=['POST'])
def add_item():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400

    name = data.get('name')
    quantity = data.get('quantity')
    price = data.get('price')
    category = data.get('category')

    if not name or quantity is None or price is None:
        return jsonify({"error": "Name, quantity, and price are required"}), 400

    try:
        quantity = int(quantity)
        price = float(price)
    except ValueError:
        return jsonify({"error": "Invalid quantity or price"}), 400

    if quantity < 0:
        return jsonify({"error": "Quantity cannot be negative"}), 400
    if price <= 0:
        return jsonify({"error": "Price must be positive"}), 400

    new_item = Item(name=name, quantity=quantity, price=price, category=category)
    db.session.add(new_item)
    db.session.commit()
    return jsonify(new_item.to_dict()), 201  # Возвращаем созданный объект и код 201


@app.route('/items/<int:item_id>', methods=['GET'])
def edit_item(item_id):
    """Отображает форму редактирования товара."""
    item = Item.query.get_or_404(item_id)
    return render_template('edit_item.html', item=item)

@app.route('/items/<int:item_id>', methods=['POST','PUT']) # Обрабатываем POST для PUT запросов
def update_item(item_id):
    """Обновляет товар."""
    item = Item.query.get_or_404(item_id)

    try:
        data = request.form
        item.name = data.get('name')
        item.quantity = int(data.get('quantity'))
        item.price = float(data.get('price'))
        item.category = data.get('category')

        if item.quantity < 0:
            return render_template('edit_item.html', item=item, error="Количество не может быть отрицательным")
        if item.price <= 0:
            return render_template('edit_item.html', item=item, error="Цена должна быть больше нуля")

        db.session.commit()
        return redirect(url_for('manage_items'))
    except ValueError:
        return render_template('edit_item.html', item=item, error="Некорректные значения для 'Количество' или 'Цена'")
    except SQLAlchemyError as e:
        db.session.rollback()
        return render_template('edit_item.html', item=item, error=f"Ошибка базы данных: {str(e)}")
    except Exception as e:
        return render_template('edit_item.html', item=item, error=f"Произошла ошибка: {str(e)}")

@app.route('/items/<int:item_id>/delete', methods=['GET'])
def delete_item(item_id):
    try:
        item = Item.query.get_or_404(item_id) # Получаем товар или возвращаем 404
        db.session.delete(item)
        db.session.commit()
        return redirect(url_for('manage_items')) # Перенаправляем на главную страницу
    except SQLAlchemyError as e:
        db.session.rollback() # Откатываем транзакцию в случае ошибки
        return jsonify({"error": f"Ошибка базы данных: {str(e)}"}), 500 # Возвращаем ошибку в формате JSON
    except Exception as e:
        return jsonify({"error": f"Произошла ошибка: {str(e)}"}), 500 # Обработка других исключений

# Маршрут для генерации отчета (GET /reports/summary)
@app.route('/reports/summary', methods=['GET'])
def get_report():
    try:
        items = Item.query.all()
        total_value = sum(item.quantity * item.price for item in items)
        categories = {}
        negative_items = []

        for item in items:
            if item.quantity <= 0:
                negative_items.append(item.to_dict())
            if item.category:
                categories.setdefault(item.category, {"count": 0, "value": 0})
                categories[item.category]["count"] += item.quantity
                categories[item.category]["value"] += item.quantity * item.price

        report = {
            "total_value": str(total_value),
            "categories": categories,
            "negative_items": negative_items
        }

        format = request.args.get('format', 'html').lower()

        if format == 'csv':
            output = StringIO()
            writer = csv.writer(output)
            writer.writerow(["Category", "Count", "Value"])
            for cat, data in categories.items():
                writer.writerow([cat, data["count"], data["value"]])

            response = make_response(output.getvalue()) # Создаем ответ Flask
            response.headers['Content-Type'] = 'text/csv'
            response.headers['Content-Disposition'] = 'attachment; filename=report.csv'
            return response

        elif format == 'json':
            return jsonify(report)
        else:
            return render_template('report.html', report=report)

    except SQLAlchemyError as e:
        db.session.rollback()
        return jsonify({"error": f"Ошибка базы данных: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"error": f"Произошла ошибка: {str(e)}"}), 500
    
@app.route('/manage_items', methods=['GET', 'POST'])
def manage_items():
    if request.method == 'POST':
        name = request.form.get('name')
        quantity = request.form.get('quantity')
        price = request.form.get('price')
        category = request.form.get('category')

        if not name or not quantity or not price:
            return render_template('manage_items.html', error="Поля 'Название', 'Количество' и 'Цена' обязательны для заполнения", items=Item.query.all())

        try:
            quantity = int(quantity)
            price = float(price)
        except ValueError:
            return render_template('manage_items.html', error="Некорректные значения для 'Количество' или 'Цена'", items=Item.query.all())

        if quantity < 0:
            return render_template('manage_items.html', error="Количество не может быть отрицательным", items=Item.query.all())
        if price <= 0:
            return render_template('manage_items.html', error="Цена должна быть больше нуля", items=Item.query.all())

        new_item = Item(name=name, quantity=quantity, price=price, category=category)
        db.session.add(new_item)
        db.session.commit()
        return redirect(url_for('manage_items'))

    items = Item.query.all()
    return render_template('manage_items.html', items=items)

# Главная страница (редирект на /manage_items)
@app.route('/', methods=['GET']) # Изменяем маршрут на главную страницу
@app.route('/items', methods=['GET'])
def get_items():
    category = request.args.get('category')
    search = request.args.get('search')  # Получаем поисковый запрос

    items = Item.query

    if category:
        items = items.filter_by(category=category)

    if search:
        items = items.filter(or_(Item.name.ilike(f"%{search}%"), Item.category.ilike(f"%{search}%")))

    items = items.all()

    if request.path == '/':
        categories = list(set([item.category for item in items if item.category is not None]))
        return render_template('manage_items.html', items=items, categories=categories)
    return jsonify([item.to_dict() for item in items])

if __name__ == '__main__':
    with app.app_context():
        db.create_all() # Можно убрать после первой миграции
    app.run(debug=True)