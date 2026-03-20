"""
Web Panel — Auth API Endpoints
"""

import hashlib
import secrets
import time
from datetime import datetime, timedelta
from aiohttp import web
from config import YOOMONEY_SECRET

# In-memory token store: token -> {user_id, email, expires_at}
# For production, use Redis or DB
tokens = {}

def hash_password(password: str, salt: str = '') -> str:
    """Hash password with SHA-256 + salt"""
    if not salt:
        salt = secrets.token_hex(16)
    return f"{salt}${hashlib.sha256((salt + password).encode()).hexdigest()}"

def verify_password(password: str, stored: str) -> bool:
    """Verify password against stored hash"""
    if '$' not in stored:
        return False
    salt, _ = stored.split('$', 1)
    return hash_password(password, salt) == stored

def generate_token(user_id: int, email: str) -> str:
    """Generate JWT-like token (simple version)"""
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + 30 * 24 * 3600  # 30 days
    tokens[token] = {'user_id': user_id, 'email': email, 'expires_at': expires_at}
    return token

def verify_token(token: str) -> dict | None:
    """Verify token and return user data"""
    data = tokens.get(token)
    if not data:
        return None
    if time.time() > data['expires_at']:
        del tokens[token]
        return None
    return data

def get_db():
    import sqlite3
    return sqlite3.connect('/root/.openclaw/workspace/vpn-bot/vpn_bot.db')


# ──────────────────────────────────────────────
# POST /api/web/auth/register
# Body: {"email": "...", "password": "..."}
# ──────────────────────────────────────────────
async def register(request):
    try:
        data = await request.json()
    except:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or '@' not in email:
        return web.json_response({'error': 'Invalid email'}, status=400)
    if len(password) < 6:
        return web.json_response({'error': 'Password must be at least 6 characters'}, status=400)
    
    password_hash = hash_password(password)
    
    conn = get_db()
    c = conn.cursor()
    
    # Check if email exists
    c.execute('SELECT id FROM web_users WHERE email = ?', (email,))
    if c.fetchone():
        conn.close()
        return web.json_response({'error': 'Email already registered'}, status=409)
    
    try:
        c.execute('INSERT INTO web_users (email, password_hash) VALUES (?, ?)',
                  (email, password_hash))
        conn.commit()
        user_id = c.lastrowid
        conn.close()
        
        token = generate_token(user_id, email)
        return web.json_response({
            'success': True,
            'token': token,
            'user': {'id': user_id, 'email': email}
        })
    except Exception as e:
        conn.close()
        return web.json_response({'error': str(e)}, status=500)


# ──────────────────────────────────────────────
# POST /api/web/auth/login
# Body: {"email": "...", "password": "..."}
# ──────────────────────────────────────────────
async def login(request):
    try:
        data = await request.json()
    except:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, email, password_hash, telegram_id FROM web_users WHERE email = ?',
              (email,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return web.json_response({'error': 'Invalid email or password'}, status=401)
    
    user_id, email, password_hash, telegram_id = row
    
    if not verify_password(password, password_hash):
        return web.json_response({'error': 'Invalid email or password'}, status=401)
    
    # Update last_login
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE web_users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user_id,))
    conn.commit()
    conn.close()
    
    token = generate_token(user_id, email)
    return web.json_response({
        'success': True,
        'token': token,
        'user': {
            'id': user_id,
            'email': email,
            'telegram_id': telegram_id,
            'linked': telegram_id is not None
        }
    })


# ──────────────────────────────────────────────
# POST /api/web/auth/logout
# Header: Authorization: Bearer <token>
# ──────────────────────────────────────────────
async def logout(request):
    auth_header = request.headers.get('Authorization', '')
    if auth_header.startswith('Bearer '):
        token = auth_header[7:]
        if token in tokens:
            del tokens[token]
    return web.json_response({'success': True})


# ──────────────────────────────────────────────
# GET /api/web/auth/me
# Header: Authorization: Bearer <token>
# ──────────────────────────────────────────────
async def me(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    token = auth_header[7:]
    user_data = verify_token(token)
    if not user_data:
        return web.json_response({'error': 'invalid or expired token'}, status=401)
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, email, telegram_id, created_at FROM web_users WHERE id = ?',
              (user_data['user_id'],))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return web.json_response({'error': 'user not found'}, status=404)
    
    return web.json_response({
        'user': {
            'id': row[0],
            'email': row[1],
            'telegram_id': row[2],
            'created_at': row[3],
            'linked': row[2] is not None
        }
    })


# ──────────────────────────────────────────────
# POST /api/web/auth/request_link
# Header: Authorization: Bearer <token>
# Generates a link code for Telegram binding
# ──────────────────────────────────────────────
async def request_link(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    token = auth_header[7:]
    user_data = verify_token(token)
    if not user_data:
        return web.json_response({'error': 'invalid token'}, status=401)
    
    # Generate 6-digit code
    code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
    expires_at = datetime.now() + timedelta(minutes=10)
    
    conn = get_db()
    c = conn.cursor()
    
    # Delete old unused codes for this email
    c.execute('DELETE FROM link_codes WHERE email = ? AND is_used = 0', (user_data['email'],))
    c.execute('INSERT INTO link_codes (code, email, expires_at) VALUES (?, ?, ?)',
              (code, user_data['email'], expires_at.isoformat()))
    conn.commit()
    conn.close()
    
    return web.json_response({
        'code': code,
        'expires_in': 600,  # 10 minutes
        'message': f'Код: {code}. Введите его в боте @cloaknetvbot для привязки.'
    })


# ──────────────────────────────────────────────
# POST /api/web/auth/link_telegram (internal, called by bot)
# Body: {"code": "...", "telegram_id": ...}
# ──────────────────────────────────────────────
async def link_telegram(request):
    try:
        data = await request.json()
    except:
        return web.json_response({'error': 'invalid JSON'}, status=400)
    
    code = str(data.get('code', '')).strip()
    telegram_id = data.get('telegram_id')
    
    if not code or not telegram_id:
        return web.json_response({'error': 'code and telegram_id required'}, status=400)
    
    conn = get_db()
    c = conn.cursor()
    
    # Find valid unused code
    c.execute('''SELECT id, email FROM link_codes
                 WHERE code = ? AND is_used = 0 AND expires_at > ?
                 ORDER BY created_at DESC LIMIT 1''',
              (code, datetime.now().isoformat()))
    row = c.fetchone()
    
    if not row:
        conn.close()
        return web.json_response({'error': 'Invalid or expired code'}, status=400)
    
    link_id, email = row
    
    # Mark code as used
    c.execute('UPDATE link_codes SET is_used = 1 WHERE id = ?', (link_id,))
    
    # Check if telegram_id already linked to different user
    c.execute('SELECT id FROM web_users WHERE telegram_id = ? AND email != ?',
              (telegram_id, email))
    if c.fetchone():
        conn.close()
        return web.json_response({'error': 'Telegram already linked to another account'}, status=409)
    
    # Link telegram_id to web user
    c.execute('UPDATE web_users SET telegram_id = ? WHERE email = ?', (telegram_id, email))
    conn.commit()
    conn.close()
    
    return web.json_response({'success': True, 'message': 'Telegram linked successfully'})


def setup_web_auth_routes(app):
    """Register web auth routes"""
    app.router.add_post('/api/web/auth/register', register)
    app.router.add_post('/api/web/auth/login', login)
    app.router.add_post('/api/web/auth/logout', logout)
    app.router.add_get('/api/web/auth/me', me)
    app.router.add_post('/api/web/auth/request_link', request_link)
    app.router.add_post('/api/web/auth/link_telegram', link_telegram)
