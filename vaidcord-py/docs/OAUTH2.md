# OAuth2 в VaidCord

Полная поддержка OAuth2 для Discord с расширенными возможностями для self-hosted зеркал и тестирования.

## Основные возможности

- ✅ **Authorization Code Grant** - стандартный OAuth2 поток для веб-приложений
- ✅ **Implicit Grant** - упрощенный поток для браузерных приложений
- ✅ **Client Credentials Grant** - для тестирования и bot-only операций
- ✅ **Bot Authorization** - добавление бота в серверы
- ✅ **Webhook Authorization** - создание webhook'ов через OAuth2
- ✅ **User Authentication** - аутентификация пользователя (для self-hosted/mock серверов)
- ✅ **Token Management** - автоматическое обновление и отзыв токенов
- ✅ **Custom Endpoints** - поддержка кастомных OAuth2 endpoint'ов
- ✅ **Proxy Support** - работа через proxy
- ✅ **CSRF Protection** - безопасная генерация state параметра

## Быстрый старт

### 1. Базовая настройка

```python
from vaidcord import OAuth2Client, OAuth2Config, OAuth2Scope

config = OAuth2Config(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    redirect_uri="https://yourdomain.com/callback",
)

client = OAuth2Client(config)
```

### 2. Создание URL авторизации

```python
auth_url = client.build_authorization_url(
    response_type="code",
    scope=[OAuth2Scope.IDENTIFY, OAuth2Scope.GUILDS],
    state=client.generate_state(),  # CSRF защита
)

print(f"Authorize: {auth_url}")
```

### 3. Обмен кода на токен

```python
# После редиректа пользователя получаем code из query параметров
code = "code_from_redirect"

token = await client.exchange_code(code)
print(f"Access Token: {token.access_token}")
print(f"Refresh Token: {token.refresh_token}")
print(f"Expires in: {token.expires_in} seconds")
```

### 4. Обновление токена

```python
new_token = await client.refresh_access_token(token.refresh_token)
```

### 5. Отзыв токена

```python
await client.revoke_token(token.access_token)
```

## Продвинутые сценарии

### Авторизация бота

```python
from vaidcord import IntegrationType

auth_url = client.build_authorization_url(
    response_type="code",
    scope=[OAuth2Scope.BOT, OAuth2Scope.APPLICATIONS_COMMANDS],
    permissions=8,  # Administrator
    guild_id="123456789",  # Опционально: предвыбрать сервер
    integration_type=IntegrationType.GUILD_INSTALL,
)
```

### Client Credentials для тестирования

```python
token = await client.get_client_credentials_token(
    scope=[OAuth2Scope.IDENTIFY]
)
```

### User Authentication (Self-Hosted Only)

⚠️ **ВНИМАНИЕ**: Используйте ТОЛЬКО с self-hosted зеркалами Discord или mock-серверами!

```python
from vaidcord import UserAuthClient

config = OAuth2Config(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    redirect_uri="https://yourdomain.com/callback",
    base_url="https://your-selfhosted-discord.com/api",
)

user_client = UserAuthClient(
    config=config,
    username="user@example.com",
    password="secure_password",
)

# Логин с учетными данными (только для self-hosted!)
token = await user_client.login_with_credentials(
    username="user@example.com",
    password="secure_password",
    mfa_code="123456",  # Опционально
)

# Получение информации о пользователе
user_info = await user_client.get_current_user(token.access_token)

# Получение серверов пользователя
guilds = await user_client.get_user_guilds(token.access_token)

# Получение подключенных аккаунтов
connections = await user_client.get_user_connections(token.access_token)
```

### Кастомные OAuth2 endpoint'ы

Полезно для self-hosted зеркал Discord:

```python
config = OAuth2Config(
    client_id="selfhosted_client_id",
    client_secret="selfhosted_client_secret",
    redirect_uri="https://myapp.com/callback",
    base_url="https://discord.myserver.com/api",
    authorize_url="https://discord.myserver.com/oauth2/authorize",
    api_version="10",
)
```

### Работа с Proxy

```python
import aiohttp

proxy_auth = aiohttp.BasicAuth("proxy_user", "proxy_password")

config = OAuth2Config(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    redirect_uri="https://yourdomain.com/callback",
    proxy="http://proxy.example.com:8080",
    proxy_auth=proxy_auth,
)
```

## Доступные OAuth2 Scopes

| Scope | Описание |
|-------|----------|
| `IDENTIFY` | Информация о пользователе |
| `EMAIL` | Email пользователя |
| `GUILDS` | Список серверов пользователя |
| `GUILDS_JOIN` | Добавление пользователя на сервер |
| `GUILDS_MEMBERS_READ` | Информация о участнике в сервере |
| `BOT` | Добавление бота на сервер |
| `APPLICATIONS_COMMANDS` | Команды приложения |
| `WEBHOOK_INCOMING` | Создание webhook'ов |
| `CONNECTIONS` | Подключенные аккаунты |
| `MESSAGES_READ` | Чтение сообщений (RPC) |
| `VOICE` | Подключение к голосовым каналам |
| `RPC` | Управление локальным клиентом Discord |

[Полный список в документации Discord](https://discord.com/developers/docs/topics/oauth2#shared-resources-oauth2-scopes)

## Типы интеграции

```python
from vaidcord import IntegrationType

# Установка на сервер (по умолчанию)
IntegrationType.GUILD_INSTALL  # 0

# Установка на пользователя
IntegrationType.USER_INSTALL   # 1
```

## Prompt типы

```python
from vaidcord import PromptType

# Запросить повторное подтверждение
PromptType.CONSENT  # "consent"

# Пропустить экран авторизации если уже подтверждено
PromptType.NONE     # "none"
```

## Обработка ошибок

```python
from vaidcord import OAuth2Error

try:
    token = await client.exchange_code("invalid_code")
except OAuth2Error as e:
    print(f"Status: {e.status}")      # HTTP статус
    print(f"Code: {e.code}")          # Discord error code
    print(f"Message: {e.message}")    # Человекочитаемое сообщение
```

## Примеры использования

Смотрите [examples/oauth2_examples.py](examples/oauth2_examples.py) для полных примеров:

- Authorization Code Grant
- Bot Authorization
- Client Credentials
- User Authentication
- Token Refresh
- Token Revocation
- Custom OAuth2 Endpoint
- Webhook Authorization

## Безопасность

### State параметр

Всегда используйте `state` параметр для защиты от CSRF атак:

```python
state = client.generate_state()
auth_url = client.build_authorization_url(state=state)

# После редиректа проверьте state
params = client.parse_redirect_url(redirect_url)
assert params["state"] == state
```

### Хранение токенов

- Никогда не храните токены в коде
- Используйте безопасное хранилище (например, зашифрованную БД)
- Регулярно обновляйте токены используя refresh token
- Отозывайте токены при выходе пользователя

## Тестирование

Все компоненты OAuth2 покрыты тестами:

```bash
uv run pytest tests/test_oauth2.py -v
```

Тесты включают:
- Генерацию URL авторизации
- Управление токенами
- Парсинг redirect URI
- Работу с ошибками
- UserAuthClient функциональность

## Поддержка Python

VaidCord OAuth2 требует **Python 3.12+** и использует современные возможности языка:
- Type hints
- Async/await
- Dataclasses
- StrEnum (через Enum)

## Лицензия

VaidCord распространяется под лицензией MIT.
