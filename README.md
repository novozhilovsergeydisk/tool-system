# Tool System

## Развертывание

### Предварительные требования
- Сервер с Ubuntu/Debian или аналогичной ОС
- Python 3.8+
- PostgreSQL
- Nginx
- Virtualenv
- Git
- WSGI-сервер (рекомендуется Gunicorn)
- Supervisor (для управления процессами)
- Certbot (для SSL)

### Подробные шаги развертывания
Предполагается, что приложение развертывается в папке `/var/www/tool-system`.

1. **Установка предварительных пакетов:**
   ```
   sudo apt update
   sudo apt install python3 python3-venv python3-pip postgresql postgresql-contrib nginx git supervisor certbot python3-certbot-nginx
   ```

2. **Клонирование репозитория:**
   ```
   sudo mkdir -p /var/www
   sudo chown -R $USER:$USER /var/www
   git clone git@github.com:novozhilovsergeydisk/tool-system.git /var/www/tool-system
   cd /var/www/tool-system
   ```

3. **Настройка виртуального окружения:**
   ```
   python3 -m venv venv
   source venv/bin/activate
   ```

4. **Установка зависимостей:**
   ```
   pip install -r requirements.txt
   pip install gunicorn
   ```

5. **Настройка базы данных:**
   Создайте пользователя и базу данных PostgreSQL:
   ```
   sudo -u postgres psql
   CREATE USER tool_user WITH PASSWORD 'your-password';
   CREATE DATABASE tool_system OWNER tool_user;
   GRANT ALL PRIVILEGES ON DATABASE tool_system TO tool_user;
   \q
   ```
   Выполните миграции для создания таблиц:
   ```
   python manage.py migrate
   python manage.py collectstatic --noinput
   ```

6. **Запуск приложения с Gunicorn:**
   ```
   gunicorn config.wsgi:application --bind 0.0.0.0:3001 --workers 3
   ```
   Для продакшена используйте Supervisor для управления.

