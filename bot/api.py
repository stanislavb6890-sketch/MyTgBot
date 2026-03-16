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
               s.price, GROUP_CONCAT(ss.node_name, ', ') as servers
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
            'servers_list': row[11] or ''
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


async def create_subscription_api(request):
    """Создать подписку из Mini App"""
    import asyncio
    import uuid as uuid_module
    
    telegram_id = request.query.get('telegram_id') or request.query.get('user_id')
    days = int(request.query.get('days', '30'))
    traffic = int(request.query.get('traffic', '10'))
    devices = int(request.query.get('devices', '1'))
    servers_param = request.query.get('servers', '')
    servers = servers_param.split(',') if servers_param else []
    
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
    # 4.5₽ × дни + 2₽ × GB + 25₽ × устройства + 45₽ × серверы
    servers_count = len(servers)
    base_price = days * 4.5 + traffic * 2 + devices * 25 + servers_count * 45
    
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
        vpn_user = await create_vpn_user(
            username=vpn_username,
            traffic_limit_bytes=traffic * (1024**3),
            expire_days=days,
            is_disabled=True,
            telegram_id=telegram_id,
            traffic_reset=traffic_reset,
            devices_limit=devices
        )
        sub_uuid = vpn_user["uuid"]
        
        # Добавляем пользователя в выбранные сквады
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
                squad_uuids = []
                for server_code in servers:
                    if server_code in country_to_uuid:
                        squad_uuids.append(country_to_uuid[server_code])
                
                # Добавляем пользователя в сквады
                if squad_uuids:
                    for squad_uuid in squad_uuids:
                        try:
                            # Используем прямой HTTP вызов
                            response = await sdk.internal_squads.client.request(
                                method='POST',
                                url=f'/internal-squads/{squad_uuid}/bulk-actions/add-users',
                                json={'userUuids': [vpn_user["uuid"]]}
                            )
                            if response.status_code != 200:
                                logger.error(f"Ошибка добавления в сквад {squad_uuid}: {response.text}")
                        except Exception as sq_e:
                            logger.error(f"Ошибка добавления в сквад {squad_uuid}: {sq_e}")
                    logger.info(f"✅ Пользователь {vpn_username} добавлен в сквады: {squad_uuids}")
            except Exception as e:
                logger.error(f"Ошибка добавления в сквады: {e}")
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
        # Создаём VPN пользователя (сразу активен)
        vpn_user = await create_vpn_user(
            username=vpn_username,
            traffic_limit_bytes=TRIAL_TRAFFIC * (1024**3),
            expire_days=TRIAL_DAYS,
            is_disabled=False,  # Сразу активен
            telegram_id=telegram_id,
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
    from config import YOOMONEY_WALLET
    label = f"topup_{user_id}_{amount}"
    
    payment_url = f"https://yoomoney.ru/quickpay/confirm?receiver={YOOMONEY_WALLET}&quickpay-form=button&paymentType=AC&sum={amount}&label={label}"
    
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
            # Используем синхронный подход для aiohttp
            import subprocess
            result = subprocess.run(
                ['python3', '-c', f'''
import asyncio
from bot.utils.remnawave import enable_vpn_user, add_user_to_squads
import asyncio
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
        from bot.main import bot
        await bot.send_message(
            telegram_id,
            f"✅ <b>Подписка оплачена!</b>\n\n"
            f"💰 Списано: {price}₽\n\n"
            f"Можете использовать VPN!"
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
               GROUP_CONCAT(ss.node_name) as servers
        FROM subscriptions s
        LEFT JOIN subscription_servers ss ON s.id = ss.subscription_id
        GROUP BY s.id
        ORDER BY s.id DESC
        LIMIT 100
    """)
    
    subs = []
    for row in cursor.fetchall():
        subs.append({
            'id': row[0],
            'user_id': row[1],
            'status': row[2],
            'is_paid': bool(row[3]),
            'price': row[4],
            'expires_at': row[5],
            'created_at': row[6],
            'servers_list': row[7]
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
            from bot.utils.notifications import notify_balance_topup
            asyncio.create_task(notify_balance_topup(telegram_id, amount, new_balance))
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления: {e}")
    
    return web.json_response({
        'success': True,
        'user_id': user_id,
        'amount_added': amount,
        'new_balance': new_balance
    })


def setup_api_routes(app):
    """Настроить API маршруты"""
    app.router.add_get('/api/squads', get_squads)
    app.router.add_get('/api/subscription/servers', get_subscription_servers)
    app.router.add_post('/api/subscription/servers', update_subscription_servers)
    app.router.add_get('/api/subscription/addons-price', get_addons_price)
    app.router.add_post('/api/subscription/traffic', add_subscription_traffic)
    app.router.add_post('/api/subscription/device', add_subscription_device)
    app.router.add_get('/api/user', get_user_data)
    app.router.add_get('/api/subscription/links', get_subscription_links)
    app.router.add_get('/api/subscription/payment', get_payment_url)
    app.router.add_post('/api/subscription/delete', delete_subscription)
    app.router.add_post('/api/subscription/create', create_subscription_api)
    app.router.add_post('/api/subscription/trial', create_trial_subscription)
    app.router.add_get('/api/subscription/renewal', get_renewal_options)
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
    app.router.add_get('/api/admin/subscriptions', admin_get_subscriptions)
    app.router.add_get('/api/admin/payments', admin_get_payments)
    app.router.add_post('/api/admin/add_balance', admin_add_balance)
    logger.info("✅ API routes настроены")
