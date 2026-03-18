"""API для Web App"""
import json
import logging
from aiohttp import web
from bot.utils.database import get_db, get_user_subscriptions, get_user_by_telegram

logger = logging.getLogger(__name__)


async def get_user_data(request):
    """Получить данные пользователя"""
    # Получаем telegram_id из URL параметра (поддерживаем both telegram_id and user_id)
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    
    if not telegram_id:
        return web.json_response({'error': 'telegram_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return web.json_response({'error': 'invalid telegram_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем пользователя
    cursor.execute("SELECT id, telegram_id, username, first_name, has_trial, purchase_count, COALESCE(balance, 0) as balance FROM users WHERE telegram_id = ?", (telegram_id,))
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
        'purchase_count': user_row[5],
        'balance': user_row[6] if len(user_row) > 6 else 0
    }
    
    # Получаем подписки
    cursor.execute("""
        SELECT s.id, s.status, s.expires_at, s.traffic_limit_bytes, s.traffic_used_bytes,
               s.devices_limit, s.servers_count, s.is_trial, s.is_paid, s.short_uuid,
               s.price, s.created_at, s.duration_days, GROUP_CONCAT(ss.node_name, ', ') as servers
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
            'price': row[10],
            'created_at': row[11],
            'duration_days': row[12] or 30,
            'servers_list': row[13] or ''
        })
    
    return web.json_response({
        'user': user,
        'subscriptions': subscriptions
    })


async def get_squads(request):
    """Получить доступные сквады"""
    try:
        from remnawave import RemnawaveSDK
        from config import REMNAWAVE_URL, REMNAWAVE_TOKEN
        
        sdk = RemnawaveSDK(base_url=REMNAWAVE_URL, token=REMNAWAVE_TOKEN)
        squads = await sdk.internal_squads.get_internal_squads()
        
        squads_list = []
        for s in squads.internal_squads:
            # Определяем страну по названию
            name = s.name.lower()
            country_emoji = "🌍"
            country_code = "XX"
            if "uk" in name or "gb" in name:
                country_emoji = "🇬🇧"
                country_code = "UK"
            elif "nl" in name or "netherlands" in name:
                country_emoji = "🇳🇱"
                country_code = "NL"
            elif "fi" in name or "finland" in name:
                country_emoji = "🇫🇮"
                country_code = "FI"
            elif "de" in name or "germany" in name:
                country_emoji = "🇩🇪"
                country_code = "DE"
            elif "ru" in name or "russia" in name or "msk" in name:
                country_emoji = "🇷🇺"
                country_code = "RU"
            
            squads_list.append({
                'uuid': str(s.uuid),
                'name': s.name,
                'country_code': country_code,
                'emoji': country_emoji,
                'members': s.info.members_count if s.info else 0
            })
        
        return web.json_response({'squads': squads_list})
    except Exception as e:
        logger.error(f"Ошибка получения сквадов: {e}")
        return web.json_response({'error': str(e)}, status=500)


async def get_subscription_servers(request):
    """Получить серверы подписки"""
    sub_id = request.query.get('sub_id')
    
    if not sub_id:
        return web.json_response({'error': 'sub_id required'}, status=400)
    
    try:
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid sub_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем серверы подписки
    cursor.execute("""
        SELECT node_uuid, node_name, country_code 
        FROM subscription_servers 
        WHERE subscription_id = ?
    """, (sub_id,))
    
    servers = []
    for row in cursor.fetchall():
        servers.append({
            'uuid': row[0],
            'name': row[1],
            'country_code': row[2]
        })
    
    conn.close()
    
    return web.json_response({
        'subscription_id': sub_id,
        'servers': servers
    })


async def update_subscription_servers(request):
    """Обновить серверы подписки (добавить/удалить)"""
    telegram_id = request.query.get('user_id') or request.query.get('telegram_id')
    sub_id = request.query.get('sub_id')
    action = request.query.get('action')  # 'add' или 'remove'
    squad_uuid = request.query.get('squad_uuid')
    
    if not telegram_id or not sub_id or not action or not squad_uuid:
        return web.json_response({'error': 'telegram_id, sub_id, action и squad_uuid required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid parameters'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Проверяем подписку
    cursor.execute("""
        SELECT s.remnawave_uuid, s.user_id, u.telegram_id
        FROM subscriptions s
        JOIN users u ON s.user_id = u.id
        WHERE s.id = ? AND u.telegram_id = ?
    """, (sub_id, telegram_id))
    
    row = cursor.fetchone()
    if not row:
        conn.close()
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    vpn_uuid, user_id, db_telegram_id = row
    conn.close()
    
    try:
        from remnawave import RemnawaveSDK
        from config import REMNAWAVE_URL, REMNAWAVE_TOKEN
        
        sdk = RemnawaveSDK(base_url=REMNAWAVE_URL, token=REMNAWAVE_TOKEN)
        
        if action == 'add':
            # Добавляем пользователя в сквад
            response = await sdk.internal_squads.client.request(
                method='POST',
                url=f'/internal-squads/{squad_uuid}/bulk-actions/add-users',
                json={'userUuids': [vpn_uuid]}
            )
            
            # Сохраняем в БД
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR IGNORE INTO subscription_servers 
                (subscription_id, node_uuid, node_name, country_code)
                VALUES (?, ?, ?, ?)
            """, (sub_id, squad_uuid, 'Server', squad_uuid[:8]))
            conn.commit()
            conn.close()
            
            return web.json_response({'success': True, 'action': 'added'})
        
        elif action == 'remove':
            # Удаляем пользователя из сквада
            response = await sdk.internal_squads.client.request(
                method='POST',
                url=f'/internal-squads/{squad_uuid}/bulk-actions/remove-users',
                json={'userUuids': [vpn_uuid]}
            )
            
            # Удаляем из БД
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM subscription_servers 
                WHERE subscription_id = ? AND node_uuid = ?
            """, (sub_id, squad_uuid))
            conn.commit()
            conn.close()
            
            return web.json_response({'success': True, 'action': 'removed'})
        
        else:
            return web.json_response({'error': 'invalid action'}, status=400)
            
    except Exception as e:
        logger.error(f"Ошибка обновления серверов: {e}")
        return web.json_response({'error': str(e)}, status=500)


async def get_addons_price(request):
    """Получить стоимость дополнений"""
    # Цена за сервер = 45₽
    # Цена за 1GB трафика = 2₽
    # Цена за 1 устройство = 25₽
    
    return web.json_response({
        'server_price': 45,
        'traffic_price_per_gb': 2,
        'device_price': 25
    })


async def add_subscription_traffic(request):
    """Добавить трафик к подписке"""
    telegram_id = request.query.get('user_id') or request.query.get('telegram_id')
    sub_id = request.query.get('sub_id')
    gb_amount = request.query.get('gb')  # сколько GB добавить
    
    if not telegram_id or not sub_id or not gb_amount:
        return web.json_response({'error': 'telegram_id, sub_id и gb required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
        sub_id = int(sub_id)
        gb_amount = int(gb_amount)
    except ValueError:
        return web.json_response({'error': 'invalid parameters'}, status=400)
    
    price_per_gb = 2
    total_price = gb_amount * price_per_gb
    
    # Проверяем баланс
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, balance FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return web.json_response({'error': 'user not found'}, status=404)
    
    user_id, balance = row
    
    if balance < total_price:
        conn.close()
        return web.json_response({'error': 'insufficient balance', 'required': total_price, 'available': balance}, status=400)
    
    # Списываем баланс
    cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (total_price, user_id))
    
    # Добавляем трафик
    gb_bytes = gb_amount * (1024**3)
    cursor.execute("UPDATE subscriptions SET traffic_limit_bytes = traffic_limit_bytes + ? WHERE id = ?", (gb_bytes, sub_id))
    
    conn.commit()
    conn.close()
    
    return web.json_response({
        'success': True,
        'gb_added': gb_amount,
        'price': total_price,
        'remaining_balance': balance - total_price
    })


async def get_subscription_traffic(request):
    """Получить актуальный трафик подписки из Remnawave"""
    sub_id = request.query.get('sub_id')
    
    if not sub_id:
        return web.json_response({'error': 'sub_id required'}, status=400)
    
    try:
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid sub_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем remnawave_uuid
    cursor.execute("SELECT remnawave_uuid, traffic_limit_bytes FROM subscriptions WHERE id = ?", (sub_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    uuid, limit_bytes = row
    
    if not uuid:
        conn.close()
        return web.json_response({'traffic_used': 0, 'traffic_limit': limit_bytes})
    
    # Получаем актуальный трафик из Remnawave
    try:
        from remnawave import RemnawaveSDK
        from config import REMNAWAVE_URL, REMNAWAVE_TOKEN
        
        sdk = RemnawaveSDK(base_url=REMNAWAVE_URL, token=REMNAWAVE_TOKEN)
        user = await sdk.users.get_user_by_uuid(uuid)
        
        if user and hasattr(user, 'user_traffic') and user.user_traffic:
            bytes_used = user.user_traffic.used_traffic_bytes or 0
            
            # Обновляем в БД
            cursor.execute("UPDATE subscriptions SET traffic_used_bytes = ? WHERE id = ?", (bytes_used, sub_id))
            conn.commit()
        else:
            bytes_used = 0
            
    except Exception as e:
        print(f"Ошибка получения трафика: {e}")
        bytes_used = 0
    
    conn.close()
    
    return web.json_response({
        'traffic_used': bytes_used,
        'traffic_limit': limit_bytes
    })


async def add_subscription_device(request):
    """Добавить устройство к подписке"""
    telegram_id = request.query.get('user_id') or request.query.get('telegram_id')
    sub_id = request.query.get('sub_id')
    
    if not telegram_id or not sub_id:
        return web.json_response({'error': 'telegram_id и sub_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid parameters'}, status=400)
    
    device_price = 25
    
    # Проверяем баланс
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, balance, devices_limit FROM users u JOIN subscriptions s ON u.id = s.user_id WHERE u.telegram_id = ? AND s.id = ?", (telegram_id, sub_id))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    user_id, balance, current_devices = row
    
    if balance < device_price:
        conn.close()
        return web.json_response({'error': 'insufficient balance', 'required': device_price, 'available': balance}, status=400)
    
    # Списываем баланс
    cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (device_price, user_id))
    
    # Добавляем устройство
    cursor.execute("UPDATE subscriptions SET devices_limit = devices_limit + 1 WHERE id = ?", (sub_id,))
    
    conn.commit()
    conn.close()
    
    return web.json_response({
        'success': True,
        'new_devices': current_devices + 1,
        'price': device_price,
        'remaining_balance': balance - device_price
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
    from config import YOOMONEY_WALLET, WEBHOOK_URL
    # URL для возврата после оплаты
    return_url = f"{WEBHOOK_URL.replace('/webhook', '')}/miniapp"
    payment_url = f"https://yoomoney.ru/quickpay/confirm?receiver={YOOMONEY_WALLET}&quickpay-form=button&paymentType=AC&sum={price}&label={sub_id}&successURL={return_url}"
    
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


async def create_subscription_api(request):
    """Создать подписку из Mini App"""
    import asyncio
    import uuid as uuid_module
    
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    days = int(request.query.get('days', '30'))
    traffic = int(request.query.get('traffic', '10'))
    devices = int(request.query.get('devices', '1'))
    servers_param = request.query.get('servers', '')
    # Уникальные серверы с сохранением порядка
    servers = list(dict.fromkeys([s for s in servers_param.split(',') if s])) if servers_param else []
    
    # Маппинг reset типа на стратегию RemnaWave
    traffic_reset_map = {
        'no_reset': 'NO_RESET',
        'daily': 'DAY',
        'weekly': 'WEEK',
        'monthly': 'MONTH'
    }
    traffic_reset_param = request.query.get('traffic_reset', 'no_reset')
    traffic_reset = traffic_reset_map.get(traffic_reset_param, 'NO_RESET')
    
    # Цена с фронтенда (или рассчитать, если не передана)
    try:
        price_from_frontend = float(request.query.get('price', '0'))
    except:
        price_from_frontend = 0
    
    if not telegram_id:
        return web.json_response({'error': 'telegram_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return web.json_response({'error': 'invalid parameters'}, status=400)
    
    from bot.utils.database import create_subscription, add_subscription_server
    from bot.utils.remnawave import create_vpn_user
    
    # Получаем user_id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, first_name FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return web.json_response({'error': 'user not found'}, status=404)
    
    user_id, username, first_name = row
    
    # Получаем номер подписки для генерации username
    cursor.execute("SELECT purchase_count FROM users WHERE id = ?", (user_id,))
    purchase_row = cursor.fetchone()
    purchase_count = purchase_row[0] if purchase_row else 0
    
    # Увеличиваем счётчик
    cursor.execute("UPDATE users SET purchase_count = purchase_count + 1 WHERE id = ?", (user_id,))
    conn.commit()
    
    # Генерируем username: user{telegram_id} или user{telegram_id}_001
    if purchase_count == 0:
        vpn_username = f"user{telegram_id}"
    else:
        vpn_username = f"user{telegram_id}_{purchase_count:03d}"
    
    # Рассчитываем цену по формуле Mini App
    # Множитель = количество сбросов (ceil(дней / интервал))
    # 4.5₽ × дни + 2₽ × GB × сбросы + 25₽ × устройства + 45₽ × серверы
    
    # Интервал сброса
    reset_intervals = {'no_reset': 999999, 'daily': 1, 'weekly': 7, 'monthly': 30}
    interval = reset_intervals.get(traffic_reset, 30)
    
    # Количество сбросов = ceil(дней / интервал)
    import math
    reset_count = math.ceil(days / interval) if interval < 999999 else 1
    
    servers_count = len(servers)
    base_price = days * 4.5 + traffic * 2 * reset_count + devices * 25 + servers_count * 45
    
    # Скидка за период
    discount = 1
    if days >= 365:
        discount = 0.7
    elif days >= 180:
        discount = 0.8
    elif days >= 90:
        discount = 0.85
    
    price = round(base_price * discount)
    
    # Используем цену с фронтенда, если передана
    if price_from_frontend > 0:
        price = price_from_frontend
    
    import uuid as uuid_module
    import random
    import string
    
    # Генерируем уникальный username
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    username = f"user{telegram_id}_{random_suffix}"
    
    # Создаём пользователя в RemnaWave (выключен до оплаты)
    try:
        import time, random
        # Генерируем уникальное описание и тег
        description = f"sub_{int(time.time())}_{random.randint(1000,9999)}_{telegram_id}"
        
        # Получаем UUID сквадов для выбранных серверов
        squad_uuids = []
        if servers:
            try:
                from remnawave import RemnawaveSDK
                from config import REMNAWAVE_URL, REMNAWAVE_TOKEN
                
                sdk = RemnawaveSDK(base_url=REMNAWAVE_URL, token=REMNAWAVE_TOKEN)
                all_squads = await sdk.internal_squads.get_internal_squads()
                
                # Маппинг country_code -> uuid
                country_to_uuid = {}
                for s in all_squads.internal_squads:
                    name = s.name.lower()
                    if "uk" in name or "gb" in name:
                        country_to_uuid["UK"] = str(s.uuid)
                    elif "nl" in name or "netherlands" in name:
                        country_to_uuid["NL"] = str(s.uuid)
                    elif "fi" in name or "finland" in name:
                        country_to_uuid["FI"] = str(s.uuid)
                    elif "de" in name or "germany" in name:
                        country_to_uuid["DE"] = str(s.uuid)
                    elif "ru" in name or "russia" in name or "msk" in name:
                        country_to_uuid["RU"] = str(s.uuid)
                
                # Выбираем UUID для выбранных серверов
                for server_code in servers:
                    if server_code in country_to_uuid:
                        squad_uuids.append(country_to_uuid[server_code])
            except Exception as e:
                logger.error(f"Ошибка получения сквадов: {e}")
        
        # Создаём VPN пользователя со сквадами
        vpn_user = await create_vpn_user(
            username=vpn_username,
            traffic_limit_bytes=traffic * (1024**3),
            expire_days=days,
            is_disabled=True,
            description=description,
            active_squads=squad_uuids if squad_uuids else None,
            traffic_reset=traffic_reset,
            devices_limit=devices
        )
        sub_uuid = vpn_user["uuid"]
        
    except Exception as e:
        logger.error(f"Ошибка создания VPN пользователя: {e}")
        return web.json_response({'error': f'Ошибка создания VPN: {str(e)}'}, status=500)
    
    # Создаём подписку в БД
    try:
        sub_id = create_subscription(
            user_id=user_id,
            remnawave_uuid=vpn_user["uuid"],
            short_uuid=vpn_user["short_uuid"],
            username=vpn_user["username"],
            duration_days=days,
            traffic_limit_bytes=traffic * (1024**3),
            devices_limit=devices,
            servers_count=len(servers),
            reset_type='monthly',
            is_trial=False,
            is_paid=False,
            price=price
        )
        
        # Сохраняем выбранные серверы
        if servers:
            for server_code in servers:
                # Маппинг country_code -> name для сохранения
                server_names = {
                    'UK': 'UK - Server',
                    'NL': 'NL - Server',
                    'FI': 'FI - Server',
                    'RU': 'Russia',
                    'DE': 'Germany'
                }
                server_name = server_names.get(server_code, server_code)
                add_subscription_server(sub_id, server_code, server_name, server_code)
        
    except Exception as e:
        logger.error(f"Ошибка создания подписки: {e}")
        conn.close()
        return web.json_response({'error': str(e)}, status=500)
    
    conn.close()
    
    return web.json_response({
        'success': True,
        'subscription_id': sub_id,
        'price': price,
        'message': f'Подписка создана! Цена: {price}₽'
    })


async def create_trial_subscription(request):
    """Создать триал подписку (тестовый период)"""
    telegram_id = request.query.get('user_id') or request.query.get('telegram_id')
    
    if not telegram_id:
        return web.json_response({'error': 'telegram_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return web.json_response({'error': 'invalid telegram_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Проверяем пользователя
    cursor.execute("SELECT id, username, first_name, has_trial FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return web.json_response({'error': 'user not found'}, status=404)
    
    user_id, username, first_name, has_trial = row
    
    # Проверяем: если уже был триал - отказываем
    if has_trial:
        conn.close()
        return web.json_response({'error': 'trial already used'}, status=400)
    
    # Проверяем: есть ли уже активная оплаченная подписка
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE user_id = ? AND is_paid = 1 AND status = 'active'", (user_id,))
    if cursor.fetchone()[0] > 0:
        conn.close()
        return web.json_response({'error': 'already has active subscription'}, status=400)
    
    conn.close()
    
    # Параметры триала
    TRIAL_DAYS = 3
    TRIAL_TRAFFIC = 5  # GB
    TRIAL_DEVICES = 1
    
    # Генерируем уникальный username
    import random
    import string
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    vpn_username = f"trial{telegram_id}_{random_suffix}"
    
    # Импортируем функцию создания VPN пользователя
    from bot.utils.remnawave import create_vpn_user
    
    try:
        # Генерируем уникальное описание: trial_{timestamp}_{random}_{telegram_id}
        import time, random
        description = f"trial_{int(time.time())}_{random.randint(1000,9999)}_{telegram_id}"
        
        # Создаём VPN пользователя (сразу активен)
        vpn_user = await create_vpn_user(
            username=vpn_username,
            traffic_limit_bytes=TRIAL_TRAFFIC * (1024**3),
            expire_days=TRIAL_DAYS,
            is_disabled=False,  # Сразу активен
            description=description,
            traffic_reset="NO_RESET",
            devices_limit=TRIAL_DEVICES
        )
        
        # Добавляем в первый доступный сквад
        try:
            from remnawave import RemnawaveSDK
            from config import REMNAWAVE_URL, REMNAWAVE_TOKEN
            sdk = RemnawaveSDK(base_url=REMNAWAVE_URL, token=REMNAWAVE_TOKEN)
            squads = await sdk.internal_squads.get_internal_squads()
            if squads.internal_squads:
                first_squad = squads.internal_squads[0]
                # Добавляем пользователя в сквад
                response = await sdk.internal_squads.client.request(
                    method='POST',
                    url=f'/internal-squads/{str(first_squad.uuid)}/bulk-actions/add-users',
                    json={'userUuids': [vpn_user["uuid"]]}
                )
        except Exception as sq_e:
            logger.error(f"Ошибка добавления в сквад: {sq_e}")
        
        # Создаём подписку в БД
        from bot.utils.database import create_subscription
        from datetime import datetime, timedelta
        
        conn = get_db()
        cursor = conn.cursor()
        
        expires_at = datetime.now() + timedelta(days=TRIAL_DAYS)
        
        cursor.execute("""
            INSERT INTO subscriptions 
            (user_id, remnawave_uuid, short_uuid, username, duration_days, traffic_limit_bytes,
             devices_limit, servers_count, reset_type, is_trial, is_paid, price, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, vpn_user["uuid"], vpn_user["short_uuid"], vpn_user["username"], 
              TRIAL_TRAFFIC * (1024**3), TRIAL_TRAFFIC * (1024**3),
              TRIAL_DEVICES, 1, 'none', True, True, 0, expires_at))
        
        sub_id = cursor.lastrowid
        
        # Сохраняем сервер (первый сквад)
        if squads.internal_squads:
            first_squad = squads.internal_squads[0]
            cursor.execute(
                "INSERT INTO subscription_servers (subscription_id, node_uuid, node_name, country_code) VALUES (?, ?, ?, ?)",
                (sub_id, str(first_squad.uuid), first_squad.name, first_squad.name[:2].upper())
            )
        
        # Помечаем что триал использован
        cursor.execute("UPDATE users SET has_trial = 1 WHERE id = ?", (user_id,))
        
        conn.commit()
        conn.close()
        
        # Отправляем уведомление о триале
        try:
            from bot.utils.notifications import notify_trial_activated
            asyncio.create_task(notify_trial_activated(telegram_id))
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления о триале: {e}")
        
        return web.json_response({
            'success': True,
            'subscription_id': sub_id,
            'message': f'Тестовый период активирован! {TRIAL_DAYS} дней, {TRIAL_TRAFFIC} GB'
        })
        
    except Exception as e:
        logger.error(f"Ошибка создания триала: {e}")
        return web.json_response({'error': str(e)}, status=500)