7. **Настройка Nginx:**
   Создайте файл `/etc/nginx/sites-available/tool-system`:
   ```
   server {
       listen 80;
       server_name your_domain.com;

       location / {
           proxy_pass http://127.0.0.1:3001;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       location /static/ {
           alias /var/www/tool-system/static/;
       }
   }
   ```
   Включите сайт:
   ```
   sudo ln -s /etc/nginx/sites-available/tool-system /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

8. **Настройка systemd unit для Gunicorn (альтернатива Supervisor):**
   Создайте файл `/etc/systemd/system/tool-system.service`:
   ```
   [Unit]
   Description=Tool System Django App
   After=network.target

   [Service]
   User=www-data
   Group=www-data
   WorkingDirectory=/var/www/tool-system
   Environment="PATH=/var/www/tool-system/venv/bin"
   ExecStart=/var/www/tool-system/venv/bin/gunicorn config.wsgi:application --bind 0.0.0.0:3001 --workers 3
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```
   Включите и запустите сервис:
   ```
   sudo systemctl daemon-reload
   sudo systemctl enable tool-system
   sudo systemctl start tool-system
   sudo systemctl status tool-system
   ```

   Или используйте Supervisor, как описано выше.

9. **Настройка SSL с Let's Encrypt:**
   ```
   sudo certbot --nginx -d your_domain.com
   ```

10. **Тестирование:**
    Проверьте доступность сайта по HTTP и HTTPS, убедитесь, что приложение работает.

## Обновление приложения

При изменении моделей или кода выполните следующие шаги на сервере:

1. **Обновите код:**
    ```
    cd /var/www/tool-system
    git pull origin main
    ```

2. **Активируйте виртуальное окружение:**
    ```
    source venv/bin/activate
    ```

3. **Обновите зависимости:**
    ```
    pip install -r requirements.txt
    ```

4. **Если модели изменились, создайте и примените миграции:**
    ```
    python manage.py makemigrations
    python manage.py migrate
    ```

5. **Соберите статические файлы:**
    ```
    python manage.py collectstatic --noinput
    ```

6. **Перезапустите Gunicorn:**
    ```
    sudo systemctl restart tool-system
    ```

7. **Если нужно создать нового суперпользователя (админа):**
    ```
    python manage.py createsuperuser
    ```

### Настройка виртуального окружения
1. Создайте виртуальное окружение:
   ```
   python -m venv venv
   ```

2. Активируйте виртуальное окружение:
   ```
   source venv/bin/activate
   ```

3. Установите зависимости (предполагая, что requirements.txt существует):
   ```
   pip install -r requirements.txt
   ```

### Настройка базы данных
1. Убедитесь, что PostgreSQL установлен и запущен.

2. Создайте пользователя и базу данных (если не сделали ранее):
   ```
   sudo -u postgres psql
   CREATE USER tool_user WITH PASSWORD 'your-password';
   CREATE DATABASE tool_system OWNER tool_user;
   GRANT ALL PRIVILEGES ON DATABASE tool_system TO tool_user;
   \q
   ```

3. Выполните миграции:
   ```
   python manage.py migrate
   ```

4. Соберите статические файлы:
    ```
    python manage.py collectstatic --noinput
    ```
    
## Локальная разработка

1. Создайте файл .env в корне проекта и добавьте переменные окружения:
    ```
    SECRET_KEY=your-secret-key
    DEBUG=True
    ALLOWED_HOSTS=localhost,127.0.0.1
    DB_NAME=tool_system
    DB_USER=tool_user
    DB_PASSWORD=your-password
    DB_HOST=localhost
    DB_PORT=5432
    ```

2. Создайте виртуальное окружение:
    ```
    python3 -m venv venv
    ```

3. Активируйте виртуальное окружение:
    ```
    source venv/bin/activate
    ```

4. Установите зависимости:
    ```
    pip install -r requirements.txt
    ```

5. Выполните миграции базы данных:
    ```
    python manage.py migrate
    ```

6. Создайте суперпользователя (опционально, для доступа к админке):
    ```
    python manage.py createsuperuser
    ```

7. Запустите сервер разработки:
    ```
    python manage.py runserver
    ```

Приложение будет доступно по адресу http://127.0.0.1:8000/

Команда для запуска сервера разработки: python manage.py runserver

### Запуск приложения
Для развертывания Django-приложения в продакшене используется WSGI-сервер. Рекомендуется Gunicorn, так как он прост в установке и настройке.

1. Установите Gunicorn (WSGI-сервер):
   ```
   pip install gunicorn
   ```

2. Запустите приложение на порту 3001:
   ```
   gunicorn config.wsgi:application --bind 0.0.0.0:3001
   ```

Альтернативно, можно использовать другие WSGI-серверы, такие как uWSGI:
   ```
   pip install uwsgi
   uwsgi --http :3001 --wsgi-file config/wsgi.py --master --processes 4 --threads 2
   ```

### Настройка Nginx
1. Установите Nginx, если он еще не установлен.

2. Создайте новый файл конфигурации сайта, например, `/etc/nginx/sites-available/tool-system`:
   ```
   server {
       listen 80;
       server_name your_domain_or_ip;

       location / {
           proxy_pass http://127.0.0.1:3001;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
           proxy_set_header X-Forwarded-Proto $scheme;
       }

       location /static/ {
           alias /path/to/your/project/static/;
       }
   }
   ```

3. Включите сайт:
   ```
   sudo ln -s /etc/nginx/sites-available/tool-system /etc/nginx/sites-enabled/
   ```

4. Проверьте конфигурацию Nginx:
   ```
   sudo nginx -t
   ```

5. Перезапустите Nginx:
   ```
   sudo systemctl restart nginx
   ```

### Рекомендации для продакшена
- Используйте менеджер процессов, такой как Supervisor, для управления Gunicorn.
- Настройте SSL с Let's Encrypt для HTTPS.
- Установите соответствующие переменные окружения для настроек продакшена.
