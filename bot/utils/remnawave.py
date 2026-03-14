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
        is_disabled: bool = True
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
        
        try:
            body = CreateUserRequestDto(
                username=username,
                expire_at=expire_at.isoformat() + "Z",
                status=status,
                traffic_limit_bytes=traffic_limit_bytes,
                traffic_limit_strategy="NO_RESET",
                vless_uuid=vless_uuid,
                trojan_password=trojan_password,
                ss_password=ss_password,
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
    is_disabled: bool = True
) -> dict:
    """Создать VPN пользователя"""
    client = RemnaWaveClient()
    return await client.create_user(
        username=username,
        traffic_limit_bytes=traffic_limit_bytes,
        expire_days=expire_days,
        is_disabled=is_disabled
    )


async def enable_vpn_user(uuid: str):
    """Включить VPN пользователя"""
    client = RemnaWaveClient()
    await client.enable_user(uuid)


async def disable_vpn_user(uuid: str):
    """Выключить VPN пользователя"""
    client = RemnaWaveClient()
    await client.disable_user(uuid)


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


if __name__ == "__main__":
    async def test():
        client = RemnaWaveClient()
        nodes = await client.get_nodes()
        print(f"Нод найдено: {len(nodes)}")
        for node in nodes:
            print(f"  - {node.name} ({node.country_code})")
    
    asyncio.run(test())
