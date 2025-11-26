class LegacyRouter:
    """
    Маршрутизатор, который запрещает любые изменения (запись, удаление)
    в базе данных 'legacy' (Node.js).
    """
    def db_for_write(self, model, **hints):
        # Если модель пытается записаться в базу 'legacy' — ЗАПРЕТИТЬ
        if model._meta.app_label == 'inventory' and model.__name__.startswith('Legacy'):
            return False
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        # Запрещаем создавать таблицы (миграции) в базе 'legacy'
        if db == 'legacy':
            return False
        return None