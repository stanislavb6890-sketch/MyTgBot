"""
Web Panel — User API Endpoints
"""
import sqlite3
from datetime import datetime
from aiohttp import web


def get_db():
    return sqlite3.connect('/root/.openclaw/workspace/vpn-bot/vpn_bot.db')


def get_current_user(token_data: dict):
    """Get full user data from token"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, telegram_id, email, created_at FROM web_users WHERE id = ?',
              (token_data['user_id'],))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        'id': row[0],
        'telegram_id': row[1],
        'email': row[2],
        'created_at': row[3]
    }


def get_vpn_user(telegram_id: int):
    """Get VPN user by telegram_id"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, balance FROM users WHERE telegram_id = ?', (telegram_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {'id': row[0], 'balance': row[1]}


def get_user_subs(telegram_id: int):
    """Get all subscriptions for a user by telegram_id"""
    conn = get_db()
    c = conn.cursor()
    # First get internal user_id
    c.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return []
    user_id = row[0]
    
    c.execute("""
        SELECT s.id, s.status, s.duration_days, s.traffic_limit_bytes, s.traffic_used_bytes,
               s.devices_limit, s.servers_count, s.is_trial, s.is_paid, s.created_at,
               s.expires_at, s.price, s.username, GROUP_CONCAT(ss.node_name, ', ') as servers
        FROM subscriptions s
        LEFT JOIN subscription_servers ss ON s.id = ss.subscription_id
        WHERE s.user_id = ?
        GROUP BY s.id
        ORDER BY s.created_at DESC
    """, (user_id,))
    
    subs = []
    for row in c.fetchall():
        traffic_limit_gb = row[3] / (1024**3) if row[3] else 0
        traffic_used_gb = row[4] / (1024**3) if row[4] else 0
        expires = datetime.fromisoformat(row[10]) if row[10] else None
        is_active = expires and expires > datetime.now() and row[1] == 'active'
        
        subs.append({
            'id': row[0],
            'status': 'active' if is_active else ('expired' if expires and expires < datetime.now() else row[1]),
            'duration_days': row[2],
            'traffic_gb': round(traffic_limit_gb, 1),
            'traffic_used_gb': round(traffic_used_gb, 1),
            'traffic_unlimited': row[3] == 0,
            'devices': row[5],
            'servers': row[6],
            'servers_list': row[13].split(', ') if row[13] else [],
            'is_trial': bool(row[7]),
            'is_paid': bool(row[8]),
            'created_at': row[9],
            'expires_at': row[10],
            'price': row[11] or 0,
            'username': row[12],
        })
    
    conn.close()
    return subs


