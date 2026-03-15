"""API для Web App"""
import json
import logging
from aiohttp import web
from bot.utils.database import get_db, get_user_subscriptions, get_user_by_telegram

logger = logging.getLogger(__name__)


async def get_user_data(request):
    """Получить данные пользователя"""
    # Получаем telegram_id из URL параметра или заголовка
    telegram_id = request.query.get('telegram_id')
    
    if not telegram_id:
        return web.json_response({'error': 'telegram_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return web.json_response({'error': 'invalid telegram_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем пользователя
    cursor.execute("SELECT id, telegram_id, username, first_name, has_trial, purchase_count FROM users WHERE telegram_id = ?", (telegram_id,))
    user_row = cursor.fetchone()
    
    if not user_row:
        conn.close()
        return web.json_response({
            'user': None,
            'subscriptions': []
        })
    
    user = {
        'id': user_row[0],
        'telegram_id': user_row[1],
        'username': user_row[2],
        'first_name': user_row[3],
        'has_trial': bool(user_row[4]),
        'purchase_count': user_row[5]
    }
    
    # Получаем подписки
    cursor.execute("""
        SELECT s.id, s.status, s.expires_at, s.traffic_limit_bytes, s.traffic_used_bytes,
               s.devices_limit, s.servers_count, s.is_trial, s.is_paid, s.short_uuid,
               GROUP_CONCAT(ss.node_name, ', ') as servers
        FROM subscriptions s
        LEFT JOIN subscription_servers ss ON s.id = ss.subscription_id
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """, (user['id'],))
    
    subs_rows = cursor.fetchall()
    conn.close()
    
    subscriptions = []
    for row in subs_rows:
        traffic_limit_gb = row[3] / (1024**3) if row[3] else 0
        traffic_used_gb = row[4] / (1024**3) if row[4] else 0
        
        subscriptions.append({
            'id': row[0],
            'status': row[1],
            'expires_at': row[2],
            'traffic_limit': traffic_limit_gb,
            'traffic_used': traffic_used_gb,
            'devices': row[5],
            'servers': row[6],
            'is_trial': bool(row[7]),
            'is_paid': bool(row[8]),
            'short_uuid': row[9],
            'servers_list': row[10] or ''
        })
    
    return web.json_response({
        'user': user,
        'subscriptions': subscriptions
    })


async def get_subscription_links(request):
    """Получить ссылку подписки (для активных)"""
    sub_id = request.query.get('sub_id')
    
    if not sub_id:
        return web.json_response({'error': 'sub_id required'}, status=400)
    
    try:
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid sub_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.short_uuid, s.status, s.is_paid, u.telegram_id
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        WHERE s.id = ?
    """, (sub_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    short_uuid, status, is_paid, telegram_id = row
    
    if status != 'active' or not is_paid:
        return web.json_response({'error': 'subscription not active'}, status=400)
    
    sub_url = f"https://sys.goodred.pro/{short_uuid}"
    
    return web.json_response({
        'sub_id': sub_id,
        'subscription_url': sub_url,
        'status': status
    })


async def get_payment_url(request):
    """Получить ссылку на оплату"""
    sub_id = request.query.get('sub_id')
    
    if not sub_id:
        return web.json_response({'error': 'sub_id required'}, status=400)
    
    try:
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid sub_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.short_uuid, s.status, s.is_paid, s.price, u.telegram_id
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        WHERE s.id = ?
    """, (sub_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    short_uuid, status, is_paid, price, telegram_id = row
    
    if is_paid:
        return web.json_response({'error': 'subscription already paid'}, status=400)
    
    # Генерируем ссылку на оплату (нужный кошелёк)
    from config import YOOMONEY_WALLET
    payment_url = f"https://yoomoney.ru/quickpay/confirm?receiver={YOOMONEY_WALLET}&quickpay-form=button&paymentType=AC&sum={price}&label={sub_id}"
    
    return web.json_response({
        'sub_id': sub_id,
        'payment_url': payment_url,
        'price': price
    })


async def delete_subscription(request):
    """Удалить подписку"""
    # Пробуем получить из POST или GET
    post_data = await request.post()
    sub_id = post_data.get('sub_id') or request.query.get('sub_id')
    
    if not sub_id:
        return web.json_response({'error': 'sub_id required'}, status=400)
    
    try:
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid sub_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем UUID подписки
    cursor.execute("SELECT remnawave_uuid FROM subscriptions WHERE id = ?", (sub_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    uuid = row[0]
    
    # Удаляем из БД
    cursor.execute('DELETE FROM subscriptions WHERE id = ?', (sub_id,))
    cursor.execute('DELETE FROM subscription_servers WHERE subscription_id = ?', (sub_id,))
    conn.commit()
    conn.close()
    
    # Пробуем удалить из панели (асинхронно)
    try:
        from bot.utils.remnawave import delete_vpn_user
        delete_vpn_user(uuid)
    except:
        pass
    
    return web.json_response({'success': True, 'sub_id': sub_id})


async def get_renewal_options(request):
    """Получить варианты продления"""
    sub_id = request.query.get('sub_id')
    if not sub_id:
        return web.json_response({'error': 'sub_id required'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.duration_days, s.traffic_limit_bytes, s.devices_limit
        FROM subscriptions s
        WHERE s.id = ?
    """, (sub_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    duration_days, traffic_limit, devices = row
    
    # Базовая цена за день
    price_per_day = 5
    
    # Варианты продления
    options = [
        {'days': 30, 'name': '1 месяц', 'price': int(duration_days * price_per_day)},
        {'days': 90, 'name': '3 месяца', 'price': int(duration_days * price_per_day * 2.8)},
        {'days': 180, 'name': '6 месяцев', 'price': int(duration_days * price_per_day * 5)},
        {'days': 365, 'name': '1 год', 'price': int(duration_days * price_per_day * 9)},
    ]
    
    return web.json_response({
        'sub_id': int(sub_id),
        'options': options
    })


async def get_user_payments(request):
    """Получить историю платежей пользователя"""
    telegram_id = request.query.get('telegram_id')
    
    if not telegram_id:
        return web.json_response({'error': 'telegram_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return web.json_response({'error': 'invalid telegram_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.id, p.amount, p.status, p.created_at
        FROM payments p
        JOIN users u ON p.user_id = u.id
        WHERE u.telegram_id = ?
        ORDER BY p.created_at DESC
        LIMIT 20
    """, (telegram_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    payments = []
    for row in rows:
        payments.append({
            'id': row[0],
            'amount': row[1],
            'status': row[2],
            'created_at': row[3]
        })
    
    return web.json_response({'payments': payments})


def setup_api_routes(app):
    """Настроить API маршруты"""
    app.router.add_get('/api/user', get_user_data)
    app.router.add_get('/api/subscription/links', get_subscription_links)
    app.router.add_get('/api/subscription/payment', get_payment_url)
    app.router.add_post('/api/subscription/delete', delete_subscription)
    app.router.add_get('/api/subscription/renewal', get_renewal_options)
    app.router.add_get('/api/payments', get_user_payments)
    logger.info("✅ API routes настроены")
