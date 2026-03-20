# Changelog

## [webpanel/v1.0.0] — 2026-03-20
### Added
- **webpanel/** — клиентский кабинет (https://panel.cloaknet.site)
  - Регистрация / Вход / Telegram привязка
  - Dashboard: баланс, подписки
  - Пополнение баланса (YooMoney)
  - История платежей
  - Профиль (смена пароля)
- **bot/web_auth.py** — Auth API endpoints
- **bot/web_panel.py** — User API endpoints
- **bot/handlers/link.py** — /link команда для привязки Telegram
- **migrations/001_web_users.py** — миграция web_users + link_codes
- **panel.cloaknet.site** — nginx + SSL

### Fixed
- Graceful restart бота (SO_REUSEADDR)

## [bot/v1.0.1] — 2026-03-19
### Fixed
- SQL injection + XSS в /db endpoint (whitelist таблиц, HTML escape)
- XSS в админке (escapeHTML, 28 мест)
- Цены синхронизированы: {14:79, 30:129, 90:349, 180:619, 365:999}
- Трафик: 50GB включено, безлимит +100₽
- Устройства: +30₽/мес за каждое доп.
- tariff.py: 10gb → 50gb
- Мёртвый код формулы удалён

### Changed
- prices → фикс.цены в config.py
