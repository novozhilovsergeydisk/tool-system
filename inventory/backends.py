import bcrypt
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User
from django.db.models import Q
from .models_legacy import LegacyUser, LegacyEmployee, LegacyUserRole

class NodeAuthBackend(BaseBackend):
    """
    Авторизация через базу данных Node.js (lan_install)
    """
    def authenticate(self, request, username=None, password=None, **kwargs):
        # username - это то, что ввел пользователь в поле "Логин" (может быть login или email)
        
        try:
            # --- ШАГ 1. ИЩЕМ ПОЛЬЗОВАТЕЛЯ В users ---
            # Ищем совпадение по name (логин) ИЛИ по email
            legacy_user = LegacyUser.objects.using('legacy').filter(
                Q(name=username) | Q(email=username)
            ).first()
            
            if not legacy_user:
                return None # Такого пользователя нет

            # --- ШАГ 2. ПРОВЕРЯЕМ ПАРОЛЬ ---
            # Используем bcrypt для сверки введенного пароля с хешем из базы
            # .encode('utf-8') нужно, так как библиотека работает с байтами
            if not bcrypt.checkpw(password.encode('utf-8'), legacy_user.password.encode('utf-8')):
                return None # Пароль не подошел

            # --- ШАГ 3. ПРОВЕРЯЕМ БЛОКИРОВКУ В employees ---
            legacy_employee = LegacyEmployee.objects.using('legacy').filter(
                user_id=legacy_user.id
            ).first()

            # Если сотрудника нет в таблице employees ИЛИ поле is_deleted = True (t)
            if not legacy_employee or legacy_employee.is_deleted:
                return None # Доступ запрещен (Заблокирован или уволен)

            # --- ШАГ 4. СИНХРОНИЗАЦИЯ С DJANGO ---
            # Если мы дошли сюда - всё ок. Создаем/Обновляем пользователя у нас.
            
            # Логин в Django всегда берем из поля name (чтобы был унифицирован)
            django_username = legacy_user.name
            
            user, created = User.objects.get_or_create(username=django_username)
            
            # Обновляем Email из users
            user.email = legacy_user.email
            
            # Обновляем ФИО из employees (разбиваем строку "Иванов Иван Иванович")
            full_name = legacy_employee.fio.strip()
            if ' ' in full_name:
                parts = full_name.split(' ', 1)
                user.first_name = parts[0]
                user.last_name = parts[1]
            else:
                user.first_name = full_name
                user.last_name = ''
            
            user.is_active = True # Мы уже проверили блокировку выше
            
            # --- ШАГ 5. ПРОВЕРКА РОЛИ (role_id = 1) ---
            is_admin = LegacyUserRole.objects.using('legacy').filter(
                user_id=legacy_user.id,
                role_id=1
            ).exists()
            
            # Назначаем права
            user.is_staff = is_admin
            user.is_superuser = is_admin

            user.save()
            
            return user
            
        except Exception as e:
            # Если случилась ошибка подключения или другая беда - просто не пускаем
            # print(f"Auth error: {e}") # Можно раскомментировать для отладки
            return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None