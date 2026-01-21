# Github репозиторий проекта анализа отзывов отелей/гостиниц

В директории project находится презентация выступления 7 группы, а так же отчет и табличка с графиками по частотности слов и распределения оценок

# Parser

В директории parser представлен код локального скрапера сайта Otzovik.com, написанного на Python + BeautifulSoup

## 1. Установите окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
## или
venv\Scripts\activate  # Windows

## 2. Установите зависимости
pip install -r requirements.txt

## 3. Запустите парсер
python parser.py

## 4. Результат .csv
Всего отелей: 7821

Всего отзывов: 47781

# Qr-код на Datalens

![Qr-code](qr-code.png)
