import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.http import JsonResponse
from django.core.paginator import Paginator
from datetime import date, timedelta
from django.contrib import messages
from .models import Nomenclature, ToolInstance, Warehouse, MovementLog, ConsumableBalance, ToolKit, Car, News
from .forms import NomenclatureForm, EmployeeForm, ToolInstanceForm, ToolKitForm, WarehouseForm, CarForm, NewsForm
from django.db.models import Q, Sum 

# --- 1. ДАШБОРД (ГЛАВНАЯ) ---
@login_required
def index(request):
    """Главная страница: Дашборд со статистикой, новостями и АЛЕРТАМИ"""
    today = date.today()
    yesterday = today - timedelta(days=1)
    warning_date = today + timedelta(days=30)

    # Статистика (без изменений)
    ops_today = MovementLog.objects.filter(date__date=today).count()
    ops_yesterday = MovementLog.objects.filter(date__date=yesterday).count()
    rec_today = MovementLog.objects.filter(date__date=today, action_type='RECEIPT').exclude(serial_number='').count()
    rec_yesterday = MovementLog.objects.filter(date__date=yesterday, action_type='RECEIPT').exclude(serial_number='').count()
    users_today = User.objects.filter(actions__date__date=today).distinct()
    users_yesterday = User.objects.filter(actions__date__date=yesterday).distinct()

    wh_count = ToolInstance.objects.filter(current_warehouse__isnull=False).values('current_warehouse').distinct().count()
    emp_count = ToolInstance.objects.filter(current_holder__isnull=False).values('current_holder').distinct().count()
    kit_count = ToolKit.objects.filter(status='ISSUED').count()
    car_count = Car.objects.filter(status='ON_ROUTE').count()
    
    # --- ПОИСК ПРОБЛЕМ (ТОЛЬКО ДЛЯ АДМИНОВ) ---
    alerts = []
    if request.user.is_staff:
        
        # 1. АВТОМОБИЛИ (ГРУППИРОВКА ПРОБЛЕМ)
        cars = Car.objects.all()
        for car in cars:
            car_issues = [] # Список проблем конкретной машины
            has_critical = False # Есть ли критичные проблемы (просрочка)

            # Проверка Страховки
            if car.insurance_expiry and car.insurance_expiry <= warning_date:
                days_left = (car.insurance_expiry - today).days
                if days_left < 0:
                    car_issues.append(f"Страховка: ИСТЕКЛА ({abs(days_left)} дн. назад)")
                    has_critical = True
                else:
                    car_issues.append(f"Страховка: истекает через {days_left} дн.")

            # Проверка ТО (Масло)
            if car.service_status != 'ok':
                km = car.km_to_service
                if km < 0:
                    car_issues.append(f"ТО (Масло): Просрочено на {abs(km)} км")
                    has_critical = True
                else:
                    car_issues.append(f"ТО (Масло): Осталось {km} км")

            # Проверка Техосмотра (Грузовые)
            if car.is_truck and car.ti_status != 'ok':
                if car.ti_status == 'danger':
                    car_issues.append("Техосмотр: ПРОСРОЧЕН!")
                    has_critical = True
                else:
                    car_issues.append("Техосмотр: Скоро подходит срок")

            # Если у машины есть проблемы - добавляем ОДИН общий алерт
            if car_issues:
                alerts.append({
                    'type': 'danger' if has_critical else 'warning',
                    'icon': 'fa-car', # Общая иконка
                    'text': f"{car.name} ({car.license_plate})", # Заголовок
                    'details_list': car_issues, # Список проблем
                    'link': f"/cars/?car_id={car.id}" # Ссылка на карточку
                })

        # 2. РАСХОДНИКИ (ГРУППИРОВКА ПО СКЛАДАМ)
        stock_problems = {}
        balances = ConsumableBalance.objects.filter(nomenclature__minimum_stock__gt=0, warehouse__isnull=False).select_related('nomenclature', 'warehouse')

        for bal in balances:
            if bal.quantity <= bal.nomenclature.minimum_stock:
                wh_name = bal.warehouse.name
                if wh_name not in stock_problems:
                    stock_problems[wh_name] = []
                stock_problems[wh_name].append(f"{bal.nomenclature.name} {bal.nomenclature.article} (Осталось {bal.quantity})")
        
        for wh_name, items_list in stock_problems.items():
            alerts.append({
                'type': 'warning',
                'icon': 'fa-boxes-packing',
                'text': f"На складе «{wh_name}» заканчиваются:",
                'details_list': items_list,
                'link': None # Ссылка не нужна
            })

    # Новости
    latest_news = News.objects.all().order_by('-date')[:5]

    context = {
        'ops_today': ops_today, 'ops_yesterday': ops_yesterday,
        'rec_today': rec_today, 'rec_yesterday': rec_yesterday,
        'users_today': users_today, 'users_yesterday': users_yesterday,
        'wh_count': wh_count, 'emp_count': emp_count,
        'kit_count': kit_count, 'car_count': car_count,
        'latest_news': latest_news,
        'news_form': NewsForm(),
        'alerts': alerts,
    }
    return render(request, 'inventory/index.html', context)

    """Главная страница: Дашборд со статистикой, новостями и АЛЕРТАМИ"""
    today = date.today()
    yesterday = today - timedelta(days=1)
    warning_date = today + timedelta(days=30)

    # Статистика
    ops_today = MovementLog.objects.filter(date__date=today).count()
    ops_yesterday = MovementLog.objects.filter(date__date=yesterday).count()
    rec_today = MovementLog.objects.filter(date__date=today, action_type='RECEIPT').exclude(serial_number='').count()
    rec_yesterday = MovementLog.objects.filter(date__date=yesterday, action_type='RECEIPT').exclude(serial_number='').count()
    users_today = User.objects.filter(actions__date__date=today).distinct()
    users_yesterday = User.objects.filter(actions__date__date=yesterday).distinct()

    wh_count = ToolInstance.objects.filter(current_warehouse__isnull=False).values('current_warehouse').distinct().count()
    emp_count = ToolInstance.objects.filter(current_holder__isnull=False).values('current_holder').distinct().count()
    kit_count = ToolKit.objects.filter(status='ISSUED').count()
    car_count = Car.objects.filter(status='ON_ROUTE').count()
    
    # АЛЕРТЫ (Только для админов)
    alerts = []
    if request.user.is_staff:
        # 1. АВТОМОБИЛИ
        cars = Car.objects.all()
        for car in cars:
            if car.insurance_expiry and car.insurance_expiry <= warning_date:
                days_left = (car.insurance_expiry - today).days
                msg = "Истекла!" if days_left < 0 else f"Осталось {days_left} дн."
                alerts.append({'type': 'danger' if days_left <= 0 else 'warning', 'icon': 'fa-file-contract', 'text': f"Страховка: {car.name} ({car.license_plate}) - {msg}", 'link': f"/cars/?car_id={car.id}"})
            
            if car.service_status != 'ok':
                km = car.km_to_service
                msg = f"Просрочено на {abs(km)} км" if km < 0 else f"Осталось {km} км"
                # ИСПРАВЛЕНО: Убрали "(Масло)" из текста
                alerts.append({'type': 'danger' if km < 0 else 'warning', 'icon': 'fa-wrench', 'text': f"ТО: {car.name} ({car.license_plate}) - {msg}", 'link': f"/cars/?car_id={car.id}"})
            
            if car.is_truck and car.ti_status != 'ok':
                alerts.append({'type': 'danger' if car.ti_status == 'danger' else 'warning', 'icon': 'fa-clipboard-list', 'text': f"Техосмотр: {car.name} ({car.license_plate}) - Пора проходить!", 'link': f"/cars/?car_id={car.id}"})

        # 2. РАСХОДНИКИ (ГРУППИРОВКА ПО СКЛАДАМ)
        stock_problems = {}
        balances = ConsumableBalance.objects.filter(nomenclature__minimum_stock__gt=0, warehouse__isnull=False).select_related('nomenclature', 'warehouse')

        for bal in balances:
            if bal.quantity <= bal.nomenclature.minimum_stock:
                wh_name = bal.warehouse.name
                if wh_name not in stock_problems:
                    stock_problems[wh_name] = []
                stock_problems[wh_name].append(f"{bal.nomenclature.name} {bal.nomenclature.article} (Осталось {bal.quantity})")
        
        for wh_name, items_list in stock_problems.items():
            alerts.append({
                'type': 'warning',
                'icon': 'fa-boxes-packing',
                'text': f"На складе «{wh_name}» заканчиваются:",
                'details_list': items_list, # ИСПРАВЛЕНО: Имя ключа 'items' заменено на 'details_list'
                'link': None
            })

    # Новости
    latest_news = News.objects.all().order_by('-date')[:5]

    context = {
        'ops_today': ops_today, 'ops_yesterday': ops_yesterday,
        'rec_today': rec_today, 'rec_yesterday': rec_yesterday,
        'users_today': users_today, 'users_yesterday': users_yesterday,
        'wh_count': wh_count, 'emp_count': emp_count,
        'kit_count': kit_count, 'car_count': car_count,
        'latest_news': latest_news,
        'news_form': NewsForm(),
        'alerts': alerts,
    }
    return render(request, 'inventory/index.html', context)

