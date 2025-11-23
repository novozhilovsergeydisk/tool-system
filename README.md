# Tool System

## Развертывание

### Предварительные требования
- Сервер с Ubuntu/Debian или аналогичной ОС
- Python 3.8+
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
   sudo apt install python3 python3-venv python3-pip nginx git supervisor certbot python3-certbot-nginx
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
1. Выполните миграции:
   ```
   python manage.py migrate
   ```

2. Соберите статические файлы:
   ```
   python manage.py collectstatic --noinput
   ```

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
