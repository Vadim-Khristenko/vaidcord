"""
Примеры использования OAuth2 модуля VaidCord.

Этот файл демонстрирует различные сценарии использования OAuth2:
- Авторизация через Authorization Code Grant
- Client Credentials для тестирования
- User Authentication для self-hosted зеркал
- Работа с токенами и их обновление
"""

from __future__ import annotations

import asyncio
from vaidcord.oauth2 import (
    OAuth2Client,
    UserAuthClient,
    OAuth2Config,
    OAuth2Scope,
    IntegrationType,
    PromptType,
)


async def example_authorization_code_grant():
    """
    Пример использования Authorization Code Grant.
    
    Это стандартный OAuth2 поток для веб-приложений.
    """
    print("=== Authorization Code Grant ===\n")
    
    # 1. Создаем конфигурацию
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://yourdomain.com/callback",
    )
    
    # 2. Создаем OAuth2 клиент
    client = OAuth2Client(config)
    
    # 3. Генерируем URL для авторизации
    auth_url = client.build_authorization_url(
        response_type="code",
        scope=[OAuth2Scope.IDENTIFY, OAuth2Scope.GUILDS],
        state=client.generate_state(),  # CSRF защита
    )
    
    print(f"URL для авторизации: {auth_url}")
    print("\nПеренаправьте пользователя на этот URL.")
    print("После авторизации пользователь будет перенаправлен на redirect_uri с code параметром.\n")
    
    # 4. После получения кода из redirect URI:
    # code = "полученный_код"
    # token = await client.exchange_code(code)
    # print(f"Access token: {token.access_token}")
    
    await client.close()


async def example_bot_authorization():
    """
    Пример авторизации бота в сервере.
    """
    print("=== Bot Authorization ===\n")
    
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://yourdomain.com/callback",
    )
    
    client = OAuth2Client(config)
    
    # Создаем URL для добавления бота в сервер
    auth_url = client.build_authorization_url(
        response_type="code",
        scope=[OAuth2Scope.BOT, OAuth2Scope.APPLICATIONS_COMMANDS],
        permissions=8,  # Administrator permission
        guild_id="123456789012345678",  # Опционально: предвыбрать сервер
        integration_type=IntegrationType.GUILD_INSTALL,
    )
    
    print(f"URL для добавления бота: {auth_url}\n")
    
    await client.close()


async def example_client_credentials():
    """
    Пример использования Client Credentials Grant.
    
    Подходит для тестирования и операций только от имени бота.
    """
    print("=== Client Credentials Grant ===\n")
    
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://yourdomain.com/callback",
    )
    
    client = OAuth2Client(config)
    
    try:
        # Получаем токен без участия пользователя
        token = await client.get_client_credentials_token(
            scope=[OAuth2Scope.IDENTIFY]
        )
        
        print(f"Access token: {token.access_token}")
        print(f"Expires in: {token.expires_in} seconds")
        print(f"Scope: {' '.join(token.scope)}\n")
        
        # Используем токен для API запросов
        # auth_info = await client.get_current_authorization(token.access_token)
        
    except Exception as e:
        print(f"Ошибка: {e}\n")
    finally:
        await client.close()


async def example_user_authentication():
    """
    Пример аутентификации пользователя.
    
    ВНИМАНИЕ: Используйте ТОЛЬКО с self-hosted зеркалами Discord
    или mock-серверами для тестирования.
    
    Использование на официальном Discord API нарушает ToS!
    """
    print("=== User Authentication (Self-Hosted Only) ===\n")
    
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://yourdomain.com/callback",
        base_url="https://your-selfhosted-discord.com/api",  # Self-hosted сервер
    )
    
    client = UserAuthClient(
        config=config,
        username="user@example.com",
        password="secure_password",
    )
    
    try:
        # Логин с учетными данными (только для self-hosted!)
        token = await client.login_with_credentials(
            username="user@example.com",
            password="secure_password",
            mfa_code="123456",  # Опционально: 2FA код
        )
        
        print(f"User access token: {token.access_token}")
        
        # Получаем информацию о пользователе
        # user_info = await client.get_current_user(token.access_token)
        # print(f"Username: {user_info.get('username')}")
        
        # Получаем сервера пользователя
        # guilds = await client.get_user_guilds(token.access_token)
        
    except Exception as e:
        print(f"Ошибка: {e}\n")
    finally:
        await client.close()