# --- 2. НОВОСТИ (ДОБАВЛЕНЫ) ---
@staff_member_required
def news_add(request):
    if request.method == 'POST':
        form = NewsForm(request.POST)
        if form.is_valid():
            news = form.save(commit=False)
            news.author = request.user
            news.save()
            messages.success(request, "Новость опубликована!")
    return redirect('index')

@staff_member_required
def news_delete(request, pk):
    news = get_object_or_404(News, pk=pk)
    if request.method == 'POST':
        news.delete()
        messages.success(request, "Новость удалена.")
    return redirect('index')

@staff_member_required
def news_delete(request, pk):
    news = get_object_or_404(News, pk=pk)
    if request.method == 'POST':
        news.delete()
        messages.success(request, "Новость удалена.")
    return redirect('index')
    # Новости
    latest_news = News.objects.all().order_by('-date')[:5]

    context = {
        'ops_today': ops_today, 'ops_yesterday': ops_yesterday,
        'rec_today': rec_today, 'rec_yesterday': rec_yesterday,
        'users_today': users_today, 'users_yesterday': users_yesterday,
        'wh_count': wh_count, 'emp_count': emp_count,
        'kit_count': kit_count, 'car_count': car_count,
        'latest_news': latest_news,
        'news_form': NewsForm(),
        'alerts': alerts,
    }
    return render(request, 'inventory/index.html', context)


