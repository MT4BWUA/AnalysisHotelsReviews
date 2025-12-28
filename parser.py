#!/usr/bin/env python3
"""
Парсер отзывов с Otzyovik.com для macOS
Версия с оценкой отзыва и признаком "до 2020"
Ускоренная версия с задержками 1-2 секунды
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random
import re
import json
import os
import sys
from datetime import datetime
from urllib.parse import urljoin
from typing import Optional, List, Dict, Any

# Импортируем Config из config.py
from config import Config


# ===================== ОСНОВНОЙ ПАРСЕР =====================
class OtzyovikParser:
    """Парсер Otzyovik.com с оценкой отзыва и признаком "до 2020" """

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()

        # Установка задержек 1-2 секунды везде
        self.config.DELAY_MIN = 3.0
        self.config.DELAY_MAX = 5.0
        self.config.DELAY_BETWEEN_HOTELS_MIN = 3.0
        self.config.DELAY_BETWEEN_HOTELS_MAX = 5.0
        self.config.DELAY_BETWEEN_PAGES_MIN = 3.0
        self.config.DELAY_BETWEEN_PAGES_MAX = 5.0
        self.config.DELAY_AFTER_BLOCK = 10  # Уменьшили с 30 до 10 при блокировке

        # Проверяем наличие атрибута TIMEOUT
        if not hasattr(self.config, 'TIMEOUT'):
            print("⚠️  Внимание: у конфигурации нет атрибута TIMEOUT, устанавливаю 10")
            self.config.TIMEOUT = 10

        self.session = self._create_session()

        # Состояние парсера
        self.results = []
        self.processed_hotels = set()
        self.processed_pages = set()
        self.total_requests = 0
        self.blocked_count = 0
        self.start_time = datetime.now()

        # Создаем папки для данных
        os.makedirs('data', exist_ok=True)
        os.makedirs('logs', exist_ok=True)

        # Настройка логирования
        self._setup_logging()

        # Загрузка прогресса
        self._load_progress()

    def _setup_logging(self):
        """Настройка логирования"""
        import logging

        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('logs/otzovik_parser.log', encoding='utf-8'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        self.logger = logging.getLogger(__name__)

    def _create_session(self):
        """Создание HTTP-сессии с реалистичными заголовками"""
        session = requests.Session()

        # Выбираем случайный User-Agent
        user_agent = random.choice(self.config.USER_AGENTS)

        # macOS-специфичные заголовки браузера
        headers = {
            'User-Agent': user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'DNT': '1',
            'Referer': 'https://otzovik.com/',
        }

        session.headers.update(headers)

        # Добавляем cookies для имитации реального пользователя
        session.cookies.update({
            'otz_view': 'list',
            'otz_region': '77',
        })

        return session

    def _random_delay(self, min_delay=None, max_delay=None):
        """Случайная задержка между запросами"""
        min_val = min_delay or self.config.DELAY_MIN
        max_val = max_delay or self.config.DELAY_MAX
        delay = random.uniform(min_val, max_val)
        time.sleep(delay)

    def _is_blocked_response(self, response):
        """Проверка, заблокирован ли доступ"""
        if not response:
            return False

        # Проверка кодов состояния
        if response.status_code in [403, 429, 503]:
            return True

        # Проверка содержимого на признаки блокировки
        if response.text:
            text_lower = response.text.lower()
            block_indicators = [
                'captcha', 'recaptcha', 'cloudflare', 'доступ ограничен',
                'your access has been blocked', 'blocked', '403 forbidden',
                'too many requests', 'rate limit exceeded'
            ]

            if any(indicator in text_lower for indicator in block_indicators):
                return True

            # Слишком короткий ответ тоже подозрителен
            if len(response.text) < 1000 and 'product-list' not in response.text:
                return True

        return False

    def _load_progress(self):
        """Загрузка прогресса из файла"""
        if os.path.exists(self.config.PROGRESS_FILE):
            try:
                with open(self.config.PROGRESS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                    self.processed_hotels = set(data.get('processed_hotels', []))
                    self.processed_pages = set(data.get('processed_pages', []))
                    self.results = data.get('results', [])
                    self.total_requests = data.get('total_requests', 0)
                    self.blocked_count = data.get('blocked_count', 0)

                self.logger.info(f"Загружен прогресс: {len(self.processed_pages)} страниц, "
                                 f"{len(self.processed_hotels)} отелей, {len(self.results)} отзывов")

            except Exception as e:
                self.logger.error(f"Ошибка загрузки прогресса: {e}")
                print(f"⚠️  Не удалось загрузить прогресс: {e}")

    def _save_progress(self):
        """Сохранение прогресса в файл"""
        try:
            data = {
                'processed_hotels': list(self.processed_hotels),
                'processed_pages': list(self.processed_pages),
                'results': self.results,
                'total_requests': self.total_requests,
                'blocked_count': self.blocked_count,
                'last_updated': datetime.now().isoformat(),
                'parser_version': '3.2',  # Обновили версию
                'delays_config': {
                    'DELAY_MIN': self.config.DELAY_MIN,
                    'DELAY_MAX': self.config.DELAY_MAX,
                    'DELAY_BETWEEN_HOTELS_MIN': self.config.DELAY_BETWEEN_HOTELS_MIN,
                    'DELAY_BETWEEN_HOTELS_MAX': self.config.DELAY_BETWEEN_HOTELS_MAX,
                    'DELAY_BETWEEN_PAGES_MIN': self.config.DELAY_BETWEEN_PAGES_MIN,
                    'DELAY_BETWEEN_PAGES_MAX': self.config.DELAY_BETWEEN_PAGES_MAX,
                    'DELAY_AFTER_BLOCK': self.config.DELAY_AFTER_BLOCK
                }
            }

            with open(self.config.PROGRESS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            # Резервная копия
            backup_file = f"data/progress_backup_{int(time.time())}.json"
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            self.logger.debug("Прогресс сохранен")

        except Exception as e:
            self.logger.error(f"Ошибка сохранения прогресса: {e}")
            print(f"⚠️  Ошибка сохранения прогресса: {e}")

    def _save_results(self):
        """Сохранение результатов в CSV и JSON"""
        if not self.results:
            self.logger.warning("Нет данных для сохранения")
            return

        try:
            df = pd.DataFrame(self.results)

            # Удаляем дубликаты по ID отзыва
            if 'review_id' in df.columns:
                initial_count = len(df)
                df = df.drop_duplicates(subset=['review_id'], keep='last')
                removed = initial_count - len(df)
                if removed > 0:
                    self.logger.info(f"Удалено {removed} дубликатов отзывов")

            # Анализ признака "до 2020"
            if 'before_2020' in df.columns:
                before_2020_count = df['before_2020'].sum() if df['before_2020'].dtype == 'bool' else 0
                self.logger.info(
                    f"Отзывов до 2020 года: {before_2020_count} ({before_2020_count / len(df) * 100:.1f}%)")

            # Анализ оценок отзывов
            if 'review_rating_numeric' in df.columns:
                avg_rating = df['review_rating_numeric'].mean()
                self.logger.info(f"Средняя оценка отзывов: {avg_rating:.2f}")

            # Сохраняем в CSV
            csv_path = self.config.OUTPUT_FILE
            df.to_csv(csv_path, index=False, encoding='utf-8-sig')

            # Также сохраняем в JSON для удобства
            json_path = csv_path.replace('.csv', '.json')
            df.to_json(json_path, orient='records', force_ascii=False, indent=2)

            self.logger.info(f"Сохранено {len(df)} отзывов в {csv_path} и {json_path}")
            print(f"💾 Сохранено {len(df)} отзывов")

        except Exception as e:
            self.logger.error(f"Ошибка сохранения результатов: {e}")
            print(f"⚠️  Ошибка сохранения результатов: {e}")

    def make_request(self, url: str, referer: Optional[str] = None, retry_count: int = 0):
        """Выполнение HTTP-запроса с обработкой ошибок"""
        self.total_requests += 1

        # Задержка перед запросом (1-2 сек)
        self._random_delay()

        try:
            # Обновляем Referer если указан
            if referer:
                self.session.headers['Referer'] = referer

            # Делаем запрос с таймаутом из конфигурации
            response = self.session.get(url, timeout=self.config.TIMEOUT)

            # Проверяем на блокировку
            if self._is_blocked_response(response):
                self.blocked_count += 1
                self.logger.warning(f"Обнаружена блокировка при запросе к {url}")

                if retry_count < self.config.MAX_RETRIES:
                    wait_time = self.config.DELAY_AFTER_BLOCK * (retry_count + 1)
                    self.logger.info(f"Повторная попытка через {wait_time} сек...")
                    time.sleep(wait_time)

                    # Меняем User-Agent для обхода блокировки
                    new_agent = random.choice(self.config.USER_AGENTS)
                    self.session.headers['User-Agent'] = new_agent

                    return self.make_request(url, referer, retry_count + 1)
                else:
                    self.logger.error(f"Превышено максимальное количество попыток для {url}")
                    return None

            # Проверяем статус ответа
            if response.status_code == 200:
                # Проверяем, что это HTML и содержит данные
                if ('text/html' in response.headers.get('Content-Type', '') and
                        len(response.text) > 1000):
                    return response.text
                else:
                    self.logger.warning(f"Невалидный ответ от {url}: "
                                        f"тип={response.headers.get('Content-Type')}, "
                                        f"размер={len(response.text)}")
                    return None

            elif response.status_code == 404:
                self.logger.warning(f"Страница не найдена: {url}")
                return None

            else:
                self.logger.warning(f"HTTP {response.status_code} от {url}")
                return None

        except requests.exceptions.Timeout:
            self.logger.warning(f"Таймаут при запросе к {url}")
            if retry_count < self.config.MAX_RETRIES:
                time.sleep(2 * (retry_count + 1))  # Уменьшено задержки при таймауте
                return self.make_request(url, referer, retry_count + 1)
            return None

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Ошибка сети при запросе к {url}: {e}")
            if retry_count < self.config.MAX_RETRIES:
                time.sleep(1 * (retry_count + 1))  # Уменьшено задержки при ошибке сети
                return self.make_request(url, referer, retry_count + 1)
            return None

    def get_list_page_url(self, page_num: int) -> str:
        """Формирование URL для страницы списка отелей"""
        if page_num == 1:
            return self.config.BASE_URL

        return f"{self.config.BASE_URL}{page_num}/"

    def parse_list_page(self, html: str, page_num: int, page_url: str) -> List[Dict[str, Any]]:
        """Парсинг страницы со списком отелей"""
        soup = BeautifulSoup(html, 'html.parser')
        hotels = []

        # Ищем контейнеры с отелями
        containers = soup.select(self.config.SELECTORS_LIST['hotel_container'])

        if not containers:
            self.logger.warning(f"На странице {page_num} не найдено отелей")
            return hotels

        self.logger.info(f"На странице {page_num} найдено {len(containers)} отелей")

        for container in containers[:self.config.MAX_HOTELS_PER_PAGE]:
            try:
                # Ссылка на страницу отеля
                link_elem = container.select_one(self.config.SELECTORS_LIST['hotel_link'])
                if not link_elem or not link_elem.get('href'):
                    continue

                # Полный URL страницы отеля
                hotel_url = link_elem['href']
                if not hotel_url.startswith('http'):
                    hotel_url = urljoin('https://otzovik.com', hotel_url)

                # Название отеля
                hotel_name = link_elem.text.strip()

                # Количество отзывов
                count_elem = container.select_one(self.config.SELECTORS_LIST['reviews_count'])
                review_count = 0
                if count_elem:
                    match = re.search(r'(\d+)', count_elem.text)
                    review_count = int(match.group()) if match else 0

                # Рейтинг отеля
                rating_elem = container.select_one(self.config.SELECTORS_LIST['rating'])
                hotel_rating = rating_elem.text.strip() if rating_elem else 'Нет'

                # ID отеля (генерируем из URL)
                hotel_id = f"hotel_{abs(hash(hotel_url)) % 1000000:06d}"

                hotels.append({
                    'id': hotel_id,
                    'name': hotel_name,
                    'url': hotel_url,
                    'reviews_count': review_count,
                    'hotel_rating': hotel_rating,  # Рейтинг отеля
                    'list_page': page_num,
                    'list_url': page_url,
                })

            except Exception as e:
                self.logger.error(f"Ошибка парсинга отеля: {e}")
                continue

        return hotels

    def extract_review_date(self, review_item) -> Dict[str, str]:
        """Извлечение даты отзыва разными способами"""
        date_data = {
            'display': '',
            'iso': '',
            'raw': '',
            'year': '',
            'month': '',
            'day': ''
        }

        try:
            # Способ 1: Из элемента с классом review-postdate
            date_elem = review_item.select_one(self.config.SELECTORS_HOTEL['review_date'])

            if date_elem:
                # Пробуем взять из атрибута content (ISO формат)
                if date_elem.has_attr('content'):
                    date_raw = date_elem['content']
                    date_data['raw'] = date_raw

                    # Пробуем преобразовать в datetime
                    try:
                        if date_raw.endswith('Z'):
                            date_raw = date_raw[:-1] + '+00:00'

                        dt = datetime.fromisoformat(date_raw)
                        date_data['iso'] = dt.isoformat()
                        date_data['display'] = dt.strftime('%d.%m.%Y')  # Формат DD.MM.YYYY
                        date_data['year'] = str(dt.year)
                        date_data['month'] = f"{dt.month:02d}"
                        date_data['day'] = f"{dt.day:02d}"
                    except ValueError:
                        date_data['display'] = date_elem.text.strip()

                # Если нет content, берем текст
                elif date_elem.text:
                    date_text = date_elem.text.strip()
                    date_data['display'] = date_text

                    # Пробуем извлечь дату из текста
                    date_patterns = [
                        r'(\d{1,2})\s+([а-я]+)\s+(\d{4})',  # 8 окт 2025
                        r'(\d{1,2})\.(\d{1,2})\.(\d{4})',  # 08.10.2025
                        r'(\d{4})-(\d{1,2})-(\d{1,2})',  # 2025-10-08
                    ]

                    for pattern in date_patterns:
                        match = re.search(pattern, date_text, re.IGNORECASE)
                        if match:
                            date_data['raw'] = date_text
                            # Пробуем преобразовать найденную дату
                            if pattern == r'(\d{1,2})\s+([а-я]+)\s+(\d{4})':
                                day, month_ru, year = match.groups()
                                # Преобразуем русские названия месяцев
                                months_ru = {
                                    'января': '01', 'февраля': '02', 'марта': '03',
                                    'апреля': '04', 'мая': '05', 'июня': '06',
                                    'июля': '07', 'августа': '08', 'сентября': '09',
                                    'октября': '10', 'ноября': '11', 'декабря': '12'
                                }
                                month = months_ru.get(month_ru.lower(), '01')
                                date_data['year'] = year
                                date_data['month'] = month
                                date_data['day'] = f"{int(day):02d}"
                                date_data['display'] = f"{day}.{month}.{year}"
                            break

            # Способ 2: Из meta-тега с itemprop="datePublished"
            if not date_data['display']:
                meta_elem = review_item.select_one(self.config.SELECTORS_HOTEL['review_date_meta'])
                if meta_elem and meta_elem.has_attr('content'):
                    date_raw = meta_elem['content']
                    date_data['raw'] = date_raw

                    try:
                        if date_raw.endswith('Z'):
                            date_raw = date_raw[:-1] + '+00:00'

                        dt = datetime.fromisoformat(date_raw)
                        date_data['iso'] = dt.isoformat()
                        date_data['display'] = dt.strftime('%d.%m.%Y')
                        date_data['year'] = str(dt.year)
                        date_data['month'] = f"{dt.month:02d}"
                        date_data['day'] = f"{dt.day:02d}"
                    except ValueError:
                        date_data['display'] = date_raw

            # Способ 3: Ищем дату в тексте отзыва
            if not date_data['display']:
                # Пробуем найти дату в любом месте
                for elem in review_item.find_all(text=True):
                    text = elem.string if elem else ''
                    if text:
                        # Ищем паттерны дат
                        patterns = [
                            r'\d{1,2}\s+[а-я]+\s+\d{4}',
                            r'\d{1,2}\.\d{1,2}\.\d{4}',
                            r'\d{4}-\d{1,2}-\d{1,2}',
                        ]

                        for pattern in patterns:
                            match = re.search(pattern, text, re.IGNORECASE)
                            if match:
                                date_data['display'] = match.group()
                                date_data['raw'] = match.group()
                                break

                    if date_data['display']:
                        break

        except Exception as e:
            self.logger.error(f"Ошибка извлечения даты: {e}")

        return date_data

    def extract_review_rating(self, review_item) -> Dict[str, Any]:
        """Извлечение оценки отзыва"""
        rating_data = {
            'text': '',
            'numeric': None,
            'stars': None
        }

        try:
            # Ищем элемент с оценкой отзыва
            rating_elem = review_item.select_one(self.config.SELECTORS_HOTEL['review_rating'])

            if rating_elem:
                rating_text = rating_elem.text.strip()
                rating_data['text'] = rating_text

                # Пробуем извлечь числовую оценку
                # Форматы: "5,0", "4,5", "5" и т.д.
                match = re.search(r'(\d+)[,\.]?(\d*)', rating_text.replace(',', '.'))
                if match:
                    if match.group(2):  # Есть дробная часть
                        rating_num = float(f"{match.group(1)}.{match.group(2)}")
                    else:
                        rating_num = float(match.group(1))

                    rating_data['numeric'] = rating_num

                    # Определяем количество звезд (округление до 0.5)
                    if rating_num >= 4.5:
                        rating_data['stars'] = 5
                    elif rating_num >= 3.5:
                        rating_data['stars'] = 4
                    elif rating_num >= 2.5:
                        rating_data['stars'] = 3
                    elif rating_num >= 1.5:
                        rating_data['stars'] = 2
                    else:
                        rating_data['stars'] = 1

        except Exception as e:
            self.logger.error(f"Ошибка извлечения оценки: {e}")

        return rating_data

    def parse_hotel_page(self, html: str, hotel_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Парсинг страницы отеля с отзывами"""
        soup = BeautifulSoup(html, 'html.parser')
        reviews = []

        # Ищем все отзывы на странице
        review_items = soup.select(self.config.SELECTORS_HOTEL['review_item'])

        if not review_items:
            self.logger.info(f"На странице отеля '{hotel_data['name']}' не найдено отзывов")
            return reviews

        self.logger.info(f"На странице отеля '{hotel_data['name']}' найдено {len(review_items)} отзывов")

        for idx, item in enumerate(review_items[:self.config.MAX_REVIEWS_PER_HOTEL], 1):
            try:
                # ============ ИЗВЛЕЧЕНИЕ ОЦЕНКИ ОТЗЫВА ============
                rating_data = self.extract_review_rating(item)

                if rating_data['numeric']:
                    self.logger.debug(f"Отзыв {idx}: оценка {rating_data['numeric']}")

                # ============ ИЗВЛЕЧЕНИЕ ДАТЫ ОТЗЫВА ============
                date_data = self.extract_review_date(item)

                # Признак "до 2020"
                before_2020 = False
                if date_data['year'] and date_data['year'].isdigit():
                    year = int(date_data['year'])
                    before_2020 = year < 2020

                if date_data['display']:
                    self.logger.debug(f"Отзыв {idx}: дата '{date_data['display']}', до 2020: {before_2020}")

                # Заголовок отзыва
                title_elem = item.select_one(self.config.SELECTORS_HOTEL['review_title'])
                title = title_elem.text.strip() if title_elem else ''

                # Текст отзыва (краткий)
                teaser_elem = item.select_one(self.config.SELECTORS_HOTEL['review_teaser'])
                teaser = teaser_elem.text.strip() if teaser_elem else ''

                # Достоинства
                plus_elem = item.select_one(self.config.SELECTORS_HOTEL['review_plus'])
                plus_text = ''
                if plus_elem:
                    plus_text = plus_elem.text.strip()
                    if plus_text.startswith('Достоинства:'):
                        plus_text = plus_text[12:].strip()

                # Недостатки
                minus_elem = item.select_one(self.config.SELECTORS_HOTEL['review_minus'])
                minus_text = ''
                if minus_elem:
                    minus_text = minus_elem.text.strip()
                    if minus_text.startswith('Недостатки:'):
                        minus_text = minus_text[11:].strip()

                # Автор отзыва
                author_elem = item.select_one(self.config.SELECTORS_HOTEL['review_author'])
                author = author_elem.text.strip() if author_elem else ''

                # Местоположение автора
                location_elem = item.select_one(self.config.SELECTORS_HOTEL['review_author_location'])
                location = location_elem.text.strip() if location_elem else ''

                # Количество рекомендаций (лайков)
                rec_elem = item.select_one(self.config.SELECTORS_HOTEL['review_recommendations'])
                recommendations = 0
                if rec_elem:
                    rec_text = rec_elem.text.strip()
                    if rec_text.isdigit():
                        recommendations = int(rec_text)

                # Количество комментариев
                comments_elem = item.select_one(self.config.SELECTORS_HOTEL['review_comments'])
                comments = 0
                if comments_elem:
                    comments_text = comments_elem.text.strip()
                    if comments_text.isdigit():
                        comments = int(comments_text)

                # Изображения в отзыве
                image_elems = item.select(self.config.SELECTORS_HOTEL['review_images'])
                images = []
                for img in image_elems:
                    if img.get('src'):
                        images.append(img['src'])

                # Формируем полный текст отзыва
                text_parts = []
                if title:
                    text_parts.append(f"Заголовок: {title}")
                if teaser:
                    text_parts.append(f"Текст: {teaser}")
                if plus_text:
                    text_parts.append(f"Достоинства: {plus_text}")
                if minus_text:
                    text_parts.append(f"Недостатки: {minus_text}")

                full_text = '\n\n'.join(text_parts) if text_parts else ''

                # Генерируем уникальный ID отзыва
                review_id = f"{hotel_data['id']}_review_{idx}_{abs(hash(title + date_data['display'])) % 10000:04d}"

                # Собираем данные отзыва
                review = {
                    'review_id': review_id,
                    'hotel_id': hotel_data['id'],
                    'hotel_name': hotel_data['name'],
                    'hotel_url': hotel_data['url'],
                    'hotel_rating': hotel_data['hotel_rating'],  # Рейтинг отеля в целом

                    # Оценка отзыва (ОСНОВНОЕ НОВОВВЕДЕНИЕ)
                    'review_rating_text': rating_data['text'],  # Текстовая оценка (например, "5,0")
                    'review_rating_numeric': rating_data['numeric'],  # Числовая оценка (float)
                    'review_rating_stars': rating_data['stars'],  # Количество звезд (1-5)

                    # Данные отзыва
                    'review_title': title,
                    'review_text': full_text,
                    'review_teaser': teaser,
                    'review_plus': plus_text,
                    'review_minus': minus_text,

                    # Даты
                    'review_date': date_data['display'],  # Человекочитаемый формат (DD.MM.YYYY)
                    'review_date_iso': date_data['iso'],  # ISO формат
                    'review_date_raw': date_data['raw'],  # Оригинальный raw формат
                    'review_year': date_data['year'],  # Год отдельно
                    'review_month': date_data['month'],  # Месяц отдельно
                    'review_day': date_data['day'],  # День отдельно

                    # Признак "до 2020" (ВТОРОЕ НОВОВВЕДЕНИЕ)
                    'before_2020': before_2020,  # True если отзыв до 2020 года

                    # Автор
                    'review_author': author,
                    'review_author_location': location,

                    # Взаимодействия
                    'recommendations': recommendations,
                    'comments': comments,
                    'images_count': len(images),
                    'images': '; '.join(images) if images else '',

                    # Мета-данные
                    'list_page': hotel_data['list_page'],
                    'scraped_at': datetime.now().isoformat(),
                }

                reviews.append(review)

            except Exception as e:
                self.logger.error(f"Ошибка парсинга отзыва {idx}: {e}")
                continue

        return reviews

    def scrape_page(self, page_num: int) -> bool:
        """Сбор данных с одной страницы списка отелей"""
        if page_num in self.processed_pages:
            self.logger.info(f"Страница {page_num} уже обработана, пропускаем")
            return True

        self.logger.info(f"Начинаю обработку страницы {page_num}")
        print(f"\n📄 Страница {page_num}: ", end='')

        # Формируем URL страницы списка
        page_url = self.get_list_page_url(page_num)
        print(f"Загружаю {page_url}")

        # Загружаем страницу списка отелей
        html = self.make_request(page_url)
        if not html:
            self.logger.error(f"Не удалось загрузить страницу списка {page_num}")
            print(f"❌ Не удалось загрузить страницу {page_num}")
            return False

        print(f"✅ Страница загружена")

        # Парсим список отелей
        hotels = self.parse_list_page(html, page_num, page_url)

        if not hotels:
            self.logger.warning(f"На странице {page_num} не найдено отелей")
            self.processed_pages.add(page_num)
            self._save_progress()
            return True

        print(f"🏨 Найдено отелей: {len(hotels)}")
        print(f"🔍 Начинаю сбор отзывов...")

        total_reviews_collected = 0
        total_before_2020 = 0

        # Обрабатываем каждый отель
        for i, hotel in enumerate(hotels, 1):
            print(f"   {i:2d}/{len(hotels)}: {hotel['name'][:50]}...", end=' ')

            # Пропускаем уже обработанные отели
            if hotel['url'] in self.processed_hotels:
                print("⏭️ уже обработан")
                continue

            # Пропускаем отели без отзывов
            if hotel['reviews_count'] == 0:
                print("📭 нет отзывов")
                self.processed_hotels.add(hotel['url'])
                continue

            print(f"({hotel['reviews_count']} отзывов)")

            # Загружаем страницу отеля
            hotel_html = self.make_request(hotel['url'], referer=page_url)

            if not hotel_html:
                print(f"      ❌ Не удалось загрузить страницу отеля")
                continue

            # Парсим отзывы на странице отеля
            reviews = self.parse_hotel_page(hotel_html, hotel)

            if reviews:
                self.results.extend(reviews)
                total_reviews_collected += len(reviews)

                # Считаем отзывы до 2020
                before_2020_count = sum(1 for r in reviews if r.get('before_2020'))
                total_before_2020 += before_2020_count

                print(f"      ✅ Собрано {len(reviews)} отзывов")
                print(
                    f"         📊 Средняя оценка: {sum(r.get('review_rating_numeric', 0) for r in reviews) / len(reviews):.1f}")
                print(f"         🗓️  До 2020 года: {before_2020_count} отзывов")

                # Выводим информацию по первым отзывам
                for review in reviews[:2]:
                    rating = review.get('review_rating_numeric', 0)
                    date = review.get('review_date', 'нет даты')
                    before_2020 = review.get('before_2020', False)
                    print(f"         ⭐ {rating:.1f} | {date} | {'до 2020' if before_2020 else 'после 2020'}")

                if len(reviews) > 2:
                    print(f"         ... и еще {len(reviews) - 2} отзывов")
            else:
                print(f"      ⚠️  Отзывы не найдены")

            # Помечаем отель как обработанный
            self.processed_hotels.add(hotel['url'])

            # Сохраняем прогресс каждые 10 отелей
            if i % 10 == 0:
                self._save_progress()
                self._save_results()

            # Задержка между отелями (1-2 сек)
            if i < len(hotels):
                delay = random.uniform(
                    self.config.DELAY_BETWEEN_HOTELS_MIN,
                    self.config.DELAY_BETWEEN_HOTELS_MAX
                )
                if delay > 0:
                    time.sleep(delay)

        # Помечаем страницу как обработанную
        self.processed_pages.add(page_num)
        self._save_progress()
        self._save_results()

        print(f"\n📊 Страница {page_num} завершена")
        print(f"   Отелей обработано: {len([h for h in hotels if h['url'] in self.processed_hotels])}/{len(hotels)}")
        print(f"   Отзывов собрано: {total_reviews_collected}")
        print(f"   Отзывов до 2020 года: {total_before_2020}")

        return True

    def run(self, start_page: int = 1, end_page: int = None):
        """Основной метод запуска парсера"""
        if end_page is None:
            end_page = self.config.MAX_PAGES

        print("=" * 70)
        print("🚀 ПАРСЕР OTZOVIK.COM - ЗАПУСК (СКОРОСТНАЯ ВЕРСИЯ)")
        print("=" * 70)
        print(f"📅 Начало работы: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"📄 Диапазон страниц: {start_page} - {end_page}")
        print(f"⚡ ВСЕ ЗАДЕРЖКИ УСТАНОВЛЕНЫ В 1-2 СЕКУНДЫ:")
        print(f"   • Между запросами: {self.config.DELAY_MIN:.1f}-{self.config.DELAY_MAX:.1f} сек")
        print(
            f"   • Между отелями: {self.config.DELAY_BETWEEN_HOTELS_MIN:.1f}-{self.config.DELAY_BETWEEN_HOTELS_MAX:.1f} сек")
        print(
            f"   • Между страницами: {self.config.DELAY_BETWEEN_PAGES_MIN:.1f}-{self.config.DELAY_BETWEEN_PAGES_MAX:.1f} сек")
        print(
            f"💾 Прогресс: {len(self.processed_pages)} стр., {len(self.processed_hotels)} отелей, {len(self.results)} отзывов")
        print("=" * 70)

        successful_pages = 0

        try:
            for page_num in range(start_page, end_page + 1):
                print(f"\n{'=' * 50}")
                print(f"🌀 ОБРАБОТКА СТРАНИЦЫ {page_num}/{end_page}")

                success = self.scrape_page(page_num)

                if success:
                    successful_pages += 1

                # Задержка между страницами (1-2 сек)
                if page_num < end_page:
                    delay = random.uniform(
                        self.config.DELAY_BETWEEN_PAGES_MIN,
                        self.config.DELAY_BETWEEN_PAGES_MAX
                    )
                    if delay > 0:
                        print(f"\n⏳ Пауза {delay:.1f} сек перед следующей страницей...")
                        time.sleep(delay)

            # Финальный отчет
            elapsed_time = datetime.now() - self.start_time

            # Статистика по оценкам и годам
            if self.results:
                ratings = [r.get('review_rating_numeric', 0) for r in self.results if r.get('review_rating_numeric')]
                before_2020_count = sum(1 for r in self.results if r.get('before_2020'))

                avg_rating = sum(ratings) / len(ratings) if ratings else 0
                before_2020_percent = (before_2020_count / len(self.results)) * 100 if self.results else 0

            print("\n" + "=" * 70)
            print("✅ СКРАПИНГ ЗАВЕРШЕН!")
            print("=" * 70)
            print(f"📊 СТАТИСТИКА:")
            print(f"   Успешных страниц: {successful_pages}/{end_page - start_page + 1}")
            print(f"   Обработано отелей: {len(self.processed_hotels)}")
            print(f"   Собрано отзывов: {len(self.results)}")

            if self.results:
                print(f"   Средняя оценка отзывов: {avg_rating:.2f}")
                print(f"   Отзывов до 2020 года: {before_2020_count} ({before_2020_percent:.1f}%)")

            print(f"   Всего запросов: {self.total_requests}")
            print(f"   Блокировок: {self.blocked_count}")
            print(f"   Затраченное время: {elapsed_time}")

            # Расчет времени на отзыв
            if self.total_requests > 0 and elapsed_time.total_seconds() > 0:
                time_per_request = elapsed_time.total_seconds() / self.total_requests
                print(f"   Среднее время на запрос: {time_per_request:.2f} сек")

            print(f"\n💾 ФАЙЛЫ:")
            print(f"   Отзывы (CSV): {self.config.OUTPUT_FILE}")
            print(f"   Отзывы (JSON): {self.config.OUTPUT_FILE.replace('.csv', '.json')}")
            print(f"   Прогресс: {self.config.PROGRESS_FILE}")
            print(f"   Логи: logs/otzovik_parser.log")

            # Сохраняем финальные результаты
            self._save_results()

            # Сохраняем статистику
            stats = {
                'successful_pages': successful_pages,
                'total_pages_attempted': end_page - start_page + 1,
                'hotels_processed': len(self.processed_hotels),
                'reviews_collected': len(self.results),
                'total_requests': self.total_requests,
                'blocked_count': self.blocked_count,
                'start_time': self.start_time.isoformat(),
                'end_time': datetime.now().isoformat(),
                'elapsed_seconds': elapsed_time.total_seconds(),
                'start_page': start_page,
                'end_page': end_page,
                'delays_config': {
                    'DELAY_MIN': self.config.DELAY_MIN,
                    'DELAY_MAX': self.config.DELAY_MAX,
                    'DELAY_BETWEEN_HOTELS_MIN': self.config.DELAY_BETWEEN_HOTELS_MIN,
                    'DELAY_BETWEEN_HOTELS_MAX': self.config.DELAY_BETWEEN_HOTELS_MAX,
                    'DELAY_BETWEEN_PAGES_MIN': self.config.DELAY_BETWEEN_PAGES_MIN,
                    'DELAY_BETWEEN_PAGES_MAX': self.config.DELAY_BETWEEN_PAGES_MAX,
                    'DELAY_AFTER_BLOCK': self.config.DELAY_AFTER_BLOCK
                }
            }

            if self.results:
                stats['average_rating'] = avg_rating
                stats['reviews_before_2020'] = before_2020_count
                stats['percent_before_2020'] = before_2020_percent

            with open('data/scraping_stats.json', 'w', encoding='utf-8') as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)

            print(f"📈 Статистика сохранена в data/scraping_stats.json")

        except KeyboardInterrupt:
            print("\n\n⏹️  СКРАПИНГ ПРЕРВАН ПОЛЬЗОВАТЕЛЕМ")
            print("💾 Сохраняю прогресс...")
            self._save_progress()
            self._save_results()
            print("✅ Прогресс сохранен. Можете продолжить позже.")

        except Exception as e:
            print(f"\n\n💥 КРИТИЧЕСКАЯ ОШИБКА: {e}")
            import traceback
            traceback.print_exc()
            print("\n💾 Сохраняю прогресс перед завершением...")
            self._save_progress()
            self._save_results()