async def get_renewal_options(request):
    """Получить варианты продления"""
    sub_id = request.query.get('sub_id')
    if not sub_id:
        return web.json_response({'error': 'sub_id required'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.duration_days, s.traffic_limit_bytes, s.devices_limit, s.reset_type,
               (SELECT COUNT(*) FROM subscription_servers WHERE subscription_id = s.id) as servers_count
        FROM subscriptions s
        WHERE s.id = ?
    """, (sub_id,))
    
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    duration_days, traffic_bytes, devices, reset_type, servers_count = row
    traffic_gb = traffic_bytes / (1024**3) if traffic_bytes else 10
    
    # Интервалы reset
    reset_intervals = {
        'NO_RESET': 999999,
        'DAY': 1,
        'WEEK': 7,
        'MONTH': 30,
        'none': 999999
    }
    interval = reset_intervals.get(reset_type, 30)
    
    # Варианты продления с правильным расчётом цены
    import math
    options = []
    for days in [30, 90, 180, 365]:
        # Количество сбросов = ceil(дней / интервал)
        reset_count = math.ceil(days / interval) if interval < 999999 else 1
        
        # Базовая цена: 4.5₽ × дни + 2₽ × GB × сбросы + 25₽ × устройства + 45₽ × серверы
        base_price = days * 4.5 + traffic_gb * 2 * reset_count + devices * 25 + servers_count * 45
        
        # Скидка за период
        discount = 1
        if days >= 365:
            discount = 0.7
        elif days >= 180:
            discount = 0.8
        elif days >= 90:
            discount = 0.85
        
        price = round(base_price * discount)
        
        name = {30: '1 месяц', 90: '3 месяца', 180: '6 месяцев', 365: '1 год'}[days]
        options.append({
            'days': days, 
            'name': name, 
            'price': price,
            'traffic': traffic_gb,
            'devices': devices
        })
    
    return web.json_response({
        'sub_id': int(sub_id),
        'options': options,
        'current': {
            'traffic': traffic_gb,
            'devices': devices,
            'reset_type': reset_type
        }
    })


async def renew_subscription(request):
    """Продлить подписку"""
    import asyncio
    from datetime import datetime, timedelta
    
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    sub_id = request.query.get('sub_id')
    days = int(request.query.get('days', '30'))
    traffic = int(request.query.get('traffic', '10'))
    devices = int(request.query.get('devices', '1'))
    servers_param = request.query.get('servers', '')
    # Уникальные серверы с сохранением порядка
    servers = list(dict.fromkeys([s for s in servers_param.split(',') if s])) if servers_param else []
    traffic_reset_param = request.query.get('traffic_reset', 'monthly')
    
    if not telegram_id or not sub_id:
        return web.json_response({'error': 'telegram_id and sub_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid parameters'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем пользователя
    cursor.execute("SELECT id, balance FROM users WHERE telegram_id = ?", (telegram_id,))
    user_row = cursor.fetchone()
    
    if not user_row:
        conn.close()
        return web.json_response({'error': 'user not found'}, status=404)
    
    user_id, balance = user_row
    
    # Получаем текущую подписку
    cursor.execute("""
        SELECT expires_at, reset_type, traffic_limit_bytes, devices_limit, 
               remnawave_uuid, status, is_paid
        FROM subscriptions 
        WHERE id = ? AND user_id = ?
    """, (sub_id, user_id))
    sub_row = cursor.fetchone()
    
    if not sub_row:
        conn.close()
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    expires_at, current_reset, current_traffic, current_devices, uuid, status, is_paid = sub_row
    
    # Проверяем, что подписка активна
    if status != 'active':
        conn.close()
        return web.json_response({'error': 'subscription not active'}, status=400)
    
    # Маппинг reset типа
    traffic_reset_map = {
        'no_reset': 'NO_RESET',
        'daily': 'DAY',
        'weekly': 'WEEK',
        'monthly': 'MONTH'
    }
    traffic_reset = traffic_reset_map.get(traffic_reset_param, 'MONTH')
    
    # Рассчитываем цену с учётом traffic_reset
    reset_intervals = {
        'no_reset': 999999,
        'daily': 1,
        'weekly': 7,
        'monthly': 30
    }
    interval = reset_intervals.get(traffic_reset_param, 30)
    
    # Количество сбросов = ceil(дней / интервал)
    import math
    reset_count = math.ceil(days / interval) if interval < 999999 else 1
    
    # Базовая цена: 4.5₽ × дни + 2₽ × GB × сбросы + 25₽ × устройства + 45₽ × серверы
    servers_count = len(servers) if servers else 1
    base_price = days * 4.5 + traffic * 2 * reset_count + devices * 25 + servers_count * 45
    
    # Скидка за период
    discount = 1
    if days >= 365:
        discount = 0.7
    elif days >= 180:
        discount = 0.8
    elif days >= 90:
        discount = 0.85
    
    price = round(base_price * discount)
    
    # Проверяем баланс
    if balance < price:
        conn.close()
        return web.json_response({
            'error': 'insufficient balance', 
            'required': price, 
            'available': balance
        }, status=400)
    
    # Списываем баланс
    cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (price, user_id))
    
    # Вычисляем новую дату окончания
    current_expires = datetime.fromisoformat(expires_at) if expires_at else datetime.now()
    new_expires = current_expires + timedelta(days=days)
    
    # Обновляем подписку в БД
    cursor.execute("""
        UPDATE subscriptions 
        SET expires_at = ?, 
            traffic_limit_bytes = ?,
            devices_limit = ?,
            reset_type = ?,
            price = price + ?
        WHERE id = ?
    """, (
        new_expires.isoformat(),
        traffic * (1024**3),
        devices,
        traffic_reset,
        price,
        sub_id
    ))
    
    # Обновляем серверы (удаляем старые, добавляем новые)
    cursor.execute("DELETE FROM subscription_servers WHERE subscription_id = ?", (sub_id,))
    
    server_names = {
        'UK': 'UK - Server',
        'NL': 'NL - Server',
        'FI': 'FI - Server',
        'RU': 'Russia',
        'DE': 'Germany'
    }
    
    for server_code in servers:
        server_name = server_names.get(server_code, server_code)
        cursor.execute("""
            INSERT INTO subscription_servers (subscription_id, node_uuid, node_name, country_code)
            VALUES (?, ?, ?, ?)
        """, (sub_id, server_code, server_name, server_code))
    
    conn.commit()
    conn.close()
    
    # Обновляем в RemnaWave
    try:
        from bot.utils.remnawave import update_vpn_user
        await update_vpn_user(
            uuid=uuid,
            expire_days=days,
            traffic_limit_bytes=traffic * (1024**3),
            traffic_reset=traffic_reset,
            devices_limit=devices
        )
    except Exception as e:
        logger.error(f"Ошибка обновления RemnaWave: {e}")
    
    # Отправляем уведомление
    try:
        import subprocess
        subprocess.Popen([
            'python3', '-c', f'''
import asyncio
import sys
sys.path.insert(0, "/root/.openclaw/workspace/vpn-bot")
from bot.utils.notifications import notify_payment_success
asyncio.run(notify_payment_success({telegram_id}, {{
    "id": {sub_id},
    "expires_at": "{new_expires.isoformat()}",
    "traffic_limit": {traffic},
    "devices": {devices}
}}, {balance - price}))
'''
        ], cwd='/root/.openclaw/workspace/vpn-bot',
           stdout=subprocess.DEVNULL,
           stderr=subprocess.DEVNULL)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")
    
    return web.json_response({
        'success': True,
        'sub_id': sub_id,
        'days_added': days,
        'new_expires': new_expires.isoformat(),
        'price': price,
        'remaining_balance': balance - price
    })


async def get_user_payments(request):
    """Получить историю платежей пользователя"""
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    
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


async def get_balance_topup(request):
    """Получить ссылку для пополнения баланса"""
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    amount = request.query.get('amount')
    
    if not telegram_id:
        return web.json_response({'error': 'telegram_id required'}, status=400)
    
    if not amount:
        return web.json_response({'error': 'amount required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
        amount = float(amount)
    except ValueError:
        return web.json_response({'error': 'invalid parameters'}, status=400)
    
    if amount < 10:
        return web.json_response({'error': 'min amount is 10'}, status=400)
    
    # Получаем user_id
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return web.json_response({'error': 'user not found'}, status=404)
    
    user_id = row[0]
    
    # Создаём label для пополнения: topup_{user_id}_{amount}
    from config import YOOMONEY_WALLET, WEBHOOK_URL
    label = f"topup_{user_id}_{amount}"
    
    # URL для возврата после оплаты
    return_url = f"{WEBHOOK_URL.replace('/webhook', '')}/miniapp"
    payment_url = f"https://yoomoney.ru/quickpay/confirm?receiver={YOOMONEY_WALLET}&quickpay-form=button&paymentType=AC&sum={amount}&label={label}&successURL={return_url}"
    
    return web.json_response({
        'payment_url': payment_url,
        'amount': amount
    })


async def pay_with_balance(request):
    """Оплатить подписку с баланса"""
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    sub_id = request.query.get('sub_id')
    
    if not telegram_id or not sub_id:
        return web.json_response({'error': 'telegram_id and sub_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid parameters'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем user_id и баланс
    cursor.execute("SELECT id, balance FROM users WHERE telegram_id = ?", (telegram_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return web.json_response({'error': 'user not found'}, status=404)
    
    user_id, balance = row
    
    # Получаем подписку и цену
    cursor.execute("SELECT price, is_paid FROM subscriptions WHERE id = ? AND user_id = ?", (sub_id, user_id))
    sub_row = cursor.fetchone()
    
    if not sub_row:
        conn.close()
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    price, is_paid = sub_row
    
    if is_paid:
        conn.close()
        return web.json_response({'error': 'already paid'}, status=400)
    
    if balance < price:
        conn.close()
        return web.json_response({'error': 'insufficient balance', 'required': price, 'available': balance}, status=400)
    
    # Списываем баланс
    cursor.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (price, user_id))
    
    # Получаем UUID для активации VPN
    cursor.execute("SELECT remnawave_uuid FROM subscriptions WHERE id = ?", (sub_id,))
    uuid_row = cursor.fetchone()
    uuid = uuid_row[0] if uuid_row else None
    
    # Активируем подписку
    from datetime import datetime, timedelta
    cursor.execute("UPDATE subscriptions SET is_paid = 1, status = 'active', paid_at = ? WHERE id = ?", 
                   (datetime.now().isoformat(), sub_id))
    
    # Начисляем реферальные бонусы
    cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (user_id,))
    referrer_row = cursor.fetchone()
    
    if referrer_row and referrer_row[0]:
        referrer_id = referrer_row[0]
        
        # Уровень 1: 5%
        bonus_level1 = price * 0.05
        cursor.execute("UPDATE users SET referral_bonus = referral_bonus + ?, balance = balance + ? WHERE id = ?", 
                    (bonus_level1, bonus_level1, referrer_id))
        
        # Уровень 2: 3%
        cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (referrer_id,))
        level2_row = cursor.fetchone()
        if level2_row and level2_row[0]:
            bonus_level2 = price * 0.03
            cursor.execute("UPDATE users SET referral_bonus = referral_bonus + ?, balance = balance + ? WHERE id = ?",
                        (bonus_level2, bonus_level2, level2_row[0]))
            
            # Уровень 3: 1%
            cursor.execute("SELECT referrer_id FROM users WHERE id = ?", (level2_row[0],))
            level3_row = cursor.fetchone()
            if level3_row and level3_row[0]:
                bonus_level3 = price * 0.01
                cursor.execute("UPDATE users SET referral_bonus = referral_bonus + ?, balance = balance + ? WHERE id = ?",
                            (bonus_level3, bonus_level3, level3_row[0]))
    
    conn.commit()
    conn.close()
    
    # Активируем VPN в панели
    if uuid:
        try:
            # Используем путь к venv python
            import subprocess
            result = subprocess.run(
                ['/root/.openclaw/workspace/vpn-bot/venv/bin/python3', '-c', f'''
import asyncio
import sys
sys.path.insert(0, "/root/.openclaw/workspace/vpn-bot")
from bot.utils.remnawave import enable_vpn_user
asyncio.run(enable_vpn_user("{uuid}"))
'''],
                capture_output=True,
                text=True,
                cwd='/root/.openclaw/workspace/vpn-bot'
            )
            if result.returncode == 0:
                logger.info(f"✅ VPN активирован: {uuid}")
            else:
                logger.error(f"Ошибка активации: {result.stderr}")
        except Exception as e:
            logger.error(f"Ошибка активации VPN: {e}")
    
    # Отправляем уведомление об оплате
    try:
        # Получаем данные подписки для уведомления
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT s.id, s.expires_at, s.traffic_limit_bytes, s.devices_limit, u.balance
            FROM subscriptions s
            JOIN users u ON s.user_id = u.id
            WHERE s.id = ?
        """, (sub_id,))
        sub_row = cursor.fetchone()
        conn.close()
        
        if sub_row:
            # Запускаем уведомление через subprocess
            import subprocess
            try:
                subproc = subprocess.run([
                    'python3', '-c', f'''
import asyncio
from bot.utils.notifications import notify_payment_success
asyncio.run(notify_payment_success({telegram_id}, {{
    "id": {sub_row[0]},
    "expires_at": "{sub_row[1]}",
    "traffic_limit": {sub_row[2] / (1024**3) if sub_row[2] else 0},
    "devices": {sub_row[3]}
}}, {sub_row[4]}))
'''
                ], cwd='/root/.openclaw/workspace/vpn-bot', capture_output=True, timeout=10)
                if subproc.returncode != 0:
                    logger.error(f"Ошибка уведомления: {subproc.stderr.decode()}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")
    
    return web.json_response({
        'success': True,
        'sub_id': sub_id,
        'amount_paid': price,
        'remaining_balance': balance - price
    })


async def notify_payment(request):
    """Отправить уведомление об оплате"""
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    sub_id = request.query.get('sub_id')
    
    if not telegram_id or not sub_id:
        return web.json_response({'error': 'telegram_id and sub_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
        sub_id = int(sub_id)
    except ValueError:
        return web.json_response({'error': 'invalid parameters'}, status=400)
    
    # Получаем данные подписки
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT price FROM subscriptions WHERE id = ?", (sub_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        return web.json_response({'error': 'subscription not found'}, status=404)
    
    price = row[0]
    
    # Отправляем уведомление через бота
    try:
        from bot.utils.notifications import send_telegram_message
        await send_telegram_message(
            telegram_id,
            f"✅ <b>Подписка оплачена!</b>\n\n"
            f"💰 Списано: {price}₽\n\n"
            f"Можете использовать VPN!",
            parse_mode="HTML"
        )
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления: {e}")
    
    return web.json_response({'success': True})


# === Реферальная система ===
async def get_referral_info(request):
    """Получить информацию о рефералах"""
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    
    if not telegram_id:
        return web.json_response({'error': 'telegram_id required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return web.json_response({'error': 'invalid telegram_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Получаем данные пользователя
    cursor.execute("""
        SELECT id, referral_code, referral_bonus
        FROM users WHERE telegram_id = ?
    """, (telegram_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return web.json_response({'error': 'user not found'}, status=404)
    
    user_id, referral_code, referral_bonus = row
    
    # Получаем количество рефералов
    cursor.execute("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user_id,))
    referral_count = cursor.fetchone()[0]
    
    # Получаем список рефералов (уровень 1)
    cursor.execute("""
        SELECT u.telegram_id, u.username, u.first_name, u.referral_bonus, u.created_at
        FROM users u WHERE u.referrer_id = ?
        ORDER BY u.created_at DESC LIMIT 20
    """, (user_id,))
    referrals = []
    for r in cursor.fetchall():
        referrals.append({
            'telegram_id': r[0],
            'username': r[1],
            'first_name': r[2],
            'bonus': r[3],
            'joined_at': r[4]
        })
    
    conn.close()
    
    return web.json_response({
        'referral_code': referral_code,
        'referral_bonus': referral_bonus,
        'referral_count': referral_count,
        'total_referrals': referral_count,
        'total_earned': referral_bonus,
        'referrals': referrals
    })


async def register_referral(request):
    """Зарегистрировать реферала (при переходе по ссылке)"""
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    referral_code = request.query.get('referral_code')
    
    if not telegram_id or not referral_code:
        return web.json_response({'error': 'telegram_id and referral_code required'}, status=400)
    
    try:
        telegram_id = int(telegram_id)
    except ValueError:
        return web.json_response({'error': 'invalid telegram_id'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Проверяем реферальный код
    cursor.execute("SELECT id FROM users WHERE referral_code = ?", (referral_code,))
    referrer_row = cursor.fetchone()
    
    if not referrer_row:
        conn.close()
        return web.json_response({'error': 'invalid referral code'}, status=404)
    
    referrer_id = referrer_row[0]
    
    # Проверяем что пользователь ещё не имеет реферала
    cursor.execute("SELECT referrer_id, telegram_id FROM users WHERE telegram_id = ?", (telegram_id,))
    user_row = cursor.fetchone()
    
    if not user_row:
        conn.close()
        return web.json_response({'error': 'user not found'}, status=404)
    
    if user_row[0]:
        conn.close()
        return web.json_response({'message': 'already has referrer'})
    
    # Регистрируем реферала
    cursor.execute("UPDATE users SET referrer_id = ? WHERE telegram_id = ?", (referrer_id, telegram_id))
    conn.commit()
    conn.close()
    
    logger.info(f"✅ Реферал зарегистрирован: {telegram_id} -> {referrer_id}")
    
    return web.json_response({'success': True})


# === Админ API ===
async def admin_get_stats(request):
    """Статистика для админа"""
    from config import ADMIN_ID
    
    # Простая проверка через query параметр (в реальном проекте использовать сессии/JWT)
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    conn = get_db()
    cursor = conn.cursor()
    
    # Статистика пользователей
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    # Статистика подписок
    cursor.execute("SELECT COUNT(*) FROM subscriptions")
    total_subs = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM subscriptions WHERE status = 'active'")
    active_subs = cursor.fetchone()[0]
    
    # Общий баланс
    cursor.execute("SELECT COALESCE(SUM(balance), 0) FROM users")
    total_balance = cursor.fetchone()[0]
    
    conn.close()
    
    return web.json_response({
        'total_users': total_users,
        'total_subscriptions': total_subs,
        'active_subscriptions': active_subs,
        'total_balance': total_balance
    })


async def admin_get_user_detail(request):
    """Детали пользователя"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    user_id = request.query.get('user_id')
    if not user_id:
        return web.json_response({'error': 'user_id required'}, status=400)
    
    user_id = int(user_id)
    conn = get_db()
    cursor = conn.cursor()
    
    # Данные пользователя
    cursor.execute("""
        SELECT id, telegram_id, username, first_name, balance, referral_bonus, 
               referrer_id, is_active, created_at
        FROM users WHERE id = ?
    """, (user_id,))
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return web.json_response({'error': 'user not found'}, status=404)
    
    user = {
        'id': row[0],
        'telegram_id': row[1],
        'username': row[2],
        'first_name': row[3],
        'balance': row[4],
        'referral_bonus': row[5],
        'referrer_id': row[6],
        'is_blocked': not bool(row[7]) if row[7] is not None else False,
        'created_at': row[8]
    }
    
    # Подписки
    cursor.execute("""
        SELECT id, status, is_paid, price, expires_at, created_at,
               traffic_limit_bytes, duration_days, devices_limit
        FROM subscriptions WHERE user_id = ?
        ORDER BY id DESC
    """, (user_id,))
    
    subscriptions = []
    for s in cursor.fetchall():
        traffic_gb = (s[6] or 0) / (1024**3) if s[6] else 0
        subscriptions.append({
            'id': s[0],
            'status': s[1],
            'is_paid': bool(s[2]),
            'price': s[3],
            'expires_at': s[4],
            'created_at': s[5],
            'traffic_gb': round(traffic_gb, 1),
            'days': s[7] or 30,
            'devices': s[8] or 1
        })
    
    # Платежи
    cursor.execute("""
        SELECT id, amount, currency, status, created_at
        FROM payments WHERE user_id = ?
        ORDER BY id DESC
        LIMIT 20
    """, (user_id,))
    
    payments = []
    for p in cursor.fetchall():
        payments.append({
            'id': p[0],
            'amount': p[1],
            'currency': p[2],
            'status': p[3],
            'created_at': p[4]
        })
    
    # Рефералы
    cursor.execute("""
        SELECT id, telegram_id, username, first_name, balance
        FROM users WHERE referrer_id = ?
        LIMIT 10
    """, (user_id,))
    
    referrals = []
    for r in cursor.fetchall():
        referrals.append({
            'id': r[0],
            'telegram_id': r[1],
            'username': r[2],
            'first_name': r[3],
            'balance': r[4]
        })
    
    conn.close()
    
    return web.json_response({
        'user': user,
        'subscriptions': subscriptions,
        'payments': payments,
        'referrals': referrals
    })


async def admin_get_users(request):
    """Список пользователей"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT u.id, u.telegram_id, u.username, u.first_name, u.balance, 
               u.referral_bonus, u.created_at,
               (SELECT COUNT(*) FROM subscriptions WHERE user_id = u.id) as sub_count
        FROM users u
        ORDER BY u.id DESC
        LIMIT 100
    """)
    
    users = []
    for row in cursor.fetchall():
        users.append({
            'id': row[0],
            'telegram_id': row[1],
            'username': row[2],
            'first_name': row[3],
            'balance': row[4],
            'referral_bonus': row[5],
            'created_at': row[6],
            'subscription_count': row[7]
        })
    
    conn.close()
    return web.json_response({'users': users})


async def admin_get_subscriptions(request):
    """Список подписок"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT s.id, s.user_id, s.status, s.is_paid, s.price, s.expires_at, s.created_at,
               s.traffic_limit_bytes, s.duration_days, s.devices_limit,
               u.telegram_id, u.username, u.first_name
        FROM subscriptions s
        LEFT JOIN users u ON s.user_id = u.id
        ORDER BY s.id DESC
        LIMIT 100
    """)
    
    subs = []
    for row in cursor.fetchall():
        traffic_gb = (row[7] or 0) / (1024**3) if row[7] else 0
        subs.append({
            'id': row[0],
            'user_id': row[1],
            'status': row[2],
            'is_paid': bool(row[3]),
            'price': row[4],
            'expires_at': row[5],
            'created_at': row[6],
            'traffic_gb': round(traffic_gb, 1),
            'days': row[8] or 30,
            'devices': row[9] or 1,
            'telegram_id': row[10],
            'username': row[11] or row[12] or 'Unknown',
            'tariff_name': f"{row[8] or 30} дней"
        })
    
    conn.close()
    return web.json_response({'subscriptions': subs})


async def admin_get_payments(request):
    """Список платежей (упрощённый)"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    # Пока возвращаем пустой список - нужно отдельную таблицу платежей
    return web.json_response({'payments': []})


async def admin_add_balance(request):
    """Добавить баланс пользователю"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    user_id = request.query.get('user_id')
    amount = request.query.get('amount')
    
    if not user_id or not amount:
        return web.json_response({'error': 'user_id and amount required'}, status=400)
    
    try:
        user_id = int(user_id)
        amount = float(amount)
    except ValueError:
        return web.json_response({'error': 'invalid parameters'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    
    cursor.execute("SELECT balance, telegram_id FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    new_balance, telegram_id = row
    
    conn.close()
    
    # Отправляем уведомление о пополнении
    if telegram_id:
        try:
            import subprocess
            subprocess.Popen([
                'python3', '-c', f'''
import asyncio
import sys
sys.path.insert(0, "/root/.openclaw/workspace/vpn-bot")
from bot.utils.notifications import notify_balance_topup
asyncio.run(notify_balance_topup({telegram_id}, {amount}, {new_balance}))
'''
            ], cwd='/root/.openclaw/workspace/vpn-bot',
               stdout=subprocess.DEVNULL,
               stderr=subprocess.DEVNULL)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
    
    return web.json_response({
        'success': True,
        'user_id': user_id,
        'amount_added': amount,
        'new_balance': new_balance
    })


# === Серверы ===
async def admin_get_servers(request):
    """Получить список серверов"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    conn = get_db()
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='servers'")
        if not cursor.fetchone():
            cursor.execute("""CREATE TABLE IF NOT EXISTS servers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, host TEXT NOT NULL, ip TEXT NOT NULL, port INTEGER DEFAULT 22, username TEXT DEFAULT 'root', location TEXT, status TEXT DEFAULT 'offline', is_active INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            conn.commit()
            return web.json_response({'servers': []})
        
        cursor.execute("SELECT id, name, host, ip, port, username, location, status, is_active, created_at FROM servers ORDER BY id DESC")
        servers = []
        for row in cursor.fetchall():
            servers.append({'id': row[0], 'name': row[1], 'host': row[2], 'ip': row[3], 'port': row[4], 'username': row[5], 'location': row[6], 'status': row[7], 'is_active': bool(row[8]), 'created_at': row[9]})
        
        conn.close()
        return web.json_response({'servers': servers})
    except Exception as e:
        conn.close()
        return web.json_response({'error': str(e)}, status=500)


async def admin_add_server(request):
    """Добавить сервер"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    name = data.get('name')
    host = data.get('host')
    ip = data.get('ip')
    port = int(data.get('port', 22))
    username = data.get('username', 'root')
    location = data.get('location', '')
    
    if not name or not host or not ip:
        return web.json_response({'error': 'name, host, ip required'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO servers (name, host, ip, port, username, location, status, is_active) VALUES (?, ?, ?, ?, ?, ?, 'offline', 1)", (name, host, ip, port, username, location))
    conn.commit()
    server_id = cursor.lastrowid
    conn.close()
    
    return web.json_response({'success': True, 'server_id': server_id})


async def admin_delete_server(request):
    """Удалить сервер"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    server_id = int(data.get('server_id'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM servers WHERE id = ?", (server_id,))
    conn.commit()
    conn.close()
    
    return web.json_response({'success': True})


async def admin_toggle_server(request):
    """Включить/выключить сервер"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    server_id = int(data.get('server_id'))
    is_active = int(data.get('is_active', 1))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE servers SET is_active = ? WHERE id = ?", (is_active, server_id))
    conn.commit()
    conn.close()
    
    return web.json_response({'success': True})


# === Тарифы ===
async def admin_get_tariffs(request):
    """Получить список тарифов"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='tariffs'")
    if not cursor.fetchone():
        cursor.execute("""CREATE TABLE IF NOT EXISTS tariffs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, days INTEGER NOT NULL, price REAL NOT NULL, traffic_gb INTEGER DEFAULT 10, devices INTEGER DEFAULT 1, is_active INTEGER DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        conn.commit()
        conn.close()
        return web.json_response({'tariffs': []})
    
    cursor.execute("SELECT id, name, days, price, traffic_gb, devices, is_active, created_at FROM tariffs ORDER BY days ASC")
    tariffs = []
    for row in cursor.fetchall():
        tariffs.append({'id': row[0], 'name': row[1], 'days': row[2], 'price': row[3], 'traffic_gb': row[4], 'devices': row[5], 'is_active': bool(row[6]), 'created_at': row[7]})
    
    conn.close()
    return web.json_response({'tariffs': tariffs})


async def admin_add_tariff(request):
    """Добавить тариф"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    name = data.get('name')
    days = int(data.get('days', 30))
    price = float(data.get('price', 0))
    traffic_gb = int(data.get('traffic_gb', 10))
    devices = int(data.get('devices', 1))
    
    if not name or price <= 0:
        return web.json_response({'error': 'name and price required'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO tariffs (name, days, price, traffic_gb, devices, is_active) VALUES (?, ?, ?, ?, ?, 1)", (name, days, price, traffic_gb, devices))
    conn.commit()
    tariff_id = cursor.lastrowid
    conn.close()
    
    return web.json_response({'success': True, 'tariff_id': tariff_id})


async def admin_update_tariff(request):
    """Обновить тариф"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    tariff_id = int(data.get('tariff_id'))
    name = data.get('name')
    days = int(data.get('days', 30))
    price = float(data.get('price', 0))
    traffic_gb = int(data.get('traffic_gb', 10))
    devices = int(data.get('devices', 1))
    is_active = int(data.get('is_active', 1))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE tariffs SET name=?, days=?, price=?, traffic_gb=?, devices=?, is_active=? WHERE id = ?", (name, days, price, traffic_gb, devices, is_active, tariff_id))
    conn.commit()
    conn.close()
    
    return web.json_response({'success': True})


async def admin_delete_tariff(request):
    """Удалить тариф"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    tariff_id = int(data.get('tariff_id'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM tariffs WHERE id = ?", (tariff_id,))
    conn.commit()
    conn.close()
    
    return web.json_response({'success': True})


# === Рассылки ===
async def admin_broadcast(request):
    """Отправить рассылку"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    message = data.get('message')
    
    if not message:
        return web.json_response({'error': 'message required'}, status=400)
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, telegram_id FROM users WHERE telegram_id IS NOT NULL")
    users = cursor.fetchall()
    
    sent = 0
    failed = 0
    
    for user_id, telegram_id in users:
        try:
            await bot.send_message(telegram_id, message)
            sent += 1
        except Exception as e:
            logger.error(f"Ошибка отправки пользователю {telegram_id}: {e}")
            failed += 1
    
    conn.close()
    
    return web.json_response({'success': True, 'sent': sent, 'failed': failed})


async def admin_get_broadcasts(request):
    """История рассылок"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    return web.json_response({'broadcasts': []})


# === Действия с пользователями ===
async def admin_block_user(request):
    """Заблокировать пользователя"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    user_id = int(data.get('user_id'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_blocked = 1 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return web.json_response({'success': True})


async def admin_unblock_user(request):
    """Разблокировать пользователя"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    user_id = int(data.get('user_id'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET is_blocked = 0 WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return web.json_response({'success': True})


async def admin_delete_user(request):
    """Удалить пользователя"""
    admin_key = request.query.get('key')
    if admin_key != 'admin_secret_key_2026':
        return web.json_response({'error': 'unauthorized'}, status=401)
    
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    user_id = int(data.get('user_id'))
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subscriptions WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM payments WHERE user_id = ?", (user_id,))
    cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    return web.json_response({'success': True})


# === Админ авторизация ===
import hashlib
import secrets

ADMIN_USERS = {
    'admin': hashlib.sha256('admin123'.encode()).hexdigest(),
    'stanislav': hashlib.sha256('stanislav123'.encode()).hexdigest()
}

async def admin_login(request):
    """Логин через логин/пароль"""
    try:
        data = await request.post() if 'application/json' not in request.headers.get('Content-Type', '') else await request.json()
    except:
        data = await request.post()
    
    username = data.get('username', '')
    password = data.get('password', '')
    
    if username not in ADMIN_USERS:
        return web.json_response({'error': 'Invalid credentials'}, status=401)
    
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    if password_hash != ADMIN_USERS[username]:
        return web.json_response({'error': 'Invalid credentials'}, status=401)
    
    # Генерируем токен
    token = secrets.token_urlsafe(32)
    
    return web.json_response({
        'success': True,
        'token': token,
        'username': username
    })


async def admin_auth(request):
    """Проверка авторизации через Telegram"""
    telegram_id = request.query.get('telegram_id')
    init_data = request.query.get('init_data')
    
    # Проверяем через базу - только для админов
    conn = get_db()
    cursor = conn.cursor()
    
    # Проверяем, есть ли пользователь и является ли он админом (по ID или username)
    cursor.execute("SELECT id FROM users WHERE telegram_id = ?", (int(telegram_id) if telegram_id else 0,))
    user = cursor.fetchone()
    
    # Разрешаем доступ для определенных Telegram ID (добавь свои)
    ALLOWED_TG_IDS = [2056591682]  # Станислав
    
    if user or (telegram_id and int(telegram_id) in ALLOWED_TG_IDS):
        token = secrets.token_urlsafe(32)
        conn.close()
        return web.json_response({
            'success': True,
            'token': token,
            'telegram_id': telegram_id
        })
    
    conn.close()
    return web.json_response({'error': 'Access denied'}, status=403)


def setup_api_routes(app):
    """Настроить API маршруты"""
    app.router.add_get('/api/squads', get_squads)
    app.router.add_get('/api/subscription/servers', get_subscription_servers)
    app.router.add_post('/api/subscription/servers', update_subscription_servers)
    app.router.add_get('/api/subscription/addons-price', get_addons_price)
    app.router.add_post('/api/subscription/traffic', add_subscription_traffic)
    app.router.add_get('/api/subscription/traffic', get_subscription_traffic)
    app.router.add_post('/api/subscription/device', add_subscription_device)
    app.router.add_get('/api/user', get_user_data)
    app.router.add_get('/api/subscription/links', get_subscription_links)
    app.router.add_get('/api/subscription/payment', get_payment_url)
    app.router.add_post('/api/subscription/delete', delete_subscription)
    app.router.add_post('/api/subscription/create', create_subscription_api)
    app.router.add_post('/api/subscription/trial', create_trial_subscription)
    app.router.add_get('/api/subscription/renewal', get_renewal_options)
    app.router.add_post('/api/subscription/renew', renew_subscription)
    app.router.add_get('/api/payments', get_user_payments)
    app.router.add_get('/api/balance/topup', get_balance_topup)
    app.router.add_post('/api/subscription/pay', pay_with_balance)
    app.router.add_post('/api/notify/payment', notify_payment)
    # Реферальная система
    app.router.add_get('/api/referral', get_referral_info)
    app.router.add_post('/api/referral/register', register_referral)
    # Админ
    app.router.add_get('/api/admin/stats', admin_get_stats)
    app.router.add_get('/api/admin/users', admin_get_users)
    app.router.add_get('/api/admin/user', admin_get_user_detail)
    app.router.add_get('/api/admin/subscriptions', admin_get_subscriptions)
    app.router.add_get('/api/admin/payments', admin_get_payments)
    app.router.add_post('/api/admin/add_balance', admin_add_balance)
    
    # Серверы
    app.router.add_get('/api/admin/servers', admin_get_servers)
    app.router.add_post('/api/admin/server/add', admin_add_server)
    app.router.add_post('/api/admin/server/delete', admin_delete_server)
    app.router.add_post('/api/admin/server/toggle', admin_toggle_server)
    
    # Тарифы
    app.router.add_get('/api/admin/tariffs', admin_get_tariffs)
    app.router.add_post('/api/admin/tariff/add', admin_add_tariff)
    app.router.add_post('/api/admin/tariff/update', admin_update_tariff)
    app.router.add_post('/api/admin/tariff/delete', admin_delete_tariff)
    
    # Рассылки
    app.router.add_post('/api/admin/broadcast', admin_broadcast)
    app.router.add_get('/api/admin/broadcasts', admin_get_broadcasts)
    
    # Пользователи - действия
    app.router.add_post('/api/admin/user/block', admin_block_user)
    app.router.add_post('/api/admin/user/unblock', admin_unblock_user)
    app.router.add_post('/api/admin/user/delete', admin_delete_user)
    
    # Авторизация
    app.router.add_post('/api/admin/login', admin_login)
    app.router.add_get('/api/admin/auth', admin_auth)
    
    logger.info("✅ API routes настроены")