# --- 2. СПИСОК ТОВАРОВ (С ПАГИНАЦИЕЙ) ---
@login_required
def tool_list(request):
    """Таблица всех инструментов и расходников"""
    
    # 1. Базовые запросы
    # Инструменты: скрываем те, что в комплектах или машинах
    tools = ToolInstance.objects.filter(kit__isnull=True, car__isnull=True).order_by('id')
    
    # Расходники: ТЕПЕРЬ ТОЖЕ скрываем те, что в комплектах (kit__isnull=True)
    consumables = ConsumableBalance.objects.filter(kit__isnull=True).order_by('nomenclature__name')
    
    employees = User.objects.filter(is_active=True).order_by('username')
    warehouses = Warehouse.objects.all().order_by('name')

    # 2. Фильтрация
    search = request.GET.get('search', '')
    wh_id = request.GET.get('warehouse', '')
    emp_id = request.GET.get('employee', '')

    if search:
        tools = tools.filter(Q(nomenclature__name__icontains=search) | Q(inventory_id__icontains=search))
        consumables = consumables.filter(nomenclature__name__icontains=search)
    if wh_id:
        tools = tools.filter(current_warehouse_id=wh_id)
        consumables = consumables.filter(warehouse_id=wh_id)
    if emp_id:
        tools = tools.filter(current_holder_id=emp_id)
        consumables = consumables.filter(holder_id=emp_id)

    # 3. Пагинация (10 на страницу)
    paginator_tools = Paginator(tools, 10)
    tools_page = paginator_tools.get_page(request.GET.get('page_tools'))

    paginator_cons = Paginator(consumables, 10)
    consumables_page = paginator_cons.get_page(request.GET.get('page_cons'))

    context = {
        'tools': tools_page, 
        'consumables': consumables_page, 
        'employees': employees, 
        'warehouses': warehouses
    }
    
    # AJAX обновление
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory/tool_list_content.html', context)

    return render(request, 'inventory/tool_list.html', context)
    """Таблица всех инструментов и расходников"""
    # 1. Базовые запросы
    tools = ToolInstance.objects.filter(kit__isnull=True, car__isnull=True).order_by('id')
    consumables = ConsumableBalance.objects.all().order_by('nomenclature__name')
    
    employees = User.objects.filter(is_active=True).order_by('username')
    warehouses = Warehouse.objects.all().order_by('name')

    # 2. Фильтрация
    search = request.GET.get('search', '')
    wh_id = request.GET.get('warehouse', '')
    emp_id = request.GET.get('employee', '')

    if search:
        tools = tools.filter(Q(nomenclature__name__icontains=search) | Q(inventory_id__icontains=search))
        consumables = consumables.filter(nomenclature__name__icontains=search)
    if wh_id:
        tools = tools.filter(current_warehouse_id=wh_id)
        consumables = consumables.filter(warehouse_id=wh_id)
    if emp_id:
        tools = tools.filter(current_holder_id=emp_id)
        consumables = consumables.filter(holder_id=emp_id)

    # 3. Пагинация ИНСТРУМЕНТОВ (20 на страницу)
    paginator_tools = Paginator(tools, 10)
    page_tools_num = request.GET.get('page_tools')
    tools_page = paginator_tools.get_page(page_tools_num)

    # 4. Пагинация РАСХОДНИКОВ (20 на страницу)
    paginator_cons = Paginator(consumables, 10)
    page_cons_num = request.GET.get('page_cons')
    consumables_page = paginator_cons.get_page(page_cons_num)

    context = {
        'tools': tools_page, 
        'consumables': consumables_page, 
        'employees': employees, 
        'warehouses': warehouses
    }
    
    # Если запрос пришел через AJAX (JavaScript) - отдаем только кусок с таблицами
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory/tool_list_content.html', context)

    # Иначе отдаем полную страницу
    return render(request, 'inventory/tool_list.html', context)

# --- 2. АВТОМОБИЛИ ---
@login_required
def car_list(request):
    cars = Car.objects.all()
    selected_car = None
    edit_form = None
    
    history_trip_page = None
    history_maint_page = None
    
    today = date.today()
    warning_date = today + timedelta(days=30)

    if request.GET.get('car_id'):
        selected_car = get_object_or_404(Car, pk=request.GET.get('car_id'))
        edit_form = CarForm(instance=selected_car)
        
        # 1. История ПОЕЗДОК
        logs_trips = MovementLog.objects.filter(
            Q(source_car=selected_car) | Q(target_car=selected_car),
            action_type__in=['CAR_ISSUE', 'CAR_RETURN']
        ).order_by('-date')
        paginator_trips = Paginator(logs_trips, 10)
        history_trip_page = paginator_trips.get_page(request.GET.get('page_trips'))

        # 2. История ОБСЛУЖИВАНИЯ (ТО)
        logs_maint = MovementLog.objects.filter(
            Q(source_car=selected_car) | Q(target_car=selected_car),
            action_type__in=['CAR_TO_MAINT', 'CAR_FROM_MAINT', 'CAR_TO_TI', 'CAR_FROM_TI']
        ).order_by('-date')
        paginator_maint = Paginator(logs_maint, 10)
        history_maint_page = paginator_maint.get_page(request.GET.get('page_maint'))

    context = {
        'cars': cars,
        'selected_car': selected_car,
        'employees': User.objects.filter(is_active=True),
        'form': CarForm(),
        'edit_form': edit_form,
        'history_trip_page': history_trip_page,
        'history_maint_page': history_maint_page,
        'today': today,
        'warning_date': warning_date
    }

    # AJAX: Возвращаем только правую часть (карточку и таблицы)
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory/cars_content.html', context)

    return render(request, 'inventory/cars.html', context)

@staff_member_required
def car_create(request):
    if request.method == 'POST':
        form = CarForm(request.POST)
        if form.is_valid(): car = form.save(); return redirect(f'/cars/?car_id={car.id}')
    return redirect('car_list')

