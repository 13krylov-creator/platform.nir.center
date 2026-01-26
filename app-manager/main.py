"""
App Manager API - Управление приложениями платформы
FastAPI backend для динамического добавления/редактирования приложений
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

# ============================================================================
# Configuration
# ============================================================================

APPS_JSON_PATH = os.environ.get("APPS_JSON_PATH", "/data/apps.json")
NGINX_CONF_DIR = os.environ.get("NGINX_CONF_DIR", "/nginx-conf")
NGINX_CONTAINER = os.environ.get("NGINX_CONTAINER", "iam-nginx")

# Базовый домен для формирования URL приложений
BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "nir.center")

# Предопределенные группы (из Keycloak)
AVAILABLE_GROUPS = ["admins", "app1-users"]

# Типы приложений
APP_TYPES = [
    {"value": "docker", "label": "Docker контейнер", "hint": "Приложение в Docker-сети iam-network"},
    {"value": "host", "label": "Хост-система", "hint": "Приложение на host.docker.internal"},
    {"value": "external", "label": "Внешний URL", "hint": "Приложение на другом сервере"}
]

# Статусы
APP_STATUSES = [
    {"value": "online", "label": "Онлайн"},
    {"value": "offline", "label": "Офлайн"},
    {"value": "maintenance", "label": "Техобслуживание"}
]

# Популярные иконки
POPULAR_ICONS = ["📊", "🚀", "⚙️", "📦", "🌐", "📈", "🔧", "💼", "📋", "🎯", "📁", "🔒"]

# ============================================================================
# Models
# ============================================================================

class AppCreate(BaseModel):
    """Модель для создания приложения"""
    id: str = Field(..., min_length=2, max_length=50, description="Уникальный ID (a-z, 0-9, -)")
    name: str = Field(..., min_length=2, max_length=100, description="Название приложения")
    description: str = Field(..., min_length=5, max_length=500, description="Описание")
    url: str = Field(..., description="URL приложения")
    icon: str = Field(default="📦", description="Эмодзи иконка")
    app_type: str = Field(default="docker", description="Тип: docker, host, external")
    port: Optional[int] = Field(default=None, ge=1, le=65535, description="Порт контейнера")
    status: str = Field(default="online", description="Статус: online, offline, maintenance")
    groups: list[str] = Field(default_factory=list, description="Группы доступа")
    adminOnly: bool = Field(default=False, description="Только для админов")
    createNginxConfig: bool = Field(default=False, description="Создать nginx конфигурацию")

    @field_validator('id')
    @classmethod
    def validate_id(cls, v: str) -> str:
        if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$', v):
            raise ValueError('ID должен содержать только a-z, 0-9, - и не начинаться/заканчиваться на -')
        return v

    @field_validator('app_type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        valid = [t["value"] for t in APP_TYPES]
        if v not in valid:
            raise ValueError(f'Тип должен быть одним из: {valid}')
        return v

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        valid = [s["value"] for s in APP_STATUSES]
        if v not in valid:
            raise ValueError(f'Статус должен быть одним из: {valid}')
        return v


class AppUpdate(BaseModel):
    """Модель для обновления приложения"""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    description: Optional[str] = Field(None, min_length=5, max_length=500)
    url: Optional[str] = None
    icon: Optional[str] = None
    app_type: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    status: Optional[str] = None
    groups: Optional[list[str]] = None
    adminOnly: Optional[bool] = None


class AppResponse(BaseModel):
    """Модель ответа с приложением"""
    id: str
    name: str
    description: str
    url: str
    icon: str
    groups: list[str]
    status: str
    adminOnly: bool = False
    app_type: str = "docker"
    port: Optional[int] = None
    createdAt: Optional[str] = None
    updatedAt: Optional[str] = None


# ============================================================================
# App initialization
# ============================================================================

app = FastAPI(
    title="App Manager API",
    description="API для управления приложениями платформы НИР-Центр",
    version="1.0.0"
)

# CORS для frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Helper functions
# ============================================================================

def load_apps() -> dict:
    """Загрузить apps.json"""
    try:
        with open(APPS_JSON_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {"apps": [], "adminGroups": ["admins"]}
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=500, detail=f"Ошибка парсинга apps.json: {e}")


def save_apps(data: dict) -> None:
    """Сохранить apps.json"""
    try:
        with open(APPS_JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сохранения apps.json: {e}")


def find_app_by_id(apps: list, app_id: str) -> tuple[int, dict] | tuple[None, None]:
    """Найти приложение по ID"""
    for i, app in enumerate(apps):
        if app.get("id") == app_id:
            return i, app
    return None, None


def generate_nginx_config(app_data: AppCreate) -> str:
    """Генерация nginx конфигурации для приложения"""
    
    # Определяем upstream
    if app_data.app_type == "docker":
        upstream = f"http://{app_data.id}"
        if app_data.port:
            upstream = f"http://{app_data.id}:{app_data.port}"
    elif app_data.app_type == "host":
        port = app_data.port or 8080
        upstream = f"http://host.docker.internal:{port}"
    else:
        upstream = app_data.url
    
    # Группы для RBAC
    groups_pattern = "|".join(app_data.groups) if app_data.groups else "admins"
    
    config = f'''# =============================================================================
# Приложение: {app_data.name}
# Создано автоматически: {datetime.now().isoformat()}
# =============================================================================

server {{
    listen 80;
    listen [::]:80;
    
    server_name {app_data.id}.localhost {app_data.id}.nir.center;
    
    access_log /var/log/nginx/{app_data.id}-access.log auth;
    error_log /var/log/nginx/{app_data.id}-error.log warn;
    
    # OAuth2-Proxy endpoints
    include /etc/nginx/snippets/oauth2-proxy.conf;
    
    # Основной location
    location / {{
        include /etc/nginx/snippets/auth.conf;
        
        # RBAC: доступ только для групп: {groups_pattern}
        # if ($auth_groups !~ "{groups_pattern}") {{
        #     return 403;
        # }}
        
        proxy_pass {upstream};
        include /etc/nginx/snippets/proxy-params.conf;
    }}
    
    # Health check
    location /health {{
        proxy_pass {upstream}/health;
        include /etc/nginx/snippets/proxy-params.conf;
        access_log off;
    }}
}}
'''
    return config


def reload_nginx() -> bool:
    """Перезагрузить nginx конфигурацию"""
    try:
        # Пробуем через docker exec
        result = subprocess.run(
            ["docker", "exec", NGINX_CONTAINER, "nginx", "-s", "reload"],
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Ошибка reload nginx: {e}")
        return False


def check_admin_access(x_auth_groups: str = Header(default="", alias="X-Auth-Groups")) -> bool:
    """Проверка доступа администратора"""
    if not x_auth_groups:
        raise HTTPException(status_code=403, detail="Доступ запрещен: отсутствует заголовок X-Auth-Groups")
    
    groups = [g.strip().replace("/", "") for g in x_auth_groups.split(",")]
    if "admins" not in groups:
        raise HTTPException(status_code=403, detail="Доступ запрещен: требуется группа admins")
    
    return True


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "app-manager"}


@app.get("/api/config")
async def get_config():
    """Получить конфигурацию для формы"""
    return {
        "groups": AVAILABLE_GROUPS,
        "types": APP_TYPES,
        "statuses": APP_STATUSES,
        "icons": POPULAR_ICONS
    }


@app.get("/api/apps")
async def list_apps():
    """Получить список всех приложений"""
    data = load_apps()
    return {"apps": data.get("apps", []), "total": len(data.get("apps", []))}


@app.get("/api/apps/{app_id}")
async def get_app(app_id: str):
    """Получить приложение по ID"""
    data = load_apps()
    _, app = find_app_by_id(data["apps"], app_id)
    
    if app is None:
        raise HTTPException(status_code=404, detail=f"Приложение '{app_id}' не найдено")
    
    return app


@app.post("/api/apps", status_code=201)
async def create_app(app_data: AppCreate, _: bool = Depends(check_admin_access)):
    """Создать новое приложение"""
    data = load_apps()
    
    # Проверка уникальности ID
    _, existing = find_app_by_id(data["apps"], app_data.id)
    if existing:
        raise HTTPException(status_code=409, detail=f"Приложение с ID '{app_data.id}' уже существует")
    
    # Создаем запись
    now = datetime.now().isoformat()
    
    # Формируем URL для отображения в браузере (красивый домен)
    # Если создается nginx конфигурация - используем домен, иначе оставляем введенный URL
    display_url = app_data.url
    if app_data.createNginxConfig:
        display_url = f"http://{app_data.id}.{BASE_DOMAIN}"
    
    new_app = {
        "id": app_data.id,
        "name": app_data.name,
        "description": app_data.description,
        "url": display_url,
        "internal_url": app_data.url,  # Сохраняем оригинальный URL для отладки
        "icon": app_data.icon,
        "groups": app_data.groups,
        "status": app_data.status,
        "adminOnly": app_data.adminOnly,
        "app_type": app_data.app_type,
        "port": app_data.port,
        "createdAt": now,
        "updatedAt": now
    }
    
    data["apps"].append(new_app)
    save_apps(data)
    
    # Создаем nginx конфигурацию если запрошено
    nginx_created = False
    if app_data.createNginxConfig:
        try:
            config_content = generate_nginx_config(app_data)
            config_path = Path(NGINX_CONF_DIR) / f"40-{app_data.id}.conf"
            config_path.write_text(config_content, encoding='utf-8')
            nginx_created = True
            
            # Перезагружаем nginx
            reload_nginx()
        except Exception as e:
            print(f"Ошибка создания nginx конфига: {e}")
    
    return {
        "message": "Приложение создано успешно",
        "app": new_app,
        "nginxConfigCreated": nginx_created
    }


@app.put("/api/apps/{app_id}")
async def update_app(app_id: str, update_data: AppUpdate, _: bool = Depends(check_admin_access)):
    """Обновить приложение"""
    data = load_apps()
    idx, app = find_app_by_id(data["apps"], app_id)
    
    if app is None:
        raise HTTPException(status_code=404, detail=f"Приложение '{app_id}' не найдено")
    
    # Обновляем только переданные поля
    update_dict = update_data.model_dump(exclude_unset=True)
    for key, value in update_dict.items():
        if value is not None:
            app[key] = value
    
    app["updatedAt"] = datetime.now().isoformat()
    data["apps"][idx] = app
    save_apps(data)
    
    return {"message": "Приложение обновлено", "app": app}


@app.delete("/api/apps/{app_id}")
async def delete_app(app_id: str, _: bool = Depends(check_admin_access)):
    """Удалить приложение"""
    data = load_apps()
    idx, app = find_app_by_id(data["apps"], app_id)
    
    if app is None:
        raise HTTPException(status_code=404, detail=f"Приложение '{app_id}' не найдено")
    
    # Удаляем из списка
    data["apps"].pop(idx)
    save_apps(data)
    
    # Удаляем nginx конфиг если есть
    config_path = Path(NGINX_CONF_DIR) / f"40-{app_id}.conf"
    if config_path.exists():
        config_path.unlink()
        reload_nginx()
    
    return {"message": f"Приложение '{app_id}' удалено"}


@app.post("/api/nginx/reload")
async def nginx_reload(_: bool = Depends(check_admin_access)):
    """Перезагрузить nginx"""
    success = reload_nginx()
    if success:
        return {"message": "Nginx перезагружен успешно"}
    else:
        raise HTTPException(status_code=500, detail="Ошибка перезагрузки nginx")


@app.get("/api/nginx/config/{app_id}")
async def preview_nginx_config(app_id: str):
    """Предпросмотр nginx конфигурации"""
    data = load_apps()
    _, app = find_app_by_id(data["apps"], app_id)
    
    if app is None:
        raise HTTPException(status_code=404, detail=f"Приложение '{app_id}' не найдено")
    
    # Создаем модель для генерации
    app_model = AppCreate(
        id=app["id"],
        name=app["name"],
        description=app["description"],
        url=app["url"],
        icon=app.get("icon", "📦"),
        app_type=app.get("app_type", "docker"),
        port=app.get("port"),
        status=app.get("status", "online"),
        groups=app.get("groups", []),
        adminOnly=app.get("adminOnly", False),
        createNginxConfig=False
    )
    
    config = generate_nginx_config(app_model)
    return {"config": config}


# ============================================================================
# Run
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
