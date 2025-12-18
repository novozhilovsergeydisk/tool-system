from django import forms
from django.contrib.auth.models import User
from .models import Nomenclature, ToolInstance, ToolKit, Warehouse, Car, News
from django.db.models import Q

# 1. Форма для создания ВИДА товара
class NomenclatureForm(forms.ModelForm):
    confirm_save = forms.BooleanField(required=False, initial=False, widget=forms.HiddenInput())

    class Meta:
        model = Nomenclature
        fields = ['name', 'article', 'item_type', 'minimum_stock', 'description']
        labels = {
            'name': 'Название', 'article': 'Артикул', 'item_type': 'Тип',
            'minimum_stock': 'Мин. остаток', 'description': 'Описание'
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'article': forms.TextInput(attrs={'class': 'form-control'}),
            'item_type': forms.Select(attrs={'class': 'form-select'}),
            'minimum_stock': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': '0'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        article = cleaned_data.get('article')
        confirm = cleaned_data.get('confirm_save')

        if name and article:
            exact_match = Nomenclature.objects.filter(name__iexact=name, article__iexact=article)
            if self.instance.pk:
                exact_match = exact_match.exclude(pk=self.instance.pk)
            
            if exact_match.exists():
                raise forms.ValidationError("⛔ ОШИБКА: Товар с таким Названием И Артикулом уже существует!")

            if not confirm:
                similar = Nomenclature.objects.filter(Q(name__iexact=name) | Q(article__iexact=article))
                if self.instance.pk:
                    similar = similar.exclude(pk=self.instance.pk)
                
                if similar.exists():
                    obj = similar.first()
                    msg = f"Внимание! В базе уже есть: «{obj.name}» [{obj.article}]. Это точно другой товар?"
                    self.fields['confirm_save'].widget = forms.CheckboxInput(attrs={'class': 'form-check-input'})
                    self.fields['confirm_save'].label = "Да, я уверен. Сохранить."
                    raise forms.ValidationError(msg)
        return cleaned_data

# 2. Форма для ПРИХОДА
class ToolInstanceForm(forms.ModelForm):
    quantity = forms.IntegerField(
        label='Количество', initial=1, min_value=1, required=False,
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = ToolInstance
        fields = ['nomenclature', 'inventory_id', 'current_warehouse', 'condition']
        labels = {
            'nomenclature': 'Что принимаем (Номенклатура)',
            'inventory_id': 'Инвентарный номер / S/N',
            'current_warehouse': 'На какой склад принять',
            'condition': 'Состояние (для инструмента)'
        }
        widgets = {
            'nomenclature': forms.Select(attrs={'class': 'form-select', 'id': 'id_nomenclature'}),
            'inventory_id': forms.TextInput(attrs={'class': 'form-control', 'id': 'id_inventory_id'}),
            'current_warehouse': forms.Select(attrs={'class': 'form-select'}),
            'condition': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['inventory_id'].required = False
        if not self.instance.pk:
            self.fields['current_warehouse'].required = True
            self.fields['current_warehouse'].label = "На какой склад принять (Обязательно)"

# --- НОВЫЕ ФОРМЫ СОТРУДНИКОВ ---

# 3.1. Форма СОЗДАНИЯ (С паролем и правами)
class EmployeeAddForm(forms.ModelForm):
    password = forms.CharField(label="Пароль", widget=forms.PasswordInput(attrs={'class': 'form-control'}), required=True)
    
    is_superuser = forms.BooleanField(
        label="Администратор (Полный доступ)", 
        required=False, 
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        help_text="Дает полный доступ ко всем складам и настройкам."
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'password']
        labels = {'username': 'Логин', 'first_name': 'Имя', 'last_name': 'Фамилия', 'email': 'Email'}
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if self.cleaned_data["is_superuser"]:
            user.is_superuser = True
            user.is_staff = True
        if commit:
            user.save()
        return user

# 3.2. Форма РЕДАКТИРОВАНИЯ (Без пароля и прав)
class EmployeeEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        labels = {'username': 'Логин', 'first_name': 'Имя', 'last_name': 'Фамилия', 'email': 'Email'}
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'username' in self.fields:
            self.fields['username'].disabled = True

# 4. Остальные формы (без изменений)
class ToolKitForm(forms.ModelForm):
    class Meta:
        model = ToolKit
        fields = ['name', 'description', 'warehouse']
        labels = {'name': 'Название комплекта', 'description': 'Описание', 'warehouse': 'Склад приписки'}
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'warehouse': forms.Select(attrs={'class': 'form-select'}),
        }

class WarehouseForm(forms.ModelForm):
    class Meta:
        model = Warehouse
        fields = ['name', 'address']
        labels = {'name': 'Название склада', 'address': 'Адрес'}
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
        }

class CarForm(forms.ModelForm):
    class Meta:
        model = Car
        fields = ['name', 'license_plate', 'fuel_type', 'is_truck', 'current_mileage', 'last_service_mileage', 'last_ti_date', 'insurance_expiry', 'checklist', 'description']
        labels = {
            'name': 'Марка и Модель', 'license_plate': 'Госномер', 'fuel_type': 'Тип топлива',
            'is_truck': 'Это грузовой автомобиль', 'current_mileage': 'Текущий пробег (км)',
            'last_service_mileage': 'Пробег на последнем ТО', 'last_ti_date': 'Дата последнего ТЕХОСМОТРА',
            'insurance_expiry': 'Дата окончания страховки', 'checklist': 'Текст напоминания при выдаче',
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

class NewsForm(forms.ModelForm):
    class Meta:
        model = News
        fields = ['title', 'text', 'is_important']
        labels = {'title': 'Заголовок', 'text': 'Текст', 'is_important': 'Пометить как ВАЖНУЮ'}
        widgets = {
            'title': forms.TextInput(attrs={'class': 'form-control'}),
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_important': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }