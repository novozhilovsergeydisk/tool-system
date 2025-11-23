from django.db import models
from django.contrib.auth.models import User
from datetime import date, timedelta

# --- 1. СПРАВОЧНИКИ ---

class Warehouse(models.Model):
    name = models.CharField("Название склада", max_length=100)
    address = models.CharField("Адрес", max_length=200, blank=True, null=True)
    def __str__(self): return self.name
    class Meta: verbose_name = "Склад"; verbose_name_plural = "Склады"

class Nomenclature(models.Model):
    TYPE_CHOICES = (('TOOL', 'Инструмент'), ('CONSUMABLE', 'Расходник'))
    name = models.CharField("Название", max_length=200)
    article = models.CharField("Артикул", max_length=50, unique=True)
    item_type = models.CharField("Тип", max_length=20, choices=TYPE_CHOICES)
    description = models.TextField("Описание", blank=True)
    def __str__(self): return f"{self.name} ({self.article})"
    class Meta: verbose_name = "Номенклатура"; verbose_name_plural = "Номенклатура"

# --- 2. КОМПЛЕКТЫ И АВТОМОБИЛИ ---

class ToolKit(models.Model):
    name = models.CharField("Название комплекта", max_length=200)
    description = models.TextField("Описание", blank=True)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Место хранения")
    STATUS_CHOICES = (('IN_STOCK', 'На складе'), ('ISSUED', 'Выдан'))
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='IN_STOCK')
    current_holder = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Владелец")
    def __str__(self): return self.name
    class Meta: verbose_name = "Комплект"; verbose_name_plural = "Комплекты"

class Car(models.Model):
    name = models.CharField("Марка/Модель", max_length=200)
    license_plate = models.CharField("Госномер", max_length=20, unique=True)
    description = models.TextField("Описание", blank=True)
    
    # ИЗМЕНЕНО: Теперь это просто текстовое поле, без выпадающего списка
    fuel_type = models.CharField("Тип топлива", max_length=50, default="АИ-95")

    current_mileage = models.PositiveIntegerField("Текущий пробег (км)", default=0)
    last_service_mileage = models.PositiveIntegerField("Пробег на последнем ТО", default=0)
    
    checklist = models.TextField("Чек-лист при выдаче", default="1. Проверь уровень масла\n2. Проверь уровень жидкостей\n3. Проверь наличие топливной карты", blank=True)
    insurance_expiry = models.DateField("Дата окончания страховки", null=True, blank=True)
    
    is_truck = models.BooleanField("Это грузовой автомобиль", default=False)
    last_ti_date = models.DateField("Дата последнего Техосмотра", null=True, blank=True)

    STATUS_CHOICES = (
        ('PARKED', 'На парковке'), 
        ('ON_ROUTE', 'На выезде'),
        ('MAINTENANCE', 'На обслуживании (ТО)'),
        ('TECH_INSPECTION', 'На техосмотре'),
        ('BROKEN', 'СЛОМАН'),
    )
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='PARKED')
    current_driver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Водитель")

    # Логика ТО
    @property
    def next_service_at(self):
        return self.last_service_mileage + 7500

    @property
    def km_to_service(self):
        return self.next_service_at - self.current_mileage

    @property
    def service_status(self):
        left = self.km_to_service
        if left < 0: return 'danger'
        elif left <= 100: return 'warning'
        return 'ok'
    
    # Логика Техосмотра
    @property
    def next_ti_date(self):
        if self.last_ti_date:
            return self.last_ti_date + timedelta(days=365)
        return None

    @property
    def ti_status(self):
        if not self.is_truck or not self.next_ti_date:
            return 'ok'
        days_left = (self.next_ti_date - date.today()).days
        if days_left < 0: return 'danger'
        if days_left <= 30: return 'warning'
        return 'ok'

    def __str__(self): return f"{self.name} ({self.license_plate})"
    class Meta: verbose_name = "Автомобиль"; verbose_name_plural = "Автомобили"

# --- 3. УЧЕТ ОСТАТКОВ ---

class ToolInstance(models.Model):
    nomenclature = models.ForeignKey(Nomenclature, on_delete=models.CASCADE, verbose_name="Что это")
    inventory_id = models.CharField("Инвентарный номер", max_length=50, unique=True)
    purchase_date = models.DateField("Дата покупки", null=True, blank=True)
    current_warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="На складе")
    current_holder = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="У сотрудника")
    kit = models.ForeignKey(ToolKit, on_delete=models.SET_NULL, null=True, blank=True, related_name='tools', verbose_name="В комплекте")
    car = models.ForeignKey(Car, on_delete=models.SET_NULL, null=True, blank=True, related_name='tools', verbose_name="В машине")
    
    STATUS_CHOICES = (('IN_STOCK', 'В наличии'), ('ISSUED', 'Выдан'), ('BROKEN', 'В ремонте'), ('LOST', 'Утерян/Списан'))
    status = models.CharField("Статус", max_length=20, choices=STATUS_CHOICES, default='IN_STOCK')
    CONDITION_CHOICES = (('NEW', 'Новое'), ('USED', 'Б/У'), ('BROKEN', 'Сломано'))
    condition = models.CharField("Состояние", max_length=20, choices=CONDITION_CHOICES, default='NEW')
    def __str__(self): return f"{self.nomenclature.name} [#{self.inventory_id}]"
    class Meta: verbose_name = "Экземпляр инструмента"; verbose_name_plural = "Инструменты (Учет)"

class ConsumableBalance(models.Model):
    nomenclature = models.ForeignKey(Nomenclature, on_delete=models.CASCADE, verbose_name="Расходник")
    quantity = models.PositiveIntegerField("Количество")
    
    # Место хранения (одно из трех должно быть заполнено)
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, null=True, blank=True)
    holder = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    kit = models.ForeignKey(ToolKit, on_delete=models.CASCADE, null=True, blank=True, related_name='consumables', verbose_name="В комплекте") # <--- НОВОЕ

    def __str__(self): 
        if self.warehouse: place = self.warehouse.name
        elif self.holder: place = self.holder.username
        elif self.kit: place = f"Комплект {self.kit.name}"
        else: place = "???"
        return f"{self.nomenclature.name}: {self.quantity} шт. ({place})"

    class Meta: 
        verbose_name = "Остаток расходника"
        verbose_name_plural = "Расходники (Баланс)"
        # Добавляем уникальность для комплекта
        unique_together = [
            ['nomenclature', 'warehouse'], 
            ['nomenclature', 'holder'],
            ['nomenclature', 'kit'] # <--- НОВОЕ
        ]

# --- 4. ЖУРНАЛ ---

class MovementLog(models.Model):
    ACTION_CHOICES = (
        ('RECEIPT', 'Приемка'), ('ISSUE', 'Выдача'), ('RETURN', 'Возврат'), ('WRITEOFF', 'Списание'),
        ('KIT_ISSUE', 'Выдача Комплекта'), ('KIT_RETURN', 'Возврат Комплекта'),
        ('CAR_ISSUE', 'Выдача Авто'), ('CAR_RETURN', 'Возврат Авто'),
        ('CAR_TO_MAINT', 'Отправка на ТО'), ('CAR_FROM_MAINT', 'Возврат с ТО'),
        ('CAR_TO_TI', 'Отправка на Техосмотр'), ('CAR_FROM_TI', 'Возврат с Техосмотра'), # НОВЫЕ
    )

    date = models.DateTimeField("Дата и время", auto_now_add=True)
    initiator = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='actions')
    action_type = models.CharField("Тип", max_length=20, choices=ACTION_CHOICES)
    
    nomenclature = models.ForeignKey(Nomenclature, on_delete=models.SET_NULL, null=True)
    nomenclature_name = models.CharField("Название (Архив)", max_length=200, blank=True)
    nomenclature_article = models.CharField("Артикул (Архив)", max_length=50, blank=True)
    serial_number = models.CharField("S/N (Архив)", max_length=50, blank=True)
    
    tool_instance = models.ForeignKey(ToolInstance, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.PositiveIntegerField("Количество", default=1)
    
    source_warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name='outgoing')
    source_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='returned')
    source_kit = models.ForeignKey(ToolKit, on_delete=models.SET_NULL, null=True, blank=True, related_name='outgoing_tools')
    source_car = models.ForeignKey(Car, on_delete=models.SET_NULL, null=True, blank=True, related_name='outgoing_tools')
    
    target_warehouse = models.ForeignKey(Warehouse, on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming')
    target_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='received')
    target_kit = models.ForeignKey(ToolKit, on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_tools')
    target_car = models.ForeignKey(Car, on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_tools')
    
    kit_name = models.CharField("Комплект (Архив)", max_length=200, blank=True)
    car_name = models.CharField("Авто (Архив)", max_length=200, blank=True)
    
    trip_mileage = models.PositiveIntegerField("Пробег за поездку", null=True, blank=True)
    fuel_liters = models.PositiveIntegerField("Заправлено (л)", null=True, blank=True)
    maintenance_work = models.TextField("Работы", blank=True)
    
    comment = models.TextField("Комментарий", blank=True)

    def save(self, *args, **kwargs):
        if self.nomenclature:
            self.nomenclature_name = self.nomenclature.name
            self.nomenclature_article = self.nomenclature.article
        if self.tool_instance: self.serial_number = self.tool_instance.inventory_id
        if self.source_kit: self.kit_name = self.source_kit.name
        elif self.target_kit: self.kit_name = self.target_kit.name
        if self.source_car: self.car_name = str(self.source_car)
        elif self.target_car: self.car_name = str(self.target_car)
        super().save(*args, **kwargs)

    def __str__(self): return f"{self.date} - {self.get_action_type_display()}"
    class Meta: verbose_name = "Запись в журнале"; verbose_name_plural = "Журнал движений"