from django import forms
from django.contrib.auth.models import User
from .models import Nomenclature, ToolInstance, ToolKit, Warehouse, Car

# 1. Форма для создания ВИДА товара (Справочник)
class NomenclatureForm(forms.ModelForm):
    class Meta:
        model = Nomenclature
        fields = ['name', 'article', 'item_type', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'article': forms.TextInput(attrs={'class': 'form-control'}),
            'item_type': forms.Select(attrs={'class': 'form-select'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

# 2. Форма для ПРИХОДА (Универсальная)
class ToolInstanceForm(forms.ModelForm):
    quantity = forms.IntegerField(
        label='Количество', 
        initial=1, 
        min_value=1,
        required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = ToolInstance
        fields = ['nomenclature', 'inventory_id', 'current_warehouse', 'purchase_date', 'status', 'condition']
        labels = {
            'nomenclature': 'Что это (Номенклатура)',
            'inventory_id': 'Инвентарный номер / S/N',
            'current_warehouse': 'На какой склад принять',
            'purchase_date': 'Дата покупки',
            'status': 'Статус',
            'condition': 'Состояние'
        }
        widgets = {
            'nomenclature': forms.Select(attrs={'class': 'form-select', 'id': 'id_nomenclature'}),
            'inventory_id': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_inventory_id'}),
            'current_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'purchase_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'condition': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['inventory_id'].required = False

# 3. Форма сотрудника (С ПЕРЕВОДОМ)
class EmployeeForm(forms.ModelForm):
    new_password = forms.CharField(
        label='Новый пароль',
        required=False,
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Оставьте пустым, если не меняете'}),
        help_text='Введите сюда новый пароль, чтобы изменить его.'
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'is_active', 'is_staff']
        
        labels = {
            'username': 'Логин',
            'first_name': 'Имя',
            'last_name': 'Фамилия',
            'email': 'Email',
            'is_active': 'Активен (доступ разрешен)',
            'is_staff': 'Администратор (полный доступ)'
        }
        help_texts = {
            'username': 'Обязательно. Не более 150 символов. Только буквы, цифры и символы @/./+/-/_.',
            'is_active': 'Отметьте, если пользователь должен иметь доступ к сайту. Снимите галочку вместо удаления аккаунта.',
            'is_staff': 'Отметьте, если пользователь может входить в панель администратора и видеть расширенное меню.',
        }
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

# 4. Форма Комплекта
class ToolKitForm(forms.ModelForm):
    class Meta:
        model = ToolKit
        fields = ['name', 'description', 'warehouse']
        labels = {
            'name': 'Название комплекта',
            'description': 'Описание',
            'warehouse': 'Склад приписки (где хранится)'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
        }

# 5. Форма Склада
class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'address']
        labels = {
            'name': 'Название склада',
            'address': 'Адрес / Местоположение'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
        }

# 6. Форма Автомобиля
class CarForm(forms.ModelForm):
    class Meta:
        model = Car
        fields = ['name', 'license_plate', 'fuel_type', 'is_truck', 'current_mileage', 'last_service_mileage', 'last_ti_date', 'insurance_expiry', 'checklist', 'description']
        labels = {
            'name': 'Марка и Модель',
            'license_plate': 'Госномер',
            'fuel_type': 'Тип топлива',
            'is_truck': 'Это грузовой автомобиль',
            'current_mileage': 'Текущий пробег (км)',
            'last_service_mileage': 'Пробег на последнем ТО',
            'last_ti_date': 'Дата последнего ТЕХОСМОТРА',
            'insurance_expiry': 'Дата окончания страховки',
            'checklist': 'Текст напоминания при выдаче',
            'description': 'Описание'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Lada Largus'}),
            'license_plate': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'А 000 АА 777'}),
            'fuel_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: АИ-95'}),
            'is_truck': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'current_mileage': forms.NumberInput(attrs={'class': 'form-control'}),
            'last_service_mileage': forms.NumberInput(attrs={'class': 'form-control'}),
            'last_ti_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'insurance_expiry': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'checklist': forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }