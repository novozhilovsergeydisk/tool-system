from django.contrib import admin
from .models import Warehouse, Nomenclature, ToolInstance, ConsumableBalance, MovementLog

# --- 1. КНОПКА: ВЕРНУТЬ НА СКЛАД ---
@admin.action(description='Вернуть на Основной Склад')
def return_to_warehouse(modeladmin, request, queryset):
    main_warehouse = Warehouse.objects.first()
    if not main_warehouse:
        modeladmin.message_user(request, "Ошибка: Создайте хотя бы один склад!", level='error')
        return
    
    count = 0
    for tool in queryset:
        if tool.current_warehouse == main_warehouse: continue
        
        # Пишем в журнал
        MovementLog.objects.create(
            initiator=request.user, action_type='RETURN',
            nomenclature=tool.nomenclature, tool_instance=tool,
            source_user=tool.current_holder, target_warehouse=main_warehouse,
            comment="Быстрый возврат (Админка)"
        )
        
        # Меняем статус
        tool.current_warehouse = main_warehouse
        tool.current_holder = None
        tool.status = 'IN_STOCK'
        tool.save()
        count += 1
    modeladmin.message_user(request, f"Успешно возвращено: {count} шт.")

# --- 2. ТАБЛИЦЫ (ИНТЕРФЕЙС) ---

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'address')

@admin.register(Nomenclature)
class NomenclatureAdmin(admin.ModelAdmin):
    list_display = ('name', 'article', 'item_type')
    list_filter = ('item_type',)

@admin.register(ToolInstance)
class ToolInstanceAdmin(admin.ModelAdmin):
    # Настройка колонок
    list_display = ('nomenclature', 'inventory_id', 'status', 'current_warehouse', 'current_holder')
    list_editable = ('status', 'current_warehouse', 'current_holder') # Разрешаем править в списке
    list_filter = ('status', 'current_warehouse', 'current_holder')
    search_fields = ('inventory_id', 'nomenclature__name')
    actions = [return_to_warehouse] # Подключаем нашу кнопку

    # Авто-запись в журнал при изменении руками
    def save_model(self, request, obj, form, change):
        if change:
            old = ToolInstance.objects.get(pk=obj.pk)
            # Если выдали сотруднику
            if old.current_holder is None and obj.current_holder is not None:
                MovementLog.objects.create(
                    initiator=request.user, action_type='ISSUE',
                    nomenclature=obj.nomenclature, tool_instance=obj,
                    source_warehouse=old.current_warehouse, target_user=obj.current_holder,
                    comment="Выдача через список"
                )
                obj.current_warehouse = None
                obj.status = 'ISSUED'
            # Если вернули на склад
            elif old.current_warehouse is None and obj.current_warehouse is not None:
                MovementLog.objects.create(
                    initiator=request.user, action_type='RETURN',
                    nomenclature=obj.nomenclature, tool_instance=obj,
                    source_user=old.current_holder, target_warehouse=obj.current_warehouse,
                    comment="Возврат через список"
                )
                obj.current_holder = None
                obj.status = 'IN_STOCK'
        super().save_model(request, obj, form, change)

# --- ВОТ ЭТА ЧАСТЬ ПРОПАЛА В ПРОШЛЫЙ РАЗ ---

@admin.register(ConsumableBalance)
class ConsumableBalanceAdmin(admin.ModelAdmin):
    list_display = ('nomenclature', 'quantity', 'warehouse', 'holder')
    list_editable = ('quantity',)

@admin.register(MovementLog)
class MovementLogAdmin(admin.ModelAdmin):
    list_display = ('date', 'action_type', 'nomenclature', 'initiator', 'comment')
    list_filter = ('action_type', 'date', 'initiator')