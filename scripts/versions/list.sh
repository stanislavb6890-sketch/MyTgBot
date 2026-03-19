#!/bin/bash
# Показать все доступные версии

cd /root/.openclaw/workspace/vpn-bot

echo "📋 Версии webapp/index.html"
echo ""
git tag -l --format='  %(refname:short)  %(subject)  %(creatordate)' | sort -V
echo ""
echo "HEAD: $(git rev-parse --short HEAD)"
