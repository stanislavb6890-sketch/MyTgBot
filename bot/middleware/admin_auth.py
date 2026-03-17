"""Middleware для защиты админ-панели"""
from aiohttp import web
import logging
from config import ADMIN_ID

logger = logging.getLogger(__name__)

# Секретный токен для доступа к админ-панели
ADMIN_TOKEN = "81c6402728833f1237d157a78b229285"


@web.middleware
async def admin_auth_middleware(request, handler):
    """Middleware для защиты админ-панели"""
    
    # Публичные маршруты — пропускаем без проверки
    public_paths = [
        '/miniapp',
        '/app',
        '/webhook/yoomoney',
        '/admin/login',
        '/admin/index.html',
        '/admin/login.html',
    ]
    
    # Проверяем: если не /admin — пропускаем
    if not request.path.startswith('/admin'):
        return await handler(request)
    
    # Публичные страницы — пропускаем
    if request.path in public_paths or request.path.endswith('.html'):
        return await handler(request)
    
    # Логируем попытку
    logger.info(f"📋 Admin access: {request.method} {request.path} | IP: {request.remote}")
    
    # Проверка 1: Токен в URL
    token = request.query.get('token')
    if token == ADMIN_TOKEN:
        logger.info(f"✅ Admin access granted (token): {request.remote}")
        return await handler(request)
    
    # Проверка 2: Telegram ID
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    if telegram_id:
        try:
            if int(telegram_id) == ADMIN_ID:
                logger.info(f"✅ Admin access granted (Telegram ID): {telegram_id}")
                return await handler(request)
        except (ValueError, TypeError):
            pass
    
    # Проверка 3: Заголовок X-Admin-Token
    header_token = request.headers.get('X-Admin-Token')
    if header_token == ADMIN_TOKEN:
        logger.info(f"✅ Admin access granted (header): {request.remote}")
        return await handler(request)
    
    # Отклоняем
    logger.warning(f"❌ Admin access denied: {request.remote} | path: {request.path}")
    return web.json_response({'error': 'Access denied'}, status=403)
