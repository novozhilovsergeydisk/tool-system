from django.db import models

# 1. Таблица USERS (Логины и Пароли)
class LegacyUser(models.Model):
    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=255)     # Логин (как мы выяснили)
    email = models.CharField(max_length=255)    # Почта
    password = models.CharField(max_length=255) # Хеш пароля (bcrypt)
    
    class Meta:
        managed = False      # Django не будет менять эту таблицу
        db_table = 'users'   # Имя таблицы в базе Node.js

# 2. Таблица EMPLOYEES (ФИО и Блокировка)
class LegacyEmployee(models.Model):
    id = models.BigIntegerField(primary_key=True)
    user_id = models.BigIntegerField() # Связь с users
    
    # Вы сказали, что поле ФИО называется 'fio', а блокировка 'is_deleted'.
    # Если в базе они называются иначе (например first_name), нужно поправить тут!
    fio = models.CharField(max_length=255) 
    is_deleted = models.BooleanField() # true = заблокирован

    class Meta:
        managed = False
        db_table = 'employees'

# 3. Таблица ROLES (Названия ролей)
class LegacyRole(models.Model):
    id = models.BigIntegerField(primary_key=True)
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255) # admin, user, etc.

    class Meta:
        managed = False
        db_table = 'roles'

# 4. Таблица USER_ROLES (Связь Кто - Какая роль)
class LegacyUserRole(models.Model):
    # У этой таблицы может не быть своего ID, поэтому используем user_id как ключ для чтения
    user_id = models.BigIntegerField(primary_key=True) 
    role_id = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = 'user_roles'