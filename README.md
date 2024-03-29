# Плагин оплаты через Сбербанк API для Saleor

[![Join telegram chat](https://img.shields.io/badge/chat-telegram-blue?style=flat&logo=telegram)](https://t.me/django_ecommerce) 

# Важно
* Плагин для релиза Saleor 2.9 - [смотри ветку 2.9](https://github.com/korolevpavel/saleor-gateaway-sberbank/tree/2.9)
* Плагин для релиза Saleor 2.11 - [смотри ветку 2.11](https://github.com/korolevpavel/saleor-gateaway-sberbank/tree/2.11)

# Установка 
* Склонировать файлы репозитория к себе
* Разместить в каталог с проектом (в корне проекта есть папка `/saleor/`)
* Фронтенд разместить в каталог с проектом (в корне проекта есть папка `/storefront/`)

# Настройка
* Добавить путь к плагину в `setting.py`:
```python
PLUGINS = [
     #...
     "saleor.payment.gateways.sberbank.plugin.SberbankGatewayPlugin",
 ]
```
* В Дашборде сделать настройки платежного шлюза (ввести данные от API)

# Как работает
* Клиент выбирает способ оплаты "Сбербанк"
* Происходит редирект на сайт Сбербанка для оплаты заказа
* В случае успешной оплаты, Сбербанк возвращает на страницу с информацией об успешном заказе

# Что можно улучшить
* Добавить обработку ошибок, в случае не успешной оплаты
* Провести рефакторинг
* ...
