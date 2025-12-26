#!/usr/bin/env python3
"""
Конфигурация парсера из YAML-файла или значений по умолчанию
"""

import os
from typing import Dict, Any, List


class Config:
    """Конфигурация парсера"""

    def __init__(self, config_path='config.yml'):
        # Устанавливаем значения по умолчанию
        self._set_defaults()

        # Пытаемся загрузить из YAML если файл существует
        if os.path.exists(config_path):
            self._try_load_yaml(config_path)
        else:
            print(f"⚠️  Конфигурационный файл {config_path} не найден, использую значения по умолчанию")

    def _set_defaults(self):
        """Установка значений по умолчания"""
        # Основные настройки
        self.BASE_URL = 'https://otzovik.com/travel/hotels/'
        self.MAX_PAGES = 1462
        self.OUTPUT_FILE = 'otzovik_reviews.csv'
        self.PROGRESS_FILE = 'progress.json'

        # Задержки для обхода блокировок
        self.DELAY_MIN = 8
        self.DELAY_MAX = 15
        self.DELAY_BETWEEN_PAGES_MIN = 5
        self.DELAY_BETWEEN_PAGES_MAX = 10
        self.DELAY_BETWEEN_HOTELS_MIN = 3
        self.DELAY_BETWEEN_HOTELS_MAX = 7
        self.DELAY_AFTER_BLOCK = 60
        self.MAX_RETRIES = 3
        self.TIMEOUT = 30

        # Ограничения
        self.MAX_HOTELS_PER_PAGE = 20
        self.MAX_REVIEWS_PER_HOTEL = 50

        # User-Agents
        self.USER_AGENTS = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:121.0) Gecko/20100101 Firefox/121.0",
        ]

        # Селекторы
        self.SELECTORS_LIST = {
            'hotel_container': 'div.product-list div.item',
            'hotel_link': 'a.product-name',
            'reviews_count': 'a.reviews-counter',
            'rating': 'div.rating-score-2 span:nth-of-type(2)',
        }

        self.SELECTORS_HOTEL = {
            'review_item': 'div.review-list-2 div.item',
            'review_rating': 'div.rating-score span',  # Рейтинг отзыва (текст)
            'review_rating_score': 'div.rating-score span',  # Рейтинг отзыва (число)
            'review_date': 'div.review-postdate',
            'review_date_meta': 'meta[itemprop="datePublished"]',
            'review_title': 'h3.review-title a',
            'review_teaser': 'div.review-teaser',
            'review_plus': 'div.review-plus',
            'review_minus': 'div.review-minus',
            'review_author': 'div.user-info a.user-login span',
            'review_author_location': 'div.user-info div:nth-of-type(3)',
            'review_recommendations': 'a.review-yes span',
            'review_comments': 'a.review-comments span',
            'review_images': 'div.review-thumbs img',
        }

    def _try_load_yaml(self, config_path: str):
        """Пытаемся загрузить конфигурацию из YAML файла"""
        try:
            # Пробуем импортировать yaml
            import yaml

            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)

            if not config_data:
                print(f"⚠️  Конфигурационный файл {config_path} пуст")
                return

            # Основные настройки
            if 'scraper' in config_data:
                scraper = config_data['scraper']
                self.BASE_URL = scraper.get('base_url', self.BASE_URL)
                self.MAX_PAGES = scraper.get('max_pages', self.MAX_PAGES)
                self.OUTPUT_FILE = scraper.get('output_file', self.OUTPUT_FILE)
                self.PROGRESS_FILE = scraper.get('progress_file', self.PROGRESS_FILE)

            # Задержки
            if 'delays' in config_data:
                delays = config_data['delays']
                self.DELAY_MIN = delays.get('min', self.DELAY_MIN)
                self.DELAY_MAX = delays.get('max', self.DELAY_MAX)
                self.DELAY_AFTER_BLOCK = delays.get('after_block', self.DELAY_AFTER_BLOCK)

                if 'between_pages' in delays:
                    between_pages = delays['between_pages']
                    self.DELAY_BETWEEN_PAGES_MIN = between_pages.get('min', self.DELAY_BETWEEN_PAGES_MIN)
                    self.DELAY_BETWEEN_PAGES_MAX = between_pages.get('max', self.DELAY_BETWEEN_PAGES_MAX)

                if 'between_hotels' in delays:
                    between_hotels = delays['between_hotels']
                    self.DELAY_BETWEEN_HOTELS_MIN = between_hotels.get('min', self.DELAY_BETWEEN_HOTELS_MIN)
                    self.DELAY_BETWEEN_HOTELS_MAX = between_hotels.get('max', self.DELAY_BETWEEN_HOTELS_MAX)

            # Ограничения
            if 'limits' in config_data:
                limits = config_data['limits']
                self.MAX_RETRIES = limits.get('max_retries', self.MAX_RETRIES)
                self.TIMEOUT = limits.get('timeout', self.TIMEOUT)
                self.MAX_HOTELS_PER_PAGE = limits.get('max_hotels_per_page', self.MAX_HOTELS_PER_PAGE)
                self.MAX_REVIEWS_PER_HOTEL = limits.get('max_reviews_per_hotel', self.MAX_REVIEWS_PER_HOTEL)

            # User-Agents
            if 'user_agents' in config_data:
                self.USER_AGENTS = config_data['user_agents']

            # Селекторы
            if 'selectors' in config_data:
                selectors = config_data['selectors']

                if 'list_page' in selectors:
                    self.SELECTORS_LIST.update(selectors['list_page'])

                if 'hotel_page' in selectors:
                    self.SELECTORS_HOTEL.update(selectors['hotel_page'])

            print(f"✅ Конфигурация загружена из {config_path}")

        except ImportError:
            print(f"⚠️  Модуль PyYAML не установлен, использую значения по умолчанию")
        except Exception as e:
            print(f"⚠️  Ошибка загрузки конфигурации из YAML: {e}")

    def display(self):
        """Отображение текущей конфигурации"""
        print("\n📋 ТЕКУЩАЯ КОНФИГУРАЦИЯ:")
        print("-" * 50)
        print(f"BASE_URL: {self.BASE_URL}")
        print(f"MAX_PAGES: {self.MAX_PAGES}")
        print(f"OUTPUT_FILE: {self.OUTPUT_FILE}")
        print(f"PROGRESS_FILE: {self.PROGRESS_FILE}")
        print(f"TIMEOUT: {self.TIMEOUT}")
        print(f"MAX_RETRIES: {self.MAX_RETRIES}")
        print(f"DELAY_MIN/MAX: {self.DELAY_MIN}/{self.DELAY_MAX}")
        print("-" * 50)


if __name__ == "__main__":
    config = Config()
    config.display()