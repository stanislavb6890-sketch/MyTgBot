# CloakNet VPN Bot

Telegram бот для продажи VPN-подписок с интеграцией RemnaWave.

## Функционал

- Создание подписок (период, трафик, устройства, серверы)
- Оплата через ЮMoney
- Тестовый период
- Уведомления об истечении подписки
- Админ-панель
- Mini App для пользователей

## Установка

```bash
# Клонирование
git clone https://github.com/stanislavb6890-sketch/MyTgBot.git
cd MyTgBot

# Виртуальное окружение
python3 -m venv venv
source venv/bin/activate

# Зависимости
pip install -r requirements.txt

# Настройка .env
cp .env.example .env
# Отредактируй .env с своими данными

# Запуск
python bot/main.py
```

## .env пример

```
BOT_TOKEN=your_bot_token
YOOMONEY_WALLET=your_wallet
YOOMONEY_TOKEN=your_token
REMNAWAVE_URL=https://your-panel.com
REMNAWAVE_TOKEN=your_token
ADMIN_ID=your_telegram_id
WEBHOOK_URL=https://your-domain.com/webhook/yoomoney
```

## Mini App

Для работы Mini App нужен HTTPS домен. Настрой nginx с прокси на порт 8080.

## Команды

- `/start` - Старт
- `/admin` - Админ-панель
- `/stats` - Статистика
- `/users` - Пользователи
- `/payments` - Платежи
- `/subs` - Подписки

## Crontab для уведомлений

```bash
0 */3 * * * /path/to/venv/bin/python /path/to/send_notifications.py
```

---

# Инструкция для Джарвиса (будущего)

## Запуск бота

```bash
cd /root/.openclaw/workspace/vpn-bot
source venv/bin/activate
python bot/main.py
```

## Перезапуск

```bash
pkill -f "python3 bot/main.py"
cd /root/.openclaw/workspace/vpn-bot
source venv/bin/activate
python bot/main.py > bot.log 2>&1 &
```

## Логи

```bash
tail -f /root/.openclaw/workspace/vpn-bot/bot.log
```

## Git

```bash
cd /root/.openclaw/workspace/vpn-bot

# Коммит
git add -A
git commit -m "описание изменений"

# Пуш (нужен токен)
git remote set-url origin https://ghp_TOKEN@github.com/stanislavb6890-sketch/MyTgBot.git
git push origin master
```

## Nginx

Конфиг: `/etc/nginx/sites-available/cloaknet`

```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Тестовые данные

- Telegram ID: 2056591682
- Сервер: test.cloaknet.site
- Mini App: https://test.cloaknet.site/miniapp
