# НИР-Центр — Руководство по развертыванию

## Содержание

1. [Обзор архитектуры](#обзор-архитектуры)
2. [Требования](#требования)
3. [Таблица портов](#таблица-портов)
4. [Развертывание на Windows (Dev)](#развертывание-на-windows-dev)
5. [Развертывание на Ubuntu (Prod)](#развертывание-на-ubuntu-prod)
6. [Настройка хостового Nginx](#настройка-хостового-nginx)
7. [Подключение приложений](#подключение-приложений)
8. [Управление пользователями](#управление-пользователями)
9. [Автозапуск через systemd](#автозапуск-через-systemd)
10. [Мониторинг и логирование](#мониторинг-и-логирование)
11. [Резервное копирование](#резервное-копирование)
12. [Устранение неполадок](#устранение-неполадок)

---

## Обзор архитектуры

```
┌─────────────────────────────────────────────────────────────────┐
│                        Пользователь                             │
│                    http://platform.nir.center                   │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Хостовой Nginx (Ubuntu :80/:443)                   │
│         /etc/nginx/sites-enabled/platform.nir.center            │
└─────────────────────────────┬───────────────────────────────────┘
                              │ proxy_pass :5056
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Docker: NGINX (Entry Point :5056)                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ auth_request → OAuth2-Proxy → Проверка сессии             │ │
│  └────────────────────────────────────────────────────────────┘ │
│         │                    │                    │             │
│         ▼                    ▼                    ▼             │
│   ┌──────────┐        ┌──────────┐        ┌──────────┐         │
│   │   App1   │        │   App2   │        │   AppN   │         │
│   │ (Docker) │        │  (Host)  │        │   ...    │         │
│   └──────────┘        └──────────┘        └──────────┘         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Docker: OAuth2-Proxy (:4180)                    │
│  • Проверяет cookie сессии                                     │
│  • Редиректит на Keycloak при отсутствии сессии                │
│  • Возвращает информацию о пользователе в заголовках           │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                 Docker: Keycloak (:5058)                        │
│  • OIDC Provider                                                │
│  • Управление пользователями и группами                        │
│  • Single Sign-On                                               │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│              Docker: PostgreSQL + Redis                         │
│  • Хранение данных Keycloak                                    │
│  • Хранение сессий OAuth2-Proxy                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Требования

### Windows (Development)

- Windows 10/11
- Docker Desktop для Windows
- Git с настройкой `core.autocrlf=input`

### Ubuntu (Production)

- Ubuntu 20.04 LTS или новее
- Минимум 4 GB RAM (рекомендуется 8 GB)
- Минимум 20 GB свободного места на диске
- Docker и Docker Compose v2
- Nginx (системный, для проксирования)

---

## Таблица портов

| Сервис | Внутренний порт | Внешний порт | Описание |
|--------|-----------------|--------------|----------|
| Nginx (Docker) | 80 | **5056** | HTTP Entry Point |
| Nginx (Docker) | 443 | **5057** | HTTPS Entry Point |
| Keycloak | 8080 | **5058** | Identity Provider |
| OAuth2-Proxy | 4180 | - | Internal only |
| PostgreSQL | 5432 | - | Internal only |
| Redis | 6379 | - | Internal only |

> **Примечание**: Порты 5056-5075 зарезервированы для платформы (20 портов).

---

## Развертывание на Windows (Dev)

### Шаг 1: Установка Docker Desktop

1. Скачайте Docker Desktop с [официального сайта](https://www.docker.com/products/docker-desktop/)
2. Установите и перезагрузите компьютер
3. Убедитесь, что Docker запущен (иконка в системном трее)

### Шаг 2: Настройка hosts файла

> ⚠️ **Обязательный шаг** для работы доменов на localhost

Откройте `C:\Windows\System32\drivers\etc\hosts` с правами администратора и добавьте:

```
# НИР-Центр Platform
127.0.0.1 platform.nir.center
127.0.0.1 auth.nir.center
127.0.0.1 app1.nir.center
127.0.0.1 app2.nir.center
127.0.0.1 localhost
127.0.0.1 auth.localhost
127.0.0.1 app1.localhost
127.0.0.1 app2.localhost
```

**PowerShell (от администратора):**
```powershell
$hosts = @"

# НИР-Центр Platform
127.0.0.1 platform.nir.center
127.0.0.1 auth.nir.center
127.0.0.1 app1.nir.center
127.0.0.1 app2.nir.center
"@
Add-Content -Path "C:\Windows\System32\drivers\etc\hosts" -Value $hosts
```

### Шаг 3: Клонирование и настройка

```powershell
# Клонируйте репозиторий
git clone <repository-url> iam-platform
cd iam-platform

# Скопируйте шаблон переменных окружения
copy env.example .env

# Отредактируйте .env под ваши настройки
notepad .env
```

### Шаг 4: Настройка .env для Dev

```env
ENV=dev
DOMAIN=platform.nir.center
HTTP_PORT=5056
HTTPS_PORT=5057
KEYCLOAK_PORT=5058
KEYCLOAK_EXTERNAL_URL=http://platform.nir.center:5058
COOKIE_SECURE=false
KC_START_MODE=start-dev
```

### Шаг 5: Запуск платформы

```powershell
# Запуск всех сервисов
docker compose up -d

# Просмотр логов
docker compose logs -f

# Проверка статуса
docker compose ps
```

### Шаг 6: Проверка работоспособности

1. **Портал платформы**: http://platform.nir.center:5056
   - Будет редирект на логин Keycloak
   - Тестовые пользователи: `admin/admin123`, `user1/user123`

2. **Keycloak Admin**: http://platform.nir.center:5058
   - Логин: `admin` / Пароль: из `.env`

3. **Демо-приложение**: http://app1.localhost:5056 (после добавления в hosts)

---

## Развертывание на Ubuntu (Prod)

### Шаг 1: Подготовка сервера

```bash
# Обновление системы
sudo apt update && sudo apt upgrade -y

# Установка необходимых пакетов
sudo apt install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    nginx
```

### Шаг 2: Установка Docker

```bash
# Добавление официального GPG ключа Docker
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Добавление репозитория
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Установка Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Добавление пользователя в группу docker
sudo usermod -aG docker $USER

# Перезайдите в систему для применения прав
```

### Шаг 3: Настройка hosts на сервере

```bash
# Добавьте записи в /etc/hosts
sudo tee -a /etc/hosts << EOF

# НИР-Центр Platform (локальные домены)
127.0.0.1 platform.nir.center
127.0.0.1 auth.nir.center
127.0.0.1 app1.nir.center
127.0.0.1 app2.nir.center
EOF
```

> **Для реального домена**: Настройте DNS A-записи, указывающие на IP сервера.

### Шаг 4: Перенос файлов с Windows

**Вариант A: Через Git**
```bash
git clone <repository-url> /opt/nir-platform
cd /opt/nir-platform
```

**Вариант B: Через SCP (с Windows)**
```powershell
scp -r C:\path\to\iam-platform user@ubuntu-server:/opt/nir-platform
```

### Шаг 5: Настройка .env для Production

```bash
cd /opt/nir-platform
cp env.example .env
nano .env
```

Измените следующие параметры:

```env
# Режим production
ENV=prod

# Домен (реальный или через hosts)
DOMAIN=platform.nir.center

# Порты
HTTP_PORT=5056
HTTPS_PORT=5057
KEYCLOAK_PORT=5058

# URL Keycloak (будет проксироваться через хостовой nginx)
# Для внутренней сети без SSL:
KEYCLOAK_EXTERNAL_URL=http://platform.nir.center:5058
# Для продакшена с SSL:
# KEYCLOAK_EXTERNAL_URL=https://auth.nir.center

# Cookie
COOKIE_SECURE=false  # true если используете HTTPS
COOKIE_DOMAIN=.nir.center

# Production режим Keycloak
KC_START_MODE=start

# ВАЖНО: Измените все пароли!
KEYCLOAK_ADMIN_PASSWORD=<strong-password>
KC_DB_PASSWORD=<strong-password>
POSTGRES_PASSWORD=<strong-password>
OAUTH2_CLIENT_SECRET=<strong-secret>
OAUTH2_COOKIE_SECRET=<32-byte-secret>
REDIS_PASSWORD=<strong-password>
```

### Шаг 6: Запуск платформы

```bash
cd /opt/nir-platform

# Запуск
docker compose up -d

# Проверка
docker compose ps
docker compose logs -f
```

---

## Настройка хостового Nginx

> **Важно**: Этот раздел для Ubuntu, где системный Nginx занимает порт 80.

### Шаг 1: Копирование конфигурации

```bash
# Скопируйте готовый конфиг
sudo cp /opt/nir-platform/HOST_NGINX_SITE.conf /etc/nginx/sites-available/platform.nir.center

# Создайте симлинк
sudo ln -s /etc/nginx/sites-available/platform.nir.center /etc/nginx/sites-enabled/

# Проверьте конфигурацию
sudo nginx -t

# Перезагрузите nginx
sudo systemctl reload nginx
```

### Шаг 2: Проверка

```bash
# Проверьте что nginx слушает порт 80
sudo ss -tlnp | grep :80

# Проверьте доступ к платформе
curl -I http://platform.nir.center
```

### Шаг 3: SSL с Let's Encrypt (опционально)

```bash
# Установка certbot
sudo apt install certbot python3-certbot-nginx

# Получение сертификатов
sudo certbot --nginx -d platform.nir.center -d auth.nir.center -d app1.nir.center

# Автообновление (уже настроено при установке certbot)
sudo systemctl enable certbot.timer
```

После получения SSL, обновите `.env`:
```env
COOKIE_SECURE=true
KEYCLOAK_EXTERNAL_URL=https://auth.nir.center
```

---

## Подключение приложений

### Приложение в Docker

1. **Добавьте сеть в docker-compose.yml приложения:**

```yaml
services:
  myapp:
    image: myapp:latest
    # НЕ открывайте порты наружу!
    expose:
      - "8080"
    networks:
      - iam-network

networks:
  iam-network:
    external: true
```

2. **Добавьте upstream в `nginx/conf.d/00-upstream.conf`:**

```nginx
upstream myapp {
    server myapp:8080;
    keepalive 32;
}
```

3. **Создайте конфигурацию `nginx/conf.d/35-myapp.conf`:**

```nginx
server {
    listen 80;
    server_name myapp.nir.center;
    
    include /etc/nginx/snippets/oauth2-proxy.conf;
    
    location / {
        include /etc/nginx/snippets/auth.conf;
        
        # RBAC: доступ только для определенных групп
        if ($auth_groups !~ "myapp-users|admins") {
            return 403;
        }
        
        proxy_pass http://myapp;
        include /etc/nginx/snippets/proxy-params.conf;
    }
}
```

4. **Перезагрузите nginx:**

```bash
docker compose exec nginx nginx -s reload
```

### Приложение на хосте (не в Docker)

1. **Создайте конфигурацию `nginx/conf.d/36-hostapp.conf`:**

```nginx
server {
    listen 80;
    server_name hostapp.nir.center;
    
    include /etc/nginx/snippets/oauth2-proxy.conf;
    
    location / {
        include /etc/nginx/snippets/auth.conf;
        
        # Проксирование на приложение на хосте
        # Windows: host.docker.internal
        # Linux: host.docker.internal (Docker 20.10+) или 172.17.0.1
        proxy_pass http://host.docker.internal:3000;
        include /etc/nginx/snippets/proxy-params.conf;
    }
}
```

---

## Управление пользователями

### Через Keycloak Admin Console

1. Откройте http://platform.nir.center:5058 (или через хостовой nginx)
2. Войдите как администратор
3. Выберите realm `platform`

#### Создание пользователя

1. Users → Add user
2. Заполните данные
3. Credentials → Set password
4. Groups → Join groups (выберите группы доступа)

#### Создание группы

1. Groups → New
2. Введите имя (например, `myapp-users`)

### Предустановленные пользователи

| Логин   | Пароль     | Группы                              |
|---------|------------|-------------------------------------|
| admin   | admin123   | admins, users                       |
| user1   | user123    | users, app1-users                   |
| user2   | user123    | users, app2-users                   |
| manager | manager123 | managers, users, app1-users, app2-users |

---

## Автозапуск через systemd

### Создание systemd сервиса

```bash
sudo tee /etc/systemd/system/nir-platform.service << 'EOF'
[Unit]
Description=НИР-Центр IAM Platform
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/nir-platform
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=300

[Install]
WantedBy=multi-user.target
EOF
```

### Включение автозапуска

```bash
# Перезагрузка конфигурации systemd
sudo systemctl daemon-reload

# Включение автозапуска
sudo systemctl enable nir-platform.service

# Управление сервисом
sudo systemctl start nir-platform
sudo systemctl stop nir-platform
sudo systemctl restart nir-platform
sudo systemctl status nir-platform
```

---

## Мониторинг и логирование

### Просмотр логов

```bash
# Все сервисы
docker compose logs -f

# Конкретный сервис
docker compose logs -f nginx
docker compose logs -f keycloak
docker compose logs -f oauth2-proxy

# Последние N строк
docker compose logs --tail 100 nginx
```

### Health Checks

```bash
# Статус всех сервисов
docker compose ps

# Проверка здоровья
curl -s http://localhost:5056/health || echo "nginx: OK or no /health endpoint"
curl -s http://localhost:5058/health/ready && echo "keycloak: OK"
```

### Настройка логирования Docker

```bash
# Создайте /etc/docker/daemon.json
sudo tee /etc/docker/daemon.json << 'EOF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "3"
  }
}
EOF

# Перезапустите Docker
sudo systemctl restart docker
```

### Мониторинг ресурсов

```bash
# Использование ресурсов контейнерами
docker stats

# Место на диске
docker system df
```

---

## Резервное копирование

### Скрипт резервного копирования

Создайте `/opt/nir-platform/backup.sh`:

```bash
#!/bin/bash
# =============================================================================
# НИР-Центр - Скрипт резервного копирования
# =============================================================================

BACKUP_DIR="/opt/backups/nir-platform"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_PATH="${BACKUP_DIR}/${DATE}"

mkdir -p "$BACKUP_PATH"

echo "=== Backup started at $(date) ==="

# 1. Backup PostgreSQL (Keycloak data)
echo "Backing up PostgreSQL..."
docker compose exec -T postgres pg_dump -U keycloak keycloak > "${BACKUP_PATH}/keycloak_db.sql"

# 2. Backup Redis (sessions)
echo "Backing up Redis..."
docker compose exec -T redis redis-cli BGSAVE
sleep 5
docker cp iam-redis:/data/dump.rdb "${BACKUP_PATH}/redis_dump.rdb" 2>/dev/null || echo "Redis backup skipped"

# 3. Backup конфигурации
echo "Backing up configuration..."
cp .env "${BACKUP_PATH}/.env"
cp -r nginx "${BACKUP_PATH}/nginx"
cp -r keycloak "${BACKUP_PATH}/keycloak"

# 4. Архивирование
echo "Creating archive..."
tar -czf "${BACKUP_DIR}/backup_${DATE}.tar.gz" -C "$BACKUP_PATH" .
rm -rf "$BACKUP_PATH"

# 5. Удаление старых бэкапов (старше 30 дней)
find "$BACKUP_DIR" -name "backup_*.tar.gz" -mtime +30 -delete

echo "=== Backup completed: ${BACKUP_DIR}/backup_${DATE}.tar.gz ==="
```

```bash
# Сделайте скрипт исполняемым
chmod +x /opt/nir-platform/backup.sh
```

### Автоматическое резервное копирование (cron)

```bash
# Добавьте в crontab
sudo crontab -e

# Ежедневный бэкап в 3:00
0 3 * * * /opt/nir-platform/backup.sh >> /var/log/nir-backup.log 2>&1
```

### Восстановление из бэкапа

```bash
# 1. Остановите платформу
docker compose down

# 2. Распакуйте бэкап
tar -xzf /opt/backups/nir-platform/backup_YYYYMMDD_HHMMSS.tar.gz -C /tmp/restore

# 3. Восстановите конфигурацию
cp /tmp/restore/.env .env
cp -r /tmp/restore/nginx ./
cp -r /tmp/restore/keycloak ./

# 4. Запустите платформу
docker compose up -d

# 5. Восстановите базу данных
docker compose exec -T postgres psql -U keycloak keycloak < /tmp/restore/keycloak_db.sql
```

---

## Устранение неполадок

### OAuth2-Proxy не запускается

```bash
# Проверьте логи
docker compose logs oauth2-proxy

# Частые причины:
# 1. Keycloak еще не готов - подождите 1-2 минуты
# 2. Неверный OAUTH2_CLIENT_SECRET
# 3. Невалидный OAUTH2_COOKIE_SECRET (должен быть 32 байта)
```

### Ошибка "invalid_redirect_uri" в Keycloak

1. Откройте Keycloak Admin Console
2. Clients → oauth2-proxy → Valid redirect URIs
3. Добавьте ваш домен: `http://platform.nir.center:5056/*`

### Приложение недоступно

```bash
# Проверьте сеть
docker network inspect iam-network

# Проверьте что контейнер в сети
docker inspect <container-name> | grep -A 20 Networks

# Проверьте nginx конфигурацию
docker compose exec nginx nginx -t
```

### "Bad Gateway" при доступе к приложению

```bash
# Проверьте что upstream доступен
docker compose exec nginx curl -I http://your-upstream:port

# Проверьте DNS имя контейнера в docker-compose
```

### Logout не работает

- Убедитесь что `post_logout_redirect_uri` добавлен в Keycloak клиент
- Проверьте что cookie удаляются при logout

### Сброс к начальному состоянию

```bash
# Остановка и удаление всего (ВНИМАНИЕ: удалит все данные!)
docker compose down -v

# Повторный запуск
docker compose up -d
```

---

## Полезные команды

```bash
# Статус сервисов
docker compose ps

# Логи всех сервисов
docker compose logs -f

# Логи конкретного сервиса
docker compose logs -f nginx

# Перезапуск сервиса
docker compose restart nginx

# Применение изменений nginx без перезапуска
docker compose exec nginx nginx -s reload

# Проверка конфигурации nginx
docker compose exec nginx nginx -t

# Вход в контейнер
docker compose exec nginx sh
docker compose exec keycloak bash

# Очистка неиспользуемых ресурсов
docker system prune -a

# Генерация безопасных секретов
openssl rand -base64 32  # Cookie secret
openssl rand -base64 24  # Пароли
```

---

## Чек-лист безопасности (Production)

- [ ] Все пароли изменены на надежные
- [ ] `COOKIE_SECURE=true` (если HTTPS)
- [ ] `KC_START_MODE=start` (не start-dev)
- [ ] SSL-сертификаты установлены
- [ ] Порт 5058 Keycloak закрыт извне (доступ только через nginx)
- [ ] Firewall настроен
- [ ] Бэкапы настроены и работают
- [ ] Мониторинг настроен
- [ ] Логи ротируются

---

## Контакты и поддержка

При возникновении проблем:
1. Проверьте логи: `docker compose logs -f`
2. Проверьте секцию "Устранение неполадок"
3. Создайте issue в репозитории проекта
