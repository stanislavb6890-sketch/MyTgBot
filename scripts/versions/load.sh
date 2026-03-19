#!/bin/bash
# Загрузить конкретную версию webapp/index.html
# Usage: ./load-version.sh v1.0.0
# Example: ./load-version.sh golden

set -e

cd /root/.openclaw/workspace/vpn-bot

if [ -z "$1" ]; then
    echo "❌ Укажи версию"
    echo ""
    echo "Доступные версии:"
    git tag -l | while read t; do
        echo "  - $t"
    done
    echo ""
    echo "Пример: $0 golden"
    exit 1
fi

VERSION=$1

echo "🔄 Загружаю версию: $VERSION"

# Проверяем что тег/коммит существует
if ! git rev-parse "$VERSION" >/dev/null 2>&1; then
    echo "❌ Версия '$VERSION' не найдена"
    exit 1
fi

# Показываем что было изменено
echo ""
echo "📊 Изменения относительно текущей:"
git diff HEAD -- webapp/index.html | tail -20 || true

# Берём файл из указанной версии
git checkout "$VERSION" -- webapp/index.html

echo ""
echo "✅ webapp/index.html обновлён до версии $VERSION"

# Показываем что изменилось
echo ""
echo "📊 Новые изменения:"
git diff HEAD -- webapp/index.html | head -30 || echo "  (нет изменений)"

echo ""
echo "⚠️  Не забудь перезапустить бота: перезапусти процесс"