def get_user_payments(telegram_id: int):
    """Get all payments for a user"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM users WHERE telegram_id = ?', (telegram_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return []
    user_id = row[0]
    
    c.execute("""
        SELECT p.id, p.amount, p.status, p.created_at, p.paid_at, p.subscription_id,
               s.duration_days, s.price as sub_price
        FROM payments p
        LEFT JOIN subscriptions s ON p.subscription_id = s.id
        WHERE p.user_id = ?
        ORDER BY p.created_at DESC
        LIMIT 50
    """, (user_id,))
    
    payments = []
    for row in c.fetchall():
        payments.append({
            'id': row[0],
            'amount': row[1],
            'status': row[2],
            'created_at': row[3],
            'paid_at': row[4],
            'subscription_id': row[5],
            'duration_days': row[6] or 0,
        })
    
    conn.close()
    return payments


# ──────────────────────────────────────────────
# GET /api/web/user — профиль + баланс
# ──────────────────────────────────────────────
async def get_user(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    from bot.web_auth import verify_token
    token_data = verify_token(auth[7:])
    if not token_data:
        return web.json_response({'error': 'invalid token'}, status=401)
    
    user = get_current_user(token_data)
    if not user:
        return web.json_response({'error': 'user not found'}, status=404)
    
    vpn_user = get_vpn_user(user['telegram_id']) if user['telegram_id'] else None
    subs = get_user_subs(user['telegram_id']) if user['telegram_id'] else []
    
    active_subs = [s for s in subs if s['status'] == 'active']
    
    return web.json_response({
        'user': {
            'id': user['id'],
            'email': user['email'],
            'telegram_id': user['telegram_id'],
            'telegram_linked': user['telegram_id'] is not None,
            'created_at': user['created_at'],
        },
        'balance': vpn_user['balance'] if vpn_user else 0,
        'subscriptions_count': len(subs),
        'active_subscriptions': len(active_subs),
        'has_vpn_account': vpn_user is not None,
    })


# ──────────────────────────────────────────────
# GET /api/web/subscriptions — список подписок
# ──────────────────────────────────────────────
async def get_subscriptions(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    from bot.web_auth import verify_token
    token_data = verify_token(auth[7:])
    if not token_data:
        return web.json_response({'error': 'invalid token'}, status=401)
    
    user = get_current_user(token_data)
    if not user:
        return web.json_response({'error': 'user not found'}, status=404)
    
    if not user['telegram_id']:
        return web.json_response({'subscriptions': [], 'message': 'Telegram not linked'})
    
    subs = get_user_subs(user['telegram_id'])
    return web.json_response({'subscriptions': subs})


# ──────────────────────────────────────────────
# GET /api/web/payments — история платежей
# ──────────────────────────────────────────────
async def get_payments(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    from bot.web_auth import verify_token
    token_data = verify_token(auth[7:])
    if not token_data:
        return web.json_response({'error': 'invalid token'}, status=401)
    
    user = get_current_user(token_data)
    if not user:
        return web.json_response({'error': 'user not found'}, status=404)
    
    if not user['telegram_id']:
        return web.json_response({'payments': []})
    
    payments = get_user_payments(user['telegram_id'])
    return web.json_response({'payments': payments})


# ──────────────────────────────────────────────
# POST /api/web/topup — создать ссылку на пополнение
# ──────────────────────────────────────────────
async def topup(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    from bot.web_auth import verify_token
    token_data = verify_token(auth[7:])
    if not token_data:
        return web.json_response({'error': 'invalid token'}, status=401)
    
    user = get_current_user(token_data)
    if not user:
        return web.json_response({'error': 'user not found'}, status=404)
    
    if not user['telegram_id']:
        return web.json_response({'error': 'Telegram not linked. Link first.'}, status=400)
    
    try:
        data = await request.json()
    except:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    
    amount = float(data.get('amount', 0))
    if amount < 10 or amount > 50000:
        return web.json_response({'error': 'Amount must be between 10 and 50000'}, status=400)
    
    import hashlib
    import uuid
    from config import YOOMONEY_WALLET, YOOMONEY_SECRET
    
    order_id = str(uuid.uuid4())[:12]
    label = f"topup_{user['telegram_id']}_{order_id}"
    
    # YooMoney form URL
    pay_url = (
        f"https://yoomoney.ru/quickpay/confirm.xml?"
        f"receiver={YOOMONEY_WALLET}"
        f"&sum={amount}"
        f"&label={label}"
        f"&quickpay-form=shop"
        f"&targets={label}"
    )
    
    # Also save pending topup in DB
    conn = get_db()
    c = conn.cursor()
    # Store in a simple topups table
    c.execute('''CREATE TABLE IF NOT EXISTS topups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        order_id TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    c.execute('INSERT INTO topups (telegram_id, amount, order_id) VALUES (?, ?, ?)',
              (user['telegram_id'], amount, order_id))
    conn.commit()
    conn.close()
    
    return web.json_response({
        'topup_url': pay_url,
        'amount': amount,
        'order_id': order_id,
    })


# ──────────────────────────────────────────────
# POST /api/web/subscriptions/:id/renew — продлить подписку
# ──────────────────────────────────────────────
async def renew_subscription(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    from bot.web_auth import verify_token
    token_data = verify_token(auth[7:])
    if not token_data:
        return web.json_response({'error': 'invalid token'}, status=401)
    
    user = get_current_user(token_data)
    if not user or not user['telegram_id']:
        return web.json_response({'error': 'Telegram not linked'}, status=400)
    
    # Forward to existing bot API
    import urllib.request
    sub_id = request.query.get('sub_id') or request.match_info.get('sub_id')
    days = request.query.get('days', '30')
    
    # Get renewal options
    vpn_user = get_vpn_user(user['telegram_id'])
    if not vpn_user:
        return web.json_response({'error': 'VPN account not found'}, status=404)
    
    # Forward to internal API
    from bot.utils.database import get_db as _get_db
    conn = _get_db()
    c = conn.cursor()
    c.execute('''SELECT s.id, s.status, s.expires_at, s.traffic_limit_bytes,
                 s.devices_limit, s.servers_count, s.reset_type
                 FROM subscriptions s WHERE s.user_id = ? AND s.id = ?''',
              (vpn_user['id'], int(sub_id)))
    sub = c.fetchone()
    conn.close()
    
    if not sub:
        return web.json_response({'error': 'Subscription not found'}, status=404)
    
    # Return renewal options
    prices = {14: 79, 30: 129, 90: 349, 180: 619, 365: 999}
    options = [{'days': d, 'name': {14:'14 дней',30:'1 месяц',90:'3 месяца',180:'6 месяцев',365:'1 год'}[d],
               'price': prices[d]} for d in [14, 30, 90, 180, 365]]
    
    return web.json_response({
        'options': options,
        'current': {
            'id': sub[0],
            'status': sub[1],
            'expires_at': sub[2],
            'traffic_gb': sub[3]/(1024**3) if sub[3] else 50,
            'devices': sub[4],
            'servers': sub[5],
        }
    })


# ──────────────────────────────────────────────
# GET /api/web/config/:sub_id — получить конфиг
# ──────────────────────────────────────────────
async def get_config(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    from bot.web_auth import verify_token
    token_data = verify_token(auth[7:])
    if not token_data:
        return web.json_response({'error': 'invalid token'}, status=401)
    
    user = get_current_user(token_data)
    if not user or not user['telegram_id']:
        return web.json_response({'error': 'Telegram not linked'}, status=400)
    
    sub_id = request.match_info.get('sub_id')
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id FROM users WHERE telegram_id = ?', (user['telegram_id'],))
    row = c.fetchone()
    if not row:
        conn.close()
        return web.json_response({'error': 'VPN account not found'}, status=404)
    
    c.execute('''SELECT s.id, s.username, s.short_uuid, s.status, s.expires_at,
                 GROUP_CONCAT(ss.node_name, ', ') as servers
                 FROM subscriptions s
                 LEFT JOIN subscription_servers ss ON s.id = ss.subscription_id
                 WHERE s.user_id = ? AND s.id = ?
                 GROUP BY s.id''',
              (row[0], sub_id))
    sub = c.fetchone()
    conn.close()
    
    if not sub:
        return web.json_response({'error': 'Subscription not found'}, status=404)
    
    # Check expiry
    expires = datetime.fromisoformat(sub[4]) if sub[4] else None
    if not expires or expires < datetime.now():
        return web.json_response({'error': 'Subscription expired'}, status=400)
    
    return web.json_response({
        'username': sub[1],
        'uuid': sub[2],
        'servers': sub[5].split(', ') if sub[5] else [],
        'status': sub[3],
        'expires_at': sub[4],
    })


# ──────────────────────────────────────────────
# POST /api/web/profile/password — сменить пароль
# ──────────────────────────────────────────────
async def change_password(request):
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    from bot.web_auth import verify_token
    token_data = verify_token(auth[7:])
    if not token_data:
        return web.json_response({'error': 'invalid token'}, status=401)
    
    try:
        data = await request.json()
    except:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    
    current = data.get('current_password', '')
    new_pass = data.get('new_password', '')
    
    if len(new_pass) < 6:
        return web.json_response({'error': 'New password must be at least 6 chars'}, status=400)
    
    from bot.web_auth import verify_password, hash_password
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT password_hash FROM web_users WHERE id = ?', (token_data['user_id'],))
    row = c.fetchone()
    if not row or not verify_password(current, row[0]):
        conn.close()
        return web.json_response({'error': 'Current password incorrect'}, status=400)
    
    new_hash = hash_password(new_pass)
    c.execute('UPDATE web_users SET password_hash = ? WHERE id = ?',
              (new_hash, token_data['user_id']))
    conn.commit()
    conn.close()
    
    return web.json_response({'success': True})


def setup_web_panel_routes(app):
    """Register web panel user routes"""
    app.router.add_get('/api/web/user', get_user)
    app.router.add_get('/api/web/subscriptions', get_subscriptions)
    app.router.add_get('/api/web/payments', get_payments)
    app.router.add_post('/api/web/topup', topup)
    app.router.add_post('/api/web/subscriptions/{sub_id}/renew', renew_subscription)
    app.router.add_get('/api/web/config/{sub_id}', get_config)
    app.router.add_post('/api/web/profile/password', change_password)