@staff_member_required
def car_edit(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        form = CarForm(request.POST, instance=car)
        if form.is_valid(): form.save(); return redirect(f'/cars/?car_id={car.id}')
    return redirect('car_list')

@staff_member_required
def car_delete(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        for t in car.tools.all(): t.car = None; t.current_warehouse = Warehouse.objects.first(); t.status='IN_STOCK'; t.save()
        car.delete()
    return redirect('car_list')

@login_required
def car_issue(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        user = get_object_or_404(User, pk=request.POST.get('employee_id'))
        car.current_driver = user; car.status = 'ON_ROUTE'; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_ISSUE', target_user=user, target_car=car, comment="Выезд")
    return redirect(f'/cars/?car_id={car.id}')

@login_required
def car_return(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        holder_was = car.current_driver
        end_mileage = int(request.POST.get('end_mileage', car.current_mileage))
        trip_dist = max(0, end_mileage - car.current_mileage)
        fuel_liters = int(request.POST.get('fuel_liters', 0)) if request.POST.get('fuel_added') == 'on' else 0
        car.current_driver = None; car.status = 'PARKED'; car.current_mileage = end_mileage; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_RETURN', source_user=holder_was, source_car=car, trip_mileage=trip_dist, fuel_liters=fuel_liters, comment=f"Возврат. Пробег: {trip_dist} км.")
    return redirect(f'/cars/?car_id={car.id}')

@staff_member_required
def car_to_maintenance(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        car.current_driver = None; car.status = 'MAINTENANCE'; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_TO_MAINT', target_car=car, comment="Отправлена на ТО")
    return redirect(f'/cars/?car_id={car.id}')

@staff_member_required
def car_return_from_maintenance(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        end_mileage = int(request.POST.get('end_mileage', car.current_mileage))
        trip_dist = max(0, end_mileage - car.current_mileage)
        car.status = 'PARKED'; car.current_mileage = end_mileage; car.last_service_mileage = end_mileage; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_FROM_MAINT', source_car=car, trip_mileage=trip_dist, maintenance_work=request.POST.get('works', ''), comment="Возврат с ТО. Интервал сброшен.")
    return redirect(f'/cars/?car_id={car.id}')

@staff_member_required
def car_to_tech_inspection(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        car.current_driver = None; car.status = 'TECH_INSPECTION'; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_TO_TI', target_car=car, comment="Отправлена на Техосмотр")
    return redirect(f'/cars/?car_id={car.id}')

@staff_member_required
def car_return_from_tech_inspection(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        end_mileage = int(request.POST.get('end_mileage', car.current_mileage))
        fuel_liters = int(request.POST.get('fuel_liters', 0)) if request.POST.get('fuel_added') == 'on' else 0
        trip_dist = max(0, end_mileage - car.current_mileage)
        car.status = 'PARKED'; car.current_mileage = end_mileage; car.last_ti_date = date.today(); car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_FROM_TI', source_car=car, trip_mileage=trip_dist, fuel_liters=fuel_liters, comment=f"Возврат с Техосмотра. Дата обновлена. Пробег: {trip_dist} км")
    return redirect(f'/cars/?car_id={car.id}')
@staff_member_required
def car_mark_broken(request, car_id):
    """Пометить машину как СЛОМАННУЮ"""
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        car.current_driver = None # Если была у кого-то, "забираем" (формально)
        car.status = 'BROKEN'
        car.save()
        
        MovementLog.objects.create(
            initiator=request.user,
            action_type='CAR_TO_MAINT', # Используем тип "На обслуживание" или создадим новый, если критично
            target_car=car,
            comment="АВТОМОБИЛЬ СЛОМАН (Помечен администратором)"
        )
    return redirect(f'/cars/?car_id={car.id}')

@staff_member_required
def car_mark_fixed(request, car_id):
    """Починили (Вернуть на парковку с данными о ремонте)"""
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        end_mileage = int(request.POST.get('end_mileage', car.current_mileage))
        works = request.POST.get('works', '')
        fuel_liters = int(request.POST.get('fuel_liters', 0)) if request.POST.get('fuel_added') == 'on' else 0
        
        trip_dist = max(0, end_mileage - car.current_mileage)
        
        car.status = 'PARKED'
        car.current_mileage = end_mileage
        car.save()
        
        MovementLog.objects.create(
            initiator=request.user,
            action_type='CAR_FROM_MAINT', # Используем тип "С обслуживания"
            source_car=car,
            trip_mileage=trip_dist,
            fuel_liters=fuel_liters,
            maintenance_work=works,
            comment="Ремонт завершен. Автомобиль возвращен на парковку."
        )
    return redirect(f'/cars/?car_id={car.id}')

# --- 3. ИСТОРИЯ (С ПАГИНАЦИЕЙ) ---
@login_required
def history_list(request):
    # Исключаем действия с автомобилями из общей истории
    logs_qs = MovementLog.objects.exclude(
        action_type__in=[
            'CAR_ISSUE', 'CAR_RETURN', 
            'CAR_TO_MAINT', 'CAR_FROM_MAINT',
            'CAR_TO_TI', 'CAR_FROM_TI'
        ]
    ).order_by('-date')
    
    employees = User.objects.all().order_by('username')
    
    # Фильтры
    search = request.GET.get('search', '')
    emp_id = request.GET.get('employee', '')
    d_from = request.GET.get('date_from', '')
    d_to = request.GET.get('date_to', '')

    if search: logs_qs = logs_qs.filter(Q(nomenclature_name__icontains=search)|Q(serial_number__icontains=search))
    if emp_id: logs_qs = logs_qs.filter(Q(source_user_id=emp_id)|Q(target_user_id=emp_id)|Q(initiator_id=emp_id))
    if d_from: logs_qs = logs_qs.filter(date__gte=d_from)
    if d_to: logs_qs = logs_qs.filter(date__lte=d_to)

    # ПАГИНАЦИЯ (10 записей на страницу)
    paginator = Paginator(logs_qs, 10) 
    page_number = request.GET.get('page')
    logs_page = paginator.get_page(page_number)

    context = {'logs': logs_page, 'employees': employees}
    
    # AJAX-проверка
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory/history_content.html', context)

    return render(request, 'inventory/history.html', context)

# --- 4. ОСТАЛЬНЫЕ ФУНКЦИИ (БЕЗ ИЗМЕНЕНИЙ) ---
@staff_member_required
def bulk_issue(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            employee_id = data.get('employee_id')
            items = data.get('items', [])
            user = get_object_or_404(User, pk=employee_id)
            
            for item in items:
                type_ = item['type']
                id_ = item['id']
                
                if type_ == 'tool':
                    tool = ToolInstance.objects.get(pk=id_)
                    if tool.status == 'IN_STOCK':
                        # 1. ЗАПОМИНАЕМ СКЛАД ПЕРЕД ВЫДАЧЕЙ
                        wh_was = tool.current_warehouse
                        
                        tool.current_holder = user
                        tool.current_warehouse = None
                        tool.status = 'ISSUED'
                        tool.save()
                        
                        # 2. ПИШЕМ В ЛОГ ЗАПОМНЕННЫЙ СКЛАД (wh_was)
                        MovementLog.objects.create(
                            initiator=request.user, 
                            action_type='ISSUE', 
                            nomenclature=tool.nomenclature, 
                            tool_instance=tool, 
                            source_warehouse=wh_was, # <--- БЫЛО tool.current_warehouse (пусто), СТАЛО wh_was
                            target_user=user, 
                            comment="Массовая выдача"
                        )

                elif type_ == 'consumable':
                    qty = int(item['qty'])
                    balance = ConsumableBalance.objects.get(pk=id_)
                    if balance.quantity >= qty:
                        # Запоминаем склад расходника
                        wh_was = balance.warehouse 
                        
                        balance.quantity -= qty
                        balance.save()
                        
                        target_bal, _ = ConsumableBalance.objects.get_or_create(
                            nomenclature=balance.nomenclature, 
                            holder=user, 
                            defaults={'quantity': 0}
                        )
                        target_bal.quantity += qty
                        target_bal.save()
                        
                        MovementLog.objects.create(
                            initiator=request.user, 
                            action_type='ISSUE', 
                            nomenclature=balance.nomenclature, 
                            quantity=qty, 
                            source_warehouse=wh_was, # Пишем склад
                            target_user=user, 
                            comment=f"Массовая выдача ({qty} шт)"
                        )
                        
                        if balance.quantity == 0: balance.delete()

            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    # GET-запрос (отрисовка страницы) остается без изменений
    tools_qs = ToolInstance.objects.filter(status='IN_STOCK', kit__isnull=True, car__isnull=True)
    tools_data = [{'id': t.id, 'type': 'tool', 'name': t.nomenclature.name, 'art': t.nomenclature.article, 'sn': t.inventory_id, 'wh_id': t.current_warehouse.id} for t in tools_qs]
    cons_qs = ConsumableBalance.objects.filter(warehouse__isnull=False)
    cons_data = [{'id': c.id, 'type': 'consumable', 'name': c.nomenclature.name, 'art': c.nomenclature.article, 'max_qty': c.quantity, 'wh_id': c.warehouse.id} for c in cons_qs]

    context = {'employees': User.objects.filter(is_active=True), 'warehouses': Warehouse.objects.all(), 'tools_json': json.dumps(tools_data), 'consumables_json': json.dumps(cons_data)}
    return render(request, 'inventory/bulk_issue.html', context)

@staff_member_required
def get_employee_items(request, employee_id):
    user = get_object_or_404(User, pk=employee_id)
    data = {
        # ИЗМЕНЕНО: Формат имени без "Арт:" и скобок
        'tools': [{'id': t.id, 'name': f"{t.nomenclature.name} {t.nomenclature.article}", 'sn': t.inventory_id} for t in ToolInstance.objects.filter(current_holder=user)],
        'consumables': [{'id': c.id, 'name': f"{c.nomenclature.name} {c.nomenclature.article}", 'qty': c.quantity} for c in ConsumableBalance.objects.filter(holder=user)],
    }
    return JsonResponse(data)

@staff_member_required
def api_return_item(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_type, item_id, wh_id = data.get('type'), data.get('id'), data.get('warehouse_id')
            target_wh = get_object_or_404(Warehouse, pk=wh_id)
            if item_type == 'tool':
                tool = ToolInstance.objects.get(pk=item_id)
                if tool.current_holder:
                    MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature=tool.nomenclature, nomenclature_name=tool.nomenclature.name, nomenclature_article=tool.nomenclature.article, serial_number=tool.inventory_id, source_user=tool.current_holder, target_warehouse=target_wh, comment=data.get('comment', ''))
                    tool.current_holder = None; tool.current_warehouse = target_wh; tool.status = 'IN_STOCK'; tool.save()
            elif item_type == 'consumable':
                qty = int(data.get('qty', 1)); balance = ConsumableBalance.objects.get(pk=item_id)
                if balance.quantity >= qty:
                    balance.quantity -= qty; balance.save()
                    wh_bal, _ = ConsumableBalance.objects.get_or_create(nomenclature=balance.nomenclature, warehouse=target_wh, defaults={'quantity': 0})
                    wh_bal.quantity += qty; wh_bal.save()
                    MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature=balance.nomenclature, nomenclature_name=balance.nomenclature.name, nomenclature_article=balance.nomenclature.article, quantity=qty, source_user=balance.holder, target_warehouse=target_wh, comment=data.get('comment', ''))
                    if balance.quantity == 0: balance.delete()
            return JsonResponse({'status': 'ok'})
        except Exception as e: return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=405)

@staff_member_required
def api_writeoff_item(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            item_type, item_id, comment = data.get('type'), data.get('id'), data.get('comment', 'Списание')
            if item_type == 'tool':
                tool = ToolInstance.objects.get(pk=item_id)
                MovementLog.objects.create(initiator=request.user, action_type='WRITEOFF', nomenclature=tool.nomenclature, nomenclature_name=tool.nomenclature.name, nomenclature_article=tool.nomenclature.article, serial_number=tool.inventory_id, source_user=tool.current_holder, comment=f"СПИСАНИЕ. Причина: {comment}"); tool.delete()
            elif item_type == 'consumable':
                qty = int(data.get('qty', 1)); balance = ConsumableBalance.objects.get(pk=item_id)
                if balance.quantity >= qty:
                    balance.quantity -= qty; balance.save()
                    MovementLog.objects.create(initiator=request.user, action_type='WRITEOFF', nomenclature=balance.nomenclature, quantity=qty, source_warehouse=balance.warehouse, source_user=balance.holder, nomenclature_name=balance.nomenclature.name, nomenclature_article=balance.nomenclature.article, comment=f"СПИСАНИЕ {qty} шт. Причина: {comment}")
                    if balance.quantity == 0: balance.delete()
            return JsonResponse({'status': 'ok'})
        except Exception as e: return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=405)

@staff_member_required
def tool_add(request):
    if request.method == 'POST':
        form = ToolInstanceForm(request.POST)
        if form.is_valid():
            nomenclature = form.cleaned_data['nomenclature']
            warehouse = form.cleaned_data['current_warehouse']
            qty = form.cleaned_data['quantity']
            
            if nomenclature.item_type == 'TOOL':
                inv_id = form.cleaned_data['inventory_id']
                if not inv_id:
                    form.add_error('inventory_id', 'Обязателен S/N!')
                    nom_types = {n.id: n.item_type for n in Nomenclature.objects.all()}
                    return render(request, 'inventory/tool_add.html', {'form': form, 'nomenclature_types_json': json.dumps(nom_types)})
                
                tool = form.save(commit=False)
                # АВТОМАТИЧЕСКИЕ ПОЛЯ:
                tool.purchase_date = date.today() # Дата покупки = Сегодня
                tool.status = 'IN_STOCK'          # Статус = На складе
                tool.save()
                
                MovementLog.objects.create(initiator=request.user, action_type='RECEIPT', nomenclature=nomenclature, tool_instance=tool, target_warehouse=warehouse, comment="Приход")
                messages.success(request, f"✅ Инструмент «{nomenclature.name}» успешно принят!")
            
            else:
                # Для расходников состояние не важно, оно просто суммируется
                balance, _ = ConsumableBalance.objects.get_or_create(nomenclature=nomenclature, warehouse=warehouse, defaults={'quantity': 0})
                balance.quantity += qty
                balance.save()
                MovementLog.objects.create(initiator=request.user, action_type='RECEIPT', nomenclature=nomenclature, target_warehouse=warehouse, quantity=qty, comment=f"Приход ({qty} шт)")
                messages.success(request, f"✅ Расходник «{nomenclature.name}» пополнен на {qty} шт.")
            
            return redirect('tool_add') 

    else:
        form = ToolInstanceForm()
        
    nom_types = {n.id: n.item_type for n in Nomenclature.objects.all()}
    return render(request, 'inventory/tool_add.html', {'form': form, 'nomenclature_types_json': json.dumps(nom_types)})

@staff_member_required
def tool_edit(request, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    if request.method == 'POST':
        form = ToolInstanceForm(request.POST, instance=tool)
        if form.is_valid(): form.save(); return redirect('index')
    else: form = ToolInstanceForm(instance=tool)
    return render(request, 'inventory/tool_edit.html', {'form': form, 'tool': tool})

@staff_member_required
def tool_issue(request, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    if request.method == 'POST':
        user = get_object_or_404(User, pk=request.POST.get('employee_id'))
        if tool.status == 'IN_STOCK':
            MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=tool.nomenclature, tool_instance=tool, source_warehouse=tool.current_warehouse, target_user=user, comment="Выдача сайт")
            tool.current_holder = user; tool.current_warehouse = None; tool.status = 'ISSUED'; tool.save()
    return redirect('index')

@staff_member_required
def tool_return(request, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    if request.method == 'POST':
        wh = get_object_or_404(Warehouse, pk=request.POST.get('warehouse_id'))
        if tool.status in ['ISSUED', 'LOST']:
            MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature=tool.nomenclature, tool_instance=tool, source_user=tool.current_holder, target_warehouse=wh, comment="Возврат сайт")
            tool.current_warehouse = wh; tool.current_holder = None; tool.status = 'IN_STOCK'; tool.save()
    return redirect('index')

@staff_member_required
def tool_writeoff(request, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    if request.method == 'POST':
        reason = request.POST.get('reason', 'Списание')
        MovementLog.objects.create(initiator=request.user, action_type='WRITEOFF', nomenclature=tool.nomenclature, nomenclature_name=tool.nomenclature.name, nomenclature_article=tool.nomenclature.article, serial_number=tool.inventory_id, source_warehouse=tool.current_warehouse, source_user=tool.current_holder, comment=f"Причина: {reason}"); tool.delete()
    return redirect('index')

@staff_member_required
def consumable_issue(request, pk):
    balance = get_object_or_404(ConsumableBalance, pk=pk)
    if request.method == 'POST':
        user = get_object_or_404(User, pk=request.POST.get('employee_id'))
        qty = int(request.POST.get('quantity', 0))
        if qty > 0 and balance.quantity >= qty:
            balance.quantity -= qty; balance.save()
            target, _ = ConsumableBalance.objects.get_or_create(nomenclature=balance.nomenclature, holder=user, defaults={'quantity': 0})
            target.quantity += qty; target.save()
            MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=balance.nomenclature, quantity=qty, source_warehouse=balance.warehouse, target_user=user, comment=f"Выдача {qty} шт.")
            if balance.quantity == 0: balance.delete()
    return redirect('index')

@staff_member_required
def consumable_return(request, pk):
    balance = get_object_or_404(ConsumableBalance, pk=pk)
    if request.method == 'POST':
        wh = get_object_or_404(Warehouse, pk=request.POST.get('warehouse_id'))
        qty = int(request.POST.get('quantity', 0))
        if qty > 0 and balance.quantity >= qty:
            balance.quantity -= qty; balance.save()
            target, _ = ConsumableBalance.objects.get_or_create(nomenclature=balance.nomenclature, warehouse=wh, defaults={'quantity': 0})
            target.quantity += qty; target.save()
            MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature=balance.nomenclature, quantity=qty, source_user=balance.holder, target_warehouse=wh, comment=f"Возврат {qty} шт.")
            if balance.quantity == 0: balance.delete()
    return redirect('index')

@staff_member_required
def consumable_writeoff(request, pk):
    balance = get_object_or_404(ConsumableBalance, pk=pk)
    if request.method == 'POST':
        qty = int(request.POST.get('quantity', 0))
        reason = request.POST.get('reason', 'Списание')
        if qty > 0 and balance.quantity >= qty:
            balance.quantity -= qty; balance.save()
            MovementLog.objects.create(initiator=request.user, action_type='WRITEOFF', nomenclature=balance.nomenclature, quantity=qty, source_warehouse=balance.warehouse, source_user=balance.holder, nomenclature_name=balance.nomenclature.name, nomenclature_article=balance.nomenclature.article, comment=f"СПИСАНИЕ {qty} шт. Причина: {reason}")
            if balance.quantity == 0: balance.delete()
    return redirect('index')

# --- 6. КОМПЛЕКТЫ ---
@login_required
def kit_list(request):
    kits = ToolKit.objects.all()
    selected_kit = None
    available_tools = None
    available_consumables = None
    edit_form = None

    kit_id = request.GET.get('kit_id')
    if kit_id:
        selected_kit = get_object_or_404(ToolKit, pk=kit_id)
        edit_form = ToolKitForm(instance=selected_kit)
        
        # Если у комплекта есть склад приписки, показываем товары ТОЛЬКО с этого склада
        if selected_kit.warehouse:
            # Инструменты: на складе, не в комплекте, не в машине
            available_tools = ToolInstance.objects.filter(
                current_warehouse=selected_kit.warehouse, # <--- ПРОВЕРКА СКЛАДА
                kit__isnull=True, 
                car__isnull=True, 
                status='IN_STOCK'
            )
            # Расходники: на этом же складе
            available_consumables = ConsumableBalance.objects.filter(
                warehouse=selected_kit.warehouse,
                quantity__gt=0
            )
        else:
            # Если склад не указан - ничего не показываем (или можно все, но это риск)
            available_tools = []
            available_consumables = []

    context = {
        'kits': kits,
        'selected_kit': selected_kit,
        'available_tools': available_tools,
        'available_consumables': available_consumables,
        'employees': User.objects.filter(is_active=True),
        'form': ToolKitForm(),
        'edit_form': edit_form
    }
    
    # AJAX: Возвращаем только контент
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory/kits_content.html', context)

    return render(request, 'inventory/kits.html', context)

@staff_member_required
def kit_create(request):
    if request.method == 'POST':
        form = ToolKitForm(request.POST)
        if form.is_valid(): kit = form.save(); return redirect(f'/kits/?kit_id={kit.id}')
    return redirect('kit_list')

@staff_member_required
def kit_edit(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    old_wh = kit.warehouse
    if request.method == 'POST':
        form = ToolKitForm(request.POST, instance=kit)
        if form.is_valid():
            new_kit = form.save()
            if old_wh != new_kit.warehouse:
                MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature_name=kit.name, nomenclature_article="КОМПЛЕКТ", source_warehouse=old_wh, target_warehouse=new_kit.warehouse, comment=f"Перемещение комплекта")
                # При смене склада комплекта, инструменты внутри НЕ меняют склад физически (они "в комплекте"),
                # но если мы хотим, чтобы они "переехали" - можно обновить.
                # Логика: пока они в комплекте, warehouse=None. При возврате вернутся на новый склад.
            return redirect(f'/kits/?kit_id={kit.id}')
    return redirect('kit_list')

@login_required # <--- ТЕПЕРЬ ДОСТУПНО ВСЕМ
def kit_add_tool(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        tool = get_object_or_404(ToolInstance, pk=request.POST.get('tool_id'))
        
        # Проверка: инструмент должен быть на том же складе, что и комплект
        if tool.current_warehouse != kit.warehouse:
            # Можно добавить сообщение об ошибке через messages
            return redirect(f'/kits/?kit_id={kit.id}')

        wh_was = tool.current_warehouse
        
        # Инструмент "уходит" со склада в комплект
        tool.current_warehouse = None 
        tool.kit = kit
        tool.save()
        
        MovementLog.objects.create(
            initiator=request.user,
            action_type='ISSUE', 
            nomenclature=tool.nomenclature, 
            tool_instance=tool, 
            source_warehouse=wh_was, 
            target_kit=kit, 
            comment=f"Добавлен в комплект: {kit.name}"
        )
    return redirect(f'/kits/?kit_id={kit.id}')

@login_required # <--- ТЕПЕРЬ ДОСТУПНО ВСЕМ
def kit_remove_tool(request, kit_id, tool_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    if request.method == 'POST':
        comment = request.POST.get('comment', '')
        # Возвращаем на склад приписки комплекта
        target_wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()
        
        tool.kit = None
        tool.current_warehouse = target_wh
        tool.status = 'IN_STOCK'
        tool.save()
        
        MovementLog.objects.create(
            initiator=request.user, 
            action_type='RETURN', 
            nomenclature=tool.nomenclature, 
            tool_instance=tool, 
            source_kit=kit, 
            target_warehouse=target_wh, 
            comment=f"Изъят из комплекта: {kit.name}. {comment}"
        )
    return redirect(f'/kits/?kit_id={kit.id}')

# --- РАСХОДНИКИ В КОМПЛЕКТАХ (НОВЫЕ ФУНКЦИИ) ---

@login_required
def kit_add_consumable(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        balance_id = request.POST.get('balance_id')
        qty = int(request.POST.get('quantity', 0))
        
        # Ищем расходник на складе
        source_bal = get_object_or_404(ConsumableBalance, pk=balance_id)
        
        # Проверка склада
        if source_bal.warehouse != kit.warehouse:
            return redirect(f'/kits/?kit_id={kit.id}')

        if qty > 0 and source_bal.quantity >= qty:
            # Списываем со склада
            source_bal.quantity -= qty
            source_bal.save()
            
            # Добавляем в комплект
            target_bal, _ = ConsumableBalance.objects.get_or_create(
                nomenclature=source_bal.nomenclature,
                kit=kit,
                defaults={'quantity': 0}
            )
            target_bal.quantity += qty
            target_bal.save()
            
            MovementLog.objects.create(
                initiator=request.user, 
                action_type='ISSUE', 
                nomenclature=source_bal.nomenclature, 
                quantity=qty,
                source_warehouse=source_bal.warehouse, 
                target_kit=kit, 
                comment=f"Добавлен в комплект: {kit.name}"
            )
            if source_bal.quantity == 0: source_bal.delete()
            
    return redirect(f'/kits/?kit_id={kit.id}')

@login_required
def kit_remove_consumable(request, kit_id, balance_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        kit_bal = get_object_or_404(ConsumableBalance, pk=balance_id)
        qty = int(request.POST.get('quantity', 0))
        comment = request.POST.get('comment', '')
        
        target_wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()

        if qty > 0 and kit_bal.quantity >= qty:
            kit_bal.quantity -= qty
            kit_bal.save()
            
            wh_bal, _ = ConsumableBalance.objects.get_or_create(
                nomenclature=kit_bal.nomenclature,
                warehouse=target_wh,
                defaults={'quantity': 0}
            )
            wh_bal.quantity += qty
            wh_bal.save()
            
            MovementLog.objects.create(
                initiator=request.user, 
                action_type='RETURN', 
                nomenclature=kit_bal.nomenclature, 
                quantity=qty,
                source_kit=kit, 
                target_warehouse=target_wh, 
                comment=f"Изъят из комплекта. {comment}"
            )
            if kit_bal.quantity == 0: kit_bal.delete()
            
    return redirect(f'/kits/?kit_id={kit.id}')

@staff_member_required
def kit_delete(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        # Возвращаем инструменты на склад (или оставляем висеть, но лучше вернуть)
        wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()
        for t in kit.tools.all(): 
            t.kit = None
            t.current_warehouse = wh
            t.status = 'IN_STOCK'
            t.save()
        # Расходники в комплекте просто удаляются (или можно вернуть, но это сложнее)
        # Пока просто удаляем связи
        kit.delete()
    return redirect('kit_list')

@login_required
def kit_issue(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        user = get_object_or_404(User, pk=request.POST.get('employee_id'))
        kit.current_holder = user; kit.status = 'ISSUED'; kit.save()
        
        # Инструменты: меняем статус и владельца
        for t in kit.tools.all(): 
            t.current_holder = user
            t.status = 'ISSUED'
            t.save()
            
        # Расходники остаются "в комплекте", но комплект теперь у сотрудника
        # Дополнительных действий с ConsumableBalance не требуется, они привязаны к kit_id
        
        MovementLog.objects.create(initiator=request.user, action_type='KIT_ISSUE', nomenclature_name=kit.name, nomenclature_article="КОМПЛЕКТ", source_warehouse=kit.warehouse, target_user=user, comment=request.POST.get('comment', ''))
    return redirect(f'/kits/?kit_id={kit.id}')

@login_required
def kit_return(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()
        holder_was = kit.current_holder
        kit.current_holder = None; kit.status = 'IN_STOCK'; kit.save()
        
        for t in kit.tools.all(): 
            t.current_holder = None
            # Инструменты НЕ возвращаются на склад физически, они остаются В КОМПЛЕКТЕ
            # Но комплект теперь на складе.
            # tool.current_warehouse = None (так как он внутри комплекта)
            t.status = 'IN_STOCK'
            t.save()
            
        MovementLog.objects.create(initiator=request.user, action_type='KIT_RETURN', nomenclature_name=kit.name, nomenclature_article="КОМПЛЕКТ", source_user=holder_was, target_warehouse=wh, comment=request.POST.get('comment', ''))
    return redirect(f'/kits/?kit_id={kit.id}')

@staff_member_required
def nomenclature_list(request):
    # 1. Получаем все записи
    items_qs = Nomenclature.objects.all().order_by('name')
    
    # 2. Обработка формы добавления
    if request.method == 'POST':
        form = NomenclatureForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "✅ Номенклатура успешно добавлена!")
            return redirect('nomenclature_list')
    else:
        form = NomenclatureForm()

    # 3. Пагинация (10 штук на страницу)
    paginator = Paginator(items_qs, 10)
    page_number = request.GET.get('page')
    items_page = paginator.get_page(page_number)

    context = {'items': items_page, 'form': form}

    # 4. Если это AJAX запрос - отдаем только таблицу
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory/nomenclature_list_content.html', context)
        
    # 5. Иначе отдаем полную страницу
    return render(request, 'inventory/nomenclature_list.html', context)

@staff_member_required
def nomenclature_edit(request, pk):
    item = get_object_or_404(Nomenclature, pk=pk)
    if request.method == 'POST':
        form = NomenclatureForm(request.POST, instance=item)
        if form.is_valid(): form.save(); return redirect('nomenclature_list')
    else: form = NomenclatureForm(instance=item)
    return render(request, 'inventory/nomenclature_edit.html', {'form': form, 'item': item})

@staff_member_required
def nomenclature_delete(request, pk):
    item = get_object_or_404(Nomenclature, pk=pk)
    if request.method == 'POST': item.delete()
    return redirect('nomenclature_list')

@login_required
def warehouse_list(request):
    return render(request, 'inventory/warehouse_list.html', {'warehouses': Warehouse.objects.all()})

@staff_member_required
def warehouse_add(request):
    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid(): form.save(); return redirect('warehouse_list')
    else: form = WarehouseForm()
    return render(request, 'inventory/warehouse_form.html', {'form': form, 'title': 'Добавить склад'})

@staff_member_required
def warehouse_edit(request, pk):
    wh = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=wh)
        if form.is_valid(): form.save(); return redirect('warehouse_list')
    else: form = WarehouseForm(instance=wh)
    return render(request, 'inventory/warehouse_form.html', {'form': form, 'title': f'Редактирование: {wh.name}'})

@staff_member_required
def warehouse_delete(request, pk):
    wh = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST': wh.delete()
    return redirect('warehouse_list')

@staff_member_required
def print_barcodes(request):
    return render(request, 'inventory/print_barcodes.html', {'tools': ToolInstance.objects.all()})

@staff_member_required
def quick_return(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            target_wh = get_object_or_404(Warehouse, pk=data.get('warehouse_id'))
            for sn in data.get('sn_list', []):
                try:
                    tool = ToolInstance.objects.get(inventory_id=sn)
                    if tool.status == 'IN_STOCK': continue
                    holder_was = tool.current_holder
                    tool.current_holder = None; tool.current_warehouse = target_wh; tool.status = 'IN_STOCK'; tool.save()
                    MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature=tool.nomenclature, nomenclature_name=tool.nomenclature.name, nomenclature_article=tool.nomenclature.article, serial_number=tool.inventory_id, tool_instance=tool, source_user=holder_was, target_warehouse=target_wh, comment=f"Быстрый возврат (сканер). {data.get('comment', '')}")
                except ToolInstance.DoesNotExist: continue
            return JsonResponse({'status': 'ok'})
        except Exception as e: return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    issued_tools = ToolInstance.objects.exclude(status='IN_STOCK')
    tools_data = []
    for t in issued_tools:
        holder = f"{t.current_holder.first_name} {t.current_holder.last_name}" if t.current_holder else (f"Комплект: {t.kit.name}" if t.kit else "Неизвестно")
        tools_data.append({'sn': t.inventory_id, 'name': t.nomenclature.name, 'holder': holder})
    return render(request, 'inventory/quick_return.html', {'warehouses': Warehouse.objects.all(), 'issued_tools_json': json.dumps(tools_data)})

@staff_member_required
def employee_list(request):
    employees = User.objects.all().order_by('username')
    return render(request, 'inventory/employee_list.html', {'employees': employees})

@staff_member_required
def employee_add(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            new_pwd = form.cleaned_data.get('new_password')
            if new_pwd: user.set_password(new_pwd)
            else: user.set_password('123456')
            user.save()
            return redirect('employee_list')
    else: form = EmployeeForm()
    return render(request, 'inventory/employee_add.html', {'form': form})

@staff_member_required
def employee_edit(request, user_id):
    employee = get_object_or_404(User, pk=user_id)
    if request.method == 'POST':
        form = EmployeeForm(request.POST, instance=employee)
        if form.is_valid():
            user = form.save(commit=False)
            new_pwd = form.cleaned_data.get('new_password')
            if new_pwd: user.set_password(new_pwd)
            user.save()
            return redirect('employee_list')
    else: form = EmployeeForm(instance=employee)
    return render(request, 'inventory/form_edit.html', {'form': form, 'title': f'Редактирование: {employee.username}'})
 
#Удаление пользователей
@staff_member_required
def employee_delete(request, user_id):
    """Удаление сотрудника"""
    user_to_delete = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        # Защита: Нельзя удалить самого себя
        if user_to_delete.id == request.user.id:
            return redirect('employee_list')
            
        user_to_delete.delete()
        
    return redirect('employee_list')