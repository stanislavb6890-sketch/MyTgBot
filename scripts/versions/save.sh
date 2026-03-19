#!/bin/bash
# Сохранить текущее состояние webapp как новую версию
# Usage: ./save-version.sh [version] [message]
# Example: ./save-version.sh 1.1.0 "Исправлен баг с SDK"

set -e

cd /root/.openclaw/workspace/vpn-bot

VERSION=${1:-$(date +%Y%m%d-%H%M%S)}
MESSAGE=${2:-"Backup $(date '+%Y-%m-%d %H:%M')"}

echo "📦 Сохраняю версию: $VERSION"
echo "   $MESSAGE"

# Коммитим текущее состояние
git add -A
git commit -m "$MESSAGE" || echo "Нечего коммитить или уже закоммичено"

# Создаём tag
git tag -a "v$VERSION" -m "Версия $VERSION: $MESSAGE"

# Пушим
git push origin master --tags

echo "✅ Версия $VERSION сохранена и запушена"
echo ""
echo "Tags:"
git tag -l --format='  %(refname:short) - %(subject)'