# ===================== ИНТЕРФЕЙС КОМАНДНОЙ СТРОКИ =====================
def main():
    """Основная функция запуска"""
    print("=" * 70)
    print("ПАРСЕР OTZOVIK.COM - ОЦЕНКИ ОТЗЫВОВ И ПРИЗНАК 'ДО 2020'")
    print("=" * 70)
    print("Версия 3.2: СКОРОСТНАЯ ВЕРСИЯ - ВСЕ ЗАДЕРЖКИ 1-2 СЕКУНДЫ")
    print("=" * 70)

    # Проверка зависимостей
    try:
        import requests
        import pandas as pd
        from bs4 import BeautifulSoup
        print("✅ Все зависимости установлены")
    except ImportError as e:
        print(f"\n❌ Отсутствуют зависимости: {e}")
        print("\nУстановите зависимости:")
        print("   pip install requests pandas beautifulsoup4 lxml pyyaml")
        return

    # Загружаем конфигурацию
    config = Config()
    config.display()

    # Настройка параметров
    try:
        print("\n⚙️  НАСТРОЙКА ПАРАМЕТРОВ (СКОРОСТНАЯ ВЕРСИЯ)")
        print("-" * 40)
        print("⚡ ВСЕ ЗАДЕРЖКИ УСТАНОВЛЕНЫ В 1-2 СЕКУНДЫ:")
        print(f"   • Между запросами: 1-2 сек")
        print(f"   • Между отелями: 1-2 сек")
        print(f"   • Между страницами: 1-2 сек")
        print(f"   • После блокировки: 10 сек (было 30)")
        print(f"   • Таймаут запроса: 10 сек")
        print("-" * 40)

        # Начальная страница
        start_page = 1
        try:
            start_input = input(f"Начальная страница [1-{config.MAX_PAGES}, по умолчанию 1]: ").strip()
            if start_input:
                start_page = max(1, int(start_input))
        except ValueError:
            print("Использую значение по умолчанию: 1")

        # Конечная страница
        end_page = config.MAX_PAGES

        try:
            prompt = f"Конечная страница [{start_page}-{config.MAX_PAGES}, по умолчанию {end_page}]: "
            end_input = input(prompt).strip()
            if end_input:
                end_page = min(int(end_input), config.MAX_PAGES)
        except ValueError:
            print(f"Использую значение по умолчанию: {end_page}")

        # Проверка и корректировка диапазона
        if start_page < 1:
            start_page = 1

        if end_page > config.MAX_PAGES:
            end_page = config.MAX_PAGES

        if start_page > end_page:
            start_page, end_page = end_page, start_page
            print(f"Диапазон скорректирован: {start_page}-{end_page}")

        # Расчет примерного времени
        total_pages = end_page - start_page + 1
        # Примерное время на страницу: 10 отелей * 2 сек = 20 сек + 2 сек задержка = ~22 сек
        estimated_time_per_page = 22  # секунд
        total_seconds = total_pages * estimated_time_per_page
        total_minutes = total_seconds / 60

        print(f"\n📋 ПАРАМЕТРЫ ЗАПУСКА:")
        print(f"   Страницы: {start_page} - {end_page}")
        print(f"   Всего страниц: {total_pages}")
        print(f"   ⚡ Режим: СКОРОСТНОЙ (все задержки 1-2 сек)")
        print(f"   Примерное время: ~{total_minutes:.1f} мин ({total_seconds / 3600:.1f} часов)")
        print(f"   Собираемые данные:")
        print(f"     ✓ Оценка каждого отзыва")
        print(f"     ✓ Признак 'до 2020 года'")
        print(f"     ✓ Даты отзывов")
        print(f"\n⚠️  ВНИМАНИЕ: Высокая скорость может привести к блокировке!")
        print("   При частых блокировках увеличьте задержки в config.py")

        confirm = input("\n🚀 Запустить парсер в скоростном режиме? (y/N): ").strip().lower()

        if confirm not in ['y', 'yes', 'д', 'да']:
            print("Отменено.")
            return

        # Запуск парсера
        print("\n" + "=" * 70)
        parser = OtzyovikParser(config)
        parser.run(start_page, end_page)

    except KeyboardInterrupt:
        print("\n\n⏹️  ОТМЕНЕНО ПОЛЬЗОВАТЕЛЕМ")
    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