async def example_token_refresh():
    """
    Пример обновления токена.
    """
    print("=== Token Refresh ===\n")
    
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://yourdomain.com/callback",
    )
    
    client = OAuth2Client(config)
    
    try:
        # Предположим, у нас есть refresh token
        refresh_token = "your_refresh_token_here"
        
        # Обновляем access token
        new_token = await client.refresh_access_token(refresh_token)
        
        print(f"New access token: {new_token.access_token}")
        print(f"New refresh token: {new_token.refresh_token}")
        print(f"Expires in: {new_token.expires_in} seconds\n")
        
    except Exception as e:
        print(f"Ошибка при обновлении токена: {e}\n")
    finally:
        await client.close()


async def example_token_revocation():
    """
    Пример отзыва токена.
    """
    print("=== Token Revocation ===\n")
    
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://yourdomain.com/callback",
    )
    
    client = OAuth2Client(config)
    
    try:
        access_token = "token_to_revoke"
        
        # Отзываем токен
        await client.revoke_token(
            token=access_token,
            token_type_hint="access_token",
        )
        
        print("Token successfully revoked!\n")
        
    except Exception as e:
        print(f"Ошибка при отзыве токена: {e}\n")
    finally:
        await client.close()


async def example_custom_oauth2_endpoint():
    """
    Пример использования кастомного OAuth2 endpoint.
    
    Полезно для self-hosted зеркал Discord или mock-серверов.
    """
    print("=== Custom OAuth2 Endpoint ===\n")
    
    # Конфигурация для self-hosted Discord сервера
    config = OAuth2Config(
        client_id="selfhosted_client_id",
        client_secret="selfhosted_client_secret",
        redirect_uri="https://myapp.com/callback",
        base_url="https://discord.myserver.com/api",
        authorize_url="https://discord.myserver.com/oauth2/authorize",
        api_version="10",
    )
    
    client = OAuth2Client(config)
    
    auth_url = client.build_authorization_url(
        response_type="code",
        scope=[OAuth2Scope.IDENTIFY],
    )
    
    print(f"Custom auth URL: {auth_url}")
    print(f"Token endpoint: {config.token_url}")
    print(f"Revoke endpoint: {config.revoke_url}\n")
    
    await client.close()


async def example_webhook_authorization():
    """
    Пример авторизации webhook.
    """
    print("=== Webhook Authorization ===\n")
    
    config = OAuth2Config(
        client_id="YOUR_CLIENT_ID",
        client_secret="YOUR_CLIENT_SECRET",
        redirect_uri="https://yourdomain.com/callback",
    )
    
    client = OAuth2Client(config)
    
    # Создаем URL для создания webhook
    auth_url = client.build_authorization_url(
        response_type="code",
        scope=[OAuth2Scope.WEBHOOK_INCOMING],
    )
    
    print(f"Webhook authorization URL: {auth_url}\n")
    print("After authorization, you'll receive webhook.id and webhook.token\n")
    
    await client.close()


async def main():
    """Запуск всех примеров."""
    print("=" * 60)
    print("VaidCord OAuth2 Examples")
    print("=" * 60 + "\n")
    
    # Запускаем примеры
    # Раскомментируйте нужный пример
    
    # await example_authorization_code_grant()
    # await example_bot_authorization()
    # await example_client_credentials()
    # await example_user_authentication()
    # await example_token_refresh()
    # await example_token_revocation()
    # await example_custom_oauth2_endpoint()
    # await example_webhook_authorization()
    
    print("Выберите пример для запуска, раскомментировав его в функции main().")


if __name__ == "__main__":
    asyncio.run(main())
