# Платежный шлюз для оплаты через Сбербанк для платформы Saleor

# Важно
Плагин для релиза Saleor 2.9

# Установка 
* Склонировать файлы репозитория к себе
* Разместить в каталог с проектом (в корне проекта есть папка `/saleor/`)

# Настройка
* Добавить путь к плагину в `setting.py`:
```python
PLUGINS = [
     #...
     "saleor.payment.gateways.sberbank.plugin.SberbankGatewayPlugin",
 ]
```
* В Дашборде сделать настройки платежного шлюза (ввести данные от API)

# Принцип работы
* Клиент выбирает способ оплаты "Сбербанк"
* Генерируется форма с кнопкой "Сделать платеж"
* При нажатии на кнопку происходит редирект на сайт Сбербанка для оплаты заказа
* В случае успешной оплаты, Сбербанк возвращает на страницу с информацией об успешном заказе
* С помощью `Celery` происходит обновление статуса заказа

# Что можно улучшить
* Добавить обработку ошибок, в случае не успешной оплаты
* Провести рефакторинг
* ...