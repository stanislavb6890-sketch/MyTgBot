"""Работа с RemnaWave API"""
import asyncio
from typing import Optional, List
from remnawave import RemnawaveSDK
from config import REMNAWAVE_URL, REMNAWAVE_TOKEN
import random
import string


class RemnaWaveClient:
    def __init__(self):
        self.sdk = RemnawaveSDK(base_url=REMNAWAVE_URL, token=REMNAWAVE_TOKEN)
    
    def _generate_uuid(self) -> str:
        """Генерация UUID v4"""
        import uuid
        return str(uuid.uuid4())
    
    def _generate_password(self, length: int = 16) -> str:
        """Генерация пароля"""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))
    
    async def get_nodes(self):
        """Получить все ноды"""
        response = await self.sdk.nodes.get_all_nodes()
        return response.root
    
    async def get_squads(self):
        """Получить все внутренние сквады"""
        response = await self.sdk.internal_squads.get_internal_squads()
        return response.internal_squads
    
    async def add_user_to_squads(self, user_uuid: str, squad_uuids: List[str]):
        """Добавить пользователя в сквады"""
        from remnawave.models import UpdateUserRequestDto
        
        body = UpdateUserRequestDto(
            uuid=user_uuid,
            active_internal_squads=squad_uuids
        )
        await self.sdk.users.update_user(body=body)
        """Найти ноду по имени"""
        nodes = await self.get_nodes()
        for node in nodes:
            if name.lower() in node.name.lower():
                return node
        return None
    
    async def create_user(
        self,
        username: str,
        traffic_limit_bytes: int = 10 * 1024 * 1024 * 1024,
        expire_days: int = 30,
        is_disabled: bool = True,
        telegram_id: int = None,
        traffic_reset: str = "NO_RESET",
        devices_limit: int = 1
    ) -> dict:
        """Создать пользователя (выключен по умолчанию)"""
        from datetime import datetime, timedelta
        from remnawave.models import CreateUserRequestDto
        
        expire_at = datetime.now() + timedelta(days=expire_days)
        
        # Генерируем пароли и UUID
        vless_uuid = self._generate_uuid()
        trojan_password = self._generate_password()
        ss_password = self._generate_password()
        
        status = "DISABLED" if is_disabled else "ACTIVE"
        
        # Валидация стратегии сброса
        valid_strategies = ["NO_RESET", "DAY", "WEEK", "MONTH"]
        if traffic_reset not in valid_strategies:
            traffic_reset = "NO_RESET"
        
        try:
            body = CreateUserRequestDto(
                username=username,
                expire_at=expire_at.isoformat() + "Z",
                status=status,
                traffic_limit_bytes=traffic_limit_bytes,
                traffic_limit_strategy=traffic_reset,
                hwid_device_limit=devices_limit,
                vless_uuid=vless_uuid,
                trojan_password=trojan_password,
                ss_password=ss_password,
                telegram_id=telegram_id,
            )
            
            response = await self.sdk.users.create_user(body=body)
            user_data = response
            
            return {
                "uuid": str(user_data.uuid),
                "short_uuid": user_data.short_uuid,
                "username": user_data.username,
                "vless_uuid": str(vless_uuid),
                "trojan_password": trojan_password,
                "ss_password": ss_password,
                "subscription_url": user_data.subscription_url,
            }
        except Exception as e:
            print(f"Error creating user: {e}")
            raise
    
    async def enable_user(self, uuid: str):
        """Включить пользователя"""
        await self.sdk.users.enable_user(uuid=uuid)
    
    async def disable_user(self, uuid: str):
        """Выключить пользователя"""
        await self.sdk.users.disable_user(uuid=uuid)
    
    async def delete_user(self, uuid: str):
        """Удалить пользователя"""
        await self.sdk.users.delete_user(uuid=uuid)
    
    async def get_user(self, uuid: str):
        """Получить пользователя по UUID"""
        response = await self.sdk.users.get_user_by_uuid(uuid=uuid)
        return response.root
    
    async def reset_user_traffic(self, uuid: str):
        """Сбросить трафик пользователя"""
        await self.sdk.users.reset_user_traffic(uuid=uuid)
    
    async def update_user(
        self,
        uuid: str,
        traffic_limit_bytes: int = None,
        expire_at: str = None,
        is_disabled: bool = None
    ):
        """Обновить пользователя"""
        await self.sdk.users.update_user(
            uuid=uuid,
            traffic_limit_bytes=traffic_limit_bytes,
            expire_at=expire_at,
            is_disabled=is_disabled,
            traffic_limit_strategy="NO_RESET",
        )
    
    async def get_subscription_links(self, uuid: str):
        """Получить ссылки подписки"""
        user = await self.get_user(uuid)
        return {
            "subscription_url": user.subscription_url,
            "vless_uuid": user.vless_uuid,
            "trojan_password": user.trojan_password,
            "ss_password": user.ss_password,
        }


# Синхронная обёртка для удобства
def get_client() -> RemnaWaveClient:
    return RemnaWaveClient()


# === Основные функции ===

async def create_vpn_user(
    username: str,
    traffic_limit_bytes: int,
    expire_days: int,
    is_disabled: bool = True,
    telegram_id: int = None,
    traffic_reset: str = "NO_RESET",
    devices_limit: int = 1
) -> dict:
    """Создать VPN пользователя"""
    client = RemnaWaveClient()
    return await client.create_user(
        username=username,
        traffic_limit_bytes=traffic_limit_bytes,
        expire_days=expire_days,
        is_disabled=is_disabled,
        telegram_id=telegram_id,
        traffic_reset=traffic_reset,
        devices_limit=devices_limit
    )


async def enable_vpn_user(uuid: str):
    """Включить VPN пользователя"""
    client = RemnaWaveClient()
    await client.enable_user(uuid)


async def disable_vpn_user(uuid: str):
    """Выключить VPN пользователя"""
    client = RemnaWaveClient()
    await client.disable_user(uuid)


async def update_vpn_user(
    uuid: str,
    expire_days: int = None,
    traffic_limit_bytes: int = None,
    traffic_reset: str = "MONTH",
    devices_limit: int = None
):
    """Обновить параметры VPN пользователя"""
    from datetime import datetime, timedelta
    
    client = RemnaWaveClient()
    
    # Маппинг traffic_reset на стратегию RemnaWave
    reset_strategy_map = {
        'NO_RESET': 'NO_RESET',
        'DAY': 'DAY',
        'WEEK': 'WEEK',
        'MONTH': 'MONTH',
        'no_reset': 'NO_RESET',
        'daily': 'DAY',
        'weekly': 'WEEK',
        'monthly': 'MONTH'
    }
    reset_strategy = reset_strategy_map.get(traffic_reset.upper() if traffic_reset else 'MONTH', 'MONTH')
    
    # Вычисляем expire_at если переданы дни
    expire_at = None
    if expire_days:
        expire_at = (datetime.now() + timedelta(days=expire_days)).isoformat()
    
    await client.update_user(
        uuid=uuid,
        traffic_limit_bytes=traffic_limit_bytes,
        expire_at=expire_at,
        traffic_limit_strategy=reset_strategy
    )


async def get_all_nodes() -> list:
    """Получить все ноды"""
    client = RemnaWaveClient()
    return await client.get_nodes()


async def get_all_squads() -> list:
    """Получить все сквады"""
    client = RemnaWaveClient()
    return await client.get_squads()


async def add_user_to_squads(user_uuid: str, squad_uuids: list):
    """Добавить пользователя в сквады"""
    client = RemnaWaveClient()
    await client.add_user_to_squads(user_uuid, squad_uuids)


async def get_subscription_links(uuid: str) -> dict:
    """Получить ссылки подписки пользователя"""
    client = RemnaWaveClient()
    return await client.get_subscription_links(uuid)


def delete_vpn_user(uuid: str) -> bool:
    """Удалить VPN пользователя (синхронная обёртка)"""
    # Проверяем защищённых пользователей
    try:
        from protected_users import PROTECTED_USERS
        
        # Получаем username по uuid через SDK
        import asyncio
        async def _check_protected():
            from config import REMNAWAVE_URL, REMNAWAVE_TOKEN
            from remnawave import RemnawaveSDK
            sdk = RemnawaveSDK(base_url=REMNAWAVE_URL, token=REMNAWAVE_TOKEN)
            return await sdk.users.get_user_by_uuid(uuid=uuid)
        
        try:
            user = asyncio.run(_check_protected())
            if user and user.username in PROTECTED_USERS:
                print(f"⛔ Удаление ЗАПРЕЩЕНО для защищённого пользователя: {user.username}")
                return False
        except Exception as e:
            print(f"Ошибка проверки защиты: {e}")
            pass
    except ImportError:
        pass
    
    try:
        # Создаём новый event loop для удаления
        import asyncio
        
        async def _delete():
            client = RemnaWaveClient()
            await client.delete_user(uuid)
        
        # Пробуем использовать новый loop
        try:
            loop = asyncio.get_running_loop()
            # Если уже есть запущенный loop - создаём задачу
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, _delete())
                return future.result()
        except RuntimeError:
            # Нет запущенного loop - используем asyncio.run
            asyncio.run(_delete())
            return True
    except Exception as e:
        err_str = str(e)
        # Если пользователь уже удалён - тоже ок
        if "not found" in err_str.lower() or "A025" in err_str:
            return True
        print(f"Error deleting user: {e}")
        return False


if __name__ == "__main__":
    async def test():
        client = RemnaWaveClient()
        nodes = await client.get_nodes()
        print(f"Нод найдено: {len(nodes)}")
        for node in nodes:
            print(f"  - {node.name} ({node.country_code})")
    
    asyncio.run(test())
