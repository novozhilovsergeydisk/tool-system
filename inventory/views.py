import json
from datetime import date, timedelta
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q, Sum
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.contrib import messages
from .models import Nomenclature, ToolInstance, Warehouse, MovementLog, ConsumableBalance, ToolKit, Car, News
from .forms import NomenclatureForm, EmployeeForm, ToolInstanceForm, ToolKitForm, WarehouseForm, CarForm, NewsForm
from itertools import chain

# ==========================================
# 1. ДАШБОРД (ГЛАВНАЯ)
# ==========================================
@login_required
def index(request):
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
    
    # Алерты (только для админов)
    alerts = []
    if request.user.is_staff:
        # 1. АВТОМОБИЛИ (Группировка проблем)
        cars = Car.objects.all()
        for car in cars:
            car_issues = []
            has_critical = False
            
            # Страховка
            if car.insurance_expiry and car.insurance_expiry <= warning_date:
                days_left = (car.insurance_expiry - today).days
                if days_left < 0:
                    car_issues.append(f"Страховка: ИСТЕКЛА ({abs(days_left)} дн. назад)")
                    has_critical = True
                else:
                    car_issues.append(f"Страховка: истекает через {days_left} дн.")
            
            # ТО (Масло)
            if car.service_status != 'ok':
                km = car.km_to_service
                if km < 0:
                    car_issues.append(f"ТО: Просрочено на {abs(km)} км")
                    has_critical = True
                else:
                    car_issues.append(f"ТО: Осталось {km} км")

            # Техосмотр
            if car.is_truck and car.ti_status != 'ok':
                if car.ti_status == 'danger':
                    car_issues.append("Техосмотр: ПРОСРОЧЕН!")
                    has_critical = True
                else:
                    car_issues.append("Техосмотр: Скоро подходит срок")

            if car_issues:
                alerts.append({
                    'type': 'danger' if has_critical else 'warning',
                    'icon': 'fa-car',
                    'text': f"{car.name} ({car.license_plate})",
                    'details_list': car_issues,
                    'link': f"/cars/?car_id={car.id}"
                })

        # 2. РАСХОДНИКИ (Группировка по складам)
        stock_problems = {}
        balances = ConsumableBalance.objects.filter(nomenclature__minimum_stock__gt=0, warehouse__isnull=False).select_related('nomenclature', 'warehouse')

        for bal in balances:
            if bal.quantity <= bal.nomenclature.minimum_stock:
                wh_name = bal.warehouse.name
                if wh_name not in stock_problems: stock_problems[wh_name] = []
                stock_problems[wh_name].append(f"{bal.nomenclature.name} {bal.nomenclature.article} (Осталось {bal.quantity})")
        
        for wh_name, items_list in stock_problems.items():
            alerts.append({
                'type': 'warning', 
                'icon': 'fa-boxes-packing',
                'text': f"На складе «{wh_name}» заканчиваются:",
                'details_list': items_list, 
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

# ==========================================
# 2. НОВОСТИ
# ==========================================
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

# --- 3. СПИСОК ТОВАРОВ ---
@login_required
def tool_list(request):
    """Единая таблица всех товаров"""
    from django.db.models import Q
    from itertools import chain

    # 1. Базовые запросы
    # Инструменты: исключаем те, что в машинах
    tools = ToolInstance.objects.filter(car__isnull=True).select_related('nomenclature', 'current_warehouse', 'current_holder', 'kit')
    # Расходники: исключаем те, что в комплектах (они спрятаны в чемоданах)
    consumables = ConsumableBalance.objects.filter(kit__isnull=True).select_related('nomenclature', 'warehouse', 'holder')
    
    # Данные для фильтров (для подсказок)
    employees = User.objects.filter(is_active=True).order_by('username')
    warehouses = Warehouse.objects.all().order_by('name')

    # 2. Фильтрация
    search = request.GET.get('search', '').strip()
    wh_id = request.GET.get('warehouse', '')
    emp_query = request.GET.get('employee', '').strip() # Получаем ТЕКСТ, а не ID
    type_filter = request.GET.get('item_type', '')
    status_filter = request.GET.get('status', '')

    # ПОИСК (Добавили поиск по Названию Комплекта)
    if search:
        # Инструменты: Имя, Инв.№, Артикул ИЛИ Название комплекта
        tools = tools.filter(
            Q(nomenclature__name__icontains=search) | 
            Q(inventory_id__icontains=search) | 
            Q(nomenclature__article__icontains=search) |
            Q(kit__name__icontains=search) # <--- Ищем товары по названию их комплекта
        )
        # Расходники: Имя, Артикул (у них нет комплектов в этом списке)
        consumables = consumables.filter(
            Q(nomenclature__name__icontains=search) | 
            Q(nomenclature__article__icontains=search)
        )
    
    # Фильтр по СКЛАДУ
    if wh_id:
        tools = tools.filter(current_warehouse_id=wh_id)
        consumables = consumables.filter(warehouse_id=wh_id)
    
    # Фильтр по СОТРУДНИКУ (Теперь текстовый поиск)
    if emp_query:
        users_found = User.objects.filter(
            Q(username__icontains=emp_query) | 
            Q(first_name__icontains=emp_query) | 
            Q(last_name__icontains=emp_query)
        )
        tools = tools.filter(current_holder__in=users_found)
        consumables = consumables.filter(holder__in=users_found)

    # Фильтр по ТИПУ
    if type_filter:
        if type_filter == 'CONSUMABLE':
            tools = tools.none()
        else:
            tools = tools.filter(nomenclature__item_type=type_filter)
            consumables = consumables.none()

    # Фильтр по СТАТУСУ
    if status_filter:
        if status_filter == 'IN_STOCK':
            tools = tools.filter(status='IN_STOCK')
            consumables = consumables.filter(warehouse__isnull=False)
        elif status_filter == 'ISSUED':
            tools = tools.filter(status='ISSUED')
            consumables = consumables.filter(holder__isnull=False)

    # 3. Объединение
    for t in tools: t.row_type = 'tool'
    for c in consumables: c.row_type = 'consumable'

    combined_list = list(chain(tools, consumables))
    combined_list.sort(key=lambda x: x.nomenclature.name.lower())

    # 4. Пагинация
    paginator = Paginator(combined_list, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'items': page_obj,
        'page_obj': page_obj,
        'employees': employees, 
        'warehouses': warehouses
    }
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory/tool_list_content.html', context)

    return render(request, 'inventory/tool_list.html', context)

# ==========================================
# 3.1. ОПЕРАЦИИ С ИНСТРУМЕНТОМ (ЭТОГО НЕ ХВАТАЛО)
# ==========================================
@staff_member_required
def tool_add(request):
    if request.method == 'POST':
        form = ToolInstanceForm(request.POST)
        if form.is_valid():
            nomenclature = form.cleaned_data['nomenclature']
            warehouse = form.cleaned_data['current_warehouse']
            qty = form.cleaned_data['quantity']
            
            # ИСПРАВЛЕНО: Экипировка тоже учитывается поштучно (как TOOL)
            if nomenclature.item_type in ['TOOL', 'EQUIPMENT']:
                inv_id = form.cleaned_data['inventory_id']
                if not inv_id:
                    form.add_error('inventory_id', 'Обязателен S/N!')
                    nom_types = {n.id: n.item_type for n in Nomenclature.objects.all()}
                    return render(request, 'inventory/tool_add.html', {'form': form, 'nomenclature_types_json': json.dumps(nom_types)})
                
                tool = form.save(commit=False)
                tool.purchase_date = date.today()
                tool.status = 'IN_STOCK'
                tool.save()
                
                MovementLog.objects.create(initiator=request.user, action_type='RECEIPT', nomenclature=nomenclature, tool_instance=tool, target_warehouse=warehouse, comment="Приход")
                messages.success(request, f"✅ {nomenclature.get_item_type_display()} «{nomenclature.name}» успешно принят!")
            
            else:
                # Расходники
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
        if form.is_valid(): form.save(); return redirect('tool_list')
    else: form = ToolInstanceForm(instance=tool)
    return render(request, 'inventory/tool_edit.html', {'form': form, 'tool': tool})

@staff_member_required
def tool_issue(request, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    if request.method == 'POST':
        # ПРОВЕРКА: Нельзя выдавать сломанное
        if tool.status == 'BROKEN' or tool.condition == 'BROKEN':
            messages.error(request, f"⛔ Нельзя выдать сломанный инструмент: {tool.nomenclature.name}")
            return redirect('tool_list')

        user = get_object_or_404(User, pk=request.POST.get('employee_id'))
        if tool.status == 'IN_STOCK':
            wh_was = tool.current_warehouse
            tool.current_holder = user
            tool.current_warehouse = None
            tool.status = 'ISSUED'
            tool.save()
            MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=tool.nomenclature, tool_instance=tool, source_warehouse=wh_was, target_user=user, comment="Выдача")
    return redirect('tool_list')

@staff_member_required
def tool_return(request, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    if request.method == 'POST':
        wh = get_object_or_404(Warehouse, pk=request.POST.get('warehouse_id'))
        if tool.status in ['ISSUED', 'LOST']:
            MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature=tool.nomenclature, tool_instance=tool, source_user=tool.current_holder, target_warehouse=wh, comment="Возврат")
            tool.current_warehouse = wh
            tool.current_holder = None
            tool.status = 'IN_STOCK'
            tool.save()
    return redirect('tool_list')

@staff_member_required
def tool_writeoff(request, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    if request.method == 'POST':
        reason = request.POST.get('reason', 'Списание')
        MovementLog.objects.create(initiator=request.user, action_type='WRITEOFF', nomenclature=tool.nomenclature, nomenclature_name=tool.nomenclature.name, nomenclature_article=tool.nomenclature.article, serial_number=tool.inventory_id, source_warehouse=tool.current_warehouse, source_user=tool.current_holder, comment=f"Причина: {reason}")
        tool.delete()
    return redirect('tool_list')

@login_required
def tool_take_self(request, tool_id):
    """Сотрудник берет инструмент на себя (с комментарием)"""
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    
    if request.method == 'POST':
        # ПРОВЕРКА: Нельзя брать сломанное
        if tool.status == 'BROKEN' or tool.condition == 'BROKEN':
            messages.error(request, "⛔ Этот инструмент помечен как сломанный, его нельзя взять.")
            return redirect('tool_list')

        if tool.nomenclature.item_type in ['TOOL', 'EQUIPMENT'] and tool.status == 'IN_STOCK':
            wh_was = tool.current_warehouse
            tool.current_holder = request.user
            tool.current_warehouse = None
            tool.status = 'ISSUED'
            tool.save()
            
            user_comment = request.POST.get('comment', '')
            full_comment = f"Взял самостоятельно. {user_comment}"
            
            MovementLog.objects.create(
                initiator=request.user, 
                action_type='ISSUE', 
                nomenclature=tool.nomenclature, 
                tool_instance=tool, 
                source_warehouse=wh_was, 
                target_user=request.user, 
                comment=full_comment
            )
            messages.success(request, f"Вы взяли: {tool.nomenclature.name}")
        
    return redirect('tool_list')

@login_required
def tool_return_self(request, tool_id):
    """Сотрудник возвращает инструмент (с комментарием)"""
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    
    if request.method == 'POST':
        if tool.current_holder == request.user:
            target_wh = Warehouse.objects.first() # Возврат на основной склад
            
            tool.current_holder = None
            tool.current_warehouse = target_wh
            tool.status = 'IN_STOCK'
            tool.save()
            
            user_comment = request.POST.get('comment', '')
            full_comment = f"Вернул самостоятельно. {user_comment}"
            
            MovementLog.objects.create(
                initiator=request.user, 
                action_type='RETURN', 
                nomenclature=tool.nomenclature, 
                tool_instance=tool, 
                source_user=request.user, 
                target_warehouse=target_wh, 
                comment=full_comment
            )
            messages.success(request, f"Вы вернули: {tool.nomenclature.name}")
        
    return redirect('tool_list')

# --- РАСХОДНИКИ (ТОЖЕ ПРОПУЩЕНЫ) ---
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
    return redirect('tool_list')

@staff_member_required
def consumable_return(request, pk):
    balance = get_object_or_404(ConsumableBalance, pk=pk)
    if request.method == 'POST':
        wh = get_object_or_404(Warehouse, pk=request.POST.get('warehouse_id'))
        qty = int(request.POST.get('quantity', 0))
        
        if qty > 0 and balance.quantity >= qty:
            balance.quantity -= qty
            balance.save()
            
            # ИСПРАВЛЕНО: Защита от дублей
            # Ищем ВСЕ записи на этом складе с такой номенклатурой
            target_bals = ConsumableBalance.objects.filter(
                nomenclature=balance.nomenclature, 
                warehouse=wh,
                kit__isnull=True # Важно: ищем только "чистые" остатки, не привязанные к комплектам
            )
            
            if target_bals.exists():
                # Если нашли (одну или много) - берем первую и прибавляем
                target = target_bals.first()
                target.quantity += qty
                target.save()
                
                # (Опционально: можно удалить остальные дубликаты, чтобы почистить базу)
                if target_bals.count() > 1:
                    for dup in target_bals[1:]:
                        # Переносим остатки с дублей на основную запись и удаляем их
                        target.quantity += dup.quantity
                        target.save()
                        dup.delete()
            else:
                # Если не нашли - создаем новую
                ConsumableBalance.objects.create(
                    nomenclature=balance.nomenclature, 
                    warehouse=wh, 
                    quantity=qty
                )

            MovementLog.objects.create(
                initiator=request.user, 
                action_type='RETURN', 
                nomenclature=balance.nomenclature, 
                quantity=qty, 
                source_user=balance.holder, 
                target_warehouse=wh, 
                comment=f"Возврат {qty} шт."
            )
            
            if balance.quantity == 0: balance.delete()
            
    return redirect('tool_list')

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
    return redirect('tool_list')
    
# ==========================================
# 4. АВТОМОБИЛИ
# ==========================================
@login_required
def car_list(request):
    cars = Car.objects.all()
    selected_car = None; edit_form = None; history_trip_page = None; history_maint_page = None
    today = date.today(); warning_date = today + timedelta(days=30)

    if request.GET.get('car_id'):
        selected_car = get_object_or_404(Car, pk=request.GET.get('car_id'))
        edit_form = CarForm(instance=selected_car)
        
        # История поездок (AJAX)
        logs_trips = MovementLog.objects.filter(Q(source_car=selected_car)|Q(target_car=selected_car), action_type__in=['CAR_ISSUE', 'CAR_RETURN']).order_by('-date')
        paginator_trips = Paginator(logs_trips, 10)
        history_trip_page = paginator_trips.get_page(request.GET.get('page_trips'))

        # История ТО (AJAX)
        logs_maint = MovementLog.objects.filter(Q(source_car=selected_car)|Q(target_car=selected_car), action_type__in=['CAR_TO_MAINT', 'CAR_FROM_MAINT', 'CAR_TO_TI', 'CAR_FROM_TI']).order_by('-date')
        paginator_maint = Paginator(logs_maint, 10)
        history_maint_page = paginator_maint.get_page(request.GET.get('page_maint'))

    context = {'cars': cars, 'selected_car': selected_car, 'employees': User.objects.filter(is_active=True), 'form': CarForm(), 'edit_form': edit_form, 'history_trip_page': history_trip_page, 'history_maint_page': history_maint_page, 'today': today, 'warning_date': warning_date}
    
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
        car.status = 'PARKED'; car.current_mileage = end_mileage; car.last_service_mileage = end_mileage; car.save() # Сброс ТО
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
        car.status = 'PARKED'; car.current_mileage = end_mileage; car.last_ti_date = date.today(); car.save() # Обновление даты
        MovementLog.objects.create(initiator=request.user, action_type='CAR_FROM_TI', source_car=car, trip_mileage=trip_dist, fuel_liters=fuel_liters, comment=f"Возврат с Техосмотра. Дата обновлена. Пробег: {trip_dist} км")
    return redirect(f'/cars/?car_id={car.id}')

@staff_member_required
def car_mark_broken(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        car.current_driver = None; car.status = 'BROKEN'; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_TO_MAINT', target_car=car, comment="АВТОМОБИЛЬ СЛОМАН (Помечен администратором)")
    return redirect(f'/cars/?car_id={car.id}')

@staff_member_required
def car_mark_fixed(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        end_mileage = int(request.POST.get('end_mileage', car.current_mileage))
        fuel_liters = int(request.POST.get('fuel_liters', 0)) if request.POST.get('fuel_added') == 'on' else 0
        trip_dist = max(0, end_mileage - car.current_mileage)
        car.status = 'PARKED'; car.current_mileage = end_mileage; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_FROM_MAINT', source_car=car, trip_mileage=trip_dist, fuel_liters=fuel_liters, maintenance_work=request.POST.get('works', ''), comment="Ремонт завершен. Автомобиль возвращен на парковку.")
    return redirect(f'/cars/?car_id={car.id}')

# ==========================================
# 5. КОМПЛЕКТЫ
# ==========================================
@login_required
def kit_list(request):
    kits = ToolKit.objects.all()
    selected_kit = None; available_tools = None; available_consumables = None; edit_form = None
    
    if request.GET.get('kit_id'):
        selected_kit = get_object_or_404(ToolKit, pk=request.GET.get('kit_id'))
        edit_form = ToolKitForm(instance=selected_kit)
        
        if selected_kit.warehouse:
            # ИНСТРУМЕНТЫ:
            # 1. На этом складе
            # 2. kit__isnull=True -> НЕ входит ни в один комплект (свободен)
            # 3. car__isnull=True -> НЕ в машине
            # 4. status='IN_STOCK' -> На полке
            available_tools = ToolInstance.objects.filter(
                current_warehouse=selected_kit.warehouse, 
                kit__isnull=True, # <--- ВОТ ЭТА ПРОВЕРКА ЗАПРЕЩАЕТ ДОБАВЛЯТЬ ЗАНЯТОЕ
                car__isnull=True, 
                status='IN_STOCK'
            )
            
            # РАСХОДНИКИ:
            # Тоже только свободные (не в комплектах)
            available_consumables = ConsumableBalance.objects.filter(
                warehouse=selected_kit.warehouse, 
                kit__isnull=True, 
                quantity__gt=0
            )
        else: 
            available_tools = []; available_consumables = []
    
    context = {
        'kits': kits, 
        'selected_kit': selected_kit, 
        'available_tools': available_tools, 
        'available_consumables': available_consumables, 
        'employees': User.objects.filter(is_active=True), 
        'form': ToolKitForm(), 
        'edit_form': edit_form
    }
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
            if old_wh != new_kit.warehouse: MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature_name=kit.name, nomenclature_article="КОМПЛЕКТ", source_warehouse=old_wh, target_warehouse=new_kit.warehouse, comment=f"Перемещение комплекта")
            return redirect(f'/kits/?kit_id={kit.id}')
    return redirect('kit_list')

@login_required
def kit_add_tool(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        tool = get_object_or_404(ToolInstance, pk=request.POST.get('tool_id'))
        
        # ПРОВЕРКА: Нельзя добавлять сломанное в комплект
        if tool.status == 'BROKEN' or tool.condition == 'BROKEN':
            messages.error(request, f"⛔ Нельзя добавить сломанный инструмент в комплект: {tool.nomenclature.name}")
            return redirect(f'/kits/?kit_id={kit.id}')

        if tool.current_warehouse != kit.warehouse: return redirect(f'/kits/?kit_id={kit.id}')
        tool.kit = kit; tool.save() 
    return redirect(f'/kits/?kit_id={kit.id}')

@login_required
def kit_remove_tool(request, kit_id, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    if request.method == 'POST': tool.kit = None; tool.save()
    return redirect(f'/kits/?kit_id={kit_id}')

@login_required
def kit_add_consumable(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        balance_id = request.POST.get('balance_id'); qty = int(request.POST.get('quantity', 0))
        source_bal = get_object_or_404(ConsumableBalance, pk=balance_id)
        if source_bal.warehouse != kit.warehouse: return redirect(f'/kits/?kit_id={kit.id}')
        if qty > 0 and source_bal.quantity >= qty:
            source_bal.quantity -= qty; source_bal.save()
            target_bal, _ = ConsumableBalance.objects.get_or_create(nomenclature=source_bal.nomenclature, kit=kit, defaults={'quantity': 0})
            target_bal.quantity += qty; target_bal.save()
            if source_bal.quantity == 0: source_bal.delete()
    return redirect(f'/kits/?kit_id={kit.id}')

@login_required
def kit_remove_consumable(request, kit_id, balance_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        kit_bal = get_object_or_404(ConsumableBalance, pk=balance_id)
        qty = int(request.POST.get('quantity', 0))
        target_wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()
        if qty > 0 and kit_bal.quantity >= qty:
            kit_bal.quantity -= qty; kit_bal.save()
            wh_bal, _ = ConsumableBalance.objects.get_or_create(nomenclature=kit_bal.nomenclature, warehouse=target_wh, defaults={'quantity': 0})
            wh_bal.quantity += qty; wh_bal.save()
            if kit_bal.quantity == 0: kit_bal.delete()
    return redirect(f'/kits/?kit_id={kit.id}')

@staff_member_required
def kit_delete(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()
        for t in kit.tools.all(): t.kit = None; t.current_warehouse = wh; t.status = 'IN_STOCK'; t.save()
        kit.delete()
    return redirect('kit_list')

@login_required
def kit_issue(request, kit_id):
    """ВЫДАЧА: Расходники перемещаются к сотруднику, но остаются ПРИВЯЗАНЫ к комплекту"""
    kit = get_object_or_404(ToolKit, pk=kit_id)
    
    if request.method == 'POST':
        user = get_object_or_404(User, pk=request.POST.get('employee_id'))
        
        selected_tools_ids = set(request.POST.getlist('tools_selected'))
        selected_cons_ids = set(request.POST.getlist('cons_selected'))
        partner_ids = request.POST.getlist('partner_ids')
        
        log_items = []

        # 1. ИНСТРУМЕНТЫ
        for tool in kit.tools.all():
            if str(tool.id) in selected_tools_ids:
                # БЕРУТ: Передаем сотруднику
                tool.current_holder = user
                tool.current_warehouse = None
                tool.status = 'ISSUED'
                tool.save()
                log_items.append(f"🔧 {tool.nomenclature.name} {tool.nomenclature.article} (№{tool.inventory_id})")
            else:
                # НЕ БЕРУТ: Оставляем на складе, но в комплекте
                tool.current_holder = None
                tool.current_warehouse = kit.warehouse
                tool.status = 'IN_STOCK'
                tool.save()

        # 2. РАСХОДНИКИ (НОВАЯ ЛОГИКА)
        for cons in kit.consumables.all():
            if str(cons.id) in selected_cons_ids:
                # БЕРУТ:
                # Мы НЕ удаляем запись и НЕ сливаем её с другими вещами юзера.
                # Мы просто меняем локацию этой конкретной пачки гвоздей.
                cons.holder = user
                cons.warehouse = None
                # Поле kit остается неизменным! Система помнит, что это "Гвозди от комплекта А"
                cons.save()
                
                log_items.append(f"🔩 {cons.nomenclature.name} {cons.nomenclature.article} ({cons.quantity} шт)")
            else:
                # НЕ БЕРУТ:
                # Возвращаем на склад (внутри комплекта)
                cons.holder = None
                cons.warehouse = kit.warehouse
                cons.save()

        # 3. САМ КОМПЛЕКТ
        kit.current_holder = user
        kit.status = 'ISSUED'
        
        # Напарники
        kit.co_workers.clear()
        partners_names = []
        if partner_ids:
            partners = User.objects.filter(id__in=partner_ids)
            kit.co_workers.set(partners)
            partners_names = [p.get_full_name() or p.username for p in partners]

        kit.save()
        
        if not log_items: log_items.append("Пустой кейс")
        if partners_names: log_items.append(f"\n👥 Бригада: {', '.join(partners_names)}")

        MovementLog.objects.create(
            initiator=request.user, 
            action_type='KIT_ISSUE', 
            nomenclature_name=kit.name, 
            nomenclature_article="КОМПЛЕКТ", 
            source_warehouse=kit.warehouse, 
            target_user=user, 
            composition="\n".join(log_items),
            comment=request.POST.get('comment', '')
        )

    return redirect(f'/kits/?kit_id={kit.id}')


@login_required
def kit_return(request, kit_id):
    """ВОЗВРАТ: Возвращаем Инструменты И Расходники (привязанные к комплекту)"""
    kit = get_object_or_404(ToolKit, pk=kit_id)
    
    is_authorized = (
        request.user.is_staff or 
        kit.current_holder == request.user or 
        kit.co_workers.filter(id=request.user.id).exists()
    )
    
    if request.method == 'POST' and is_authorized:
        wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()
        holder_was = kit.current_holder
        
        log_items = []
        
        # 1. ИНСТРУМЕНТЫ
        tools_to_return = ToolInstance.objects.filter(kit=kit, current_holder=holder_was)
        for tool in tools_to_return:
            tool.current_holder = None
            tool.current_warehouse = wh
            tool.status = 'IN_STOCK'
            tool.save()
            log_items.append(f"🔧 {tool.nomenclature.name} {tool.nomenclature.article} (№{tool.inventory_id})")

        # 2. РАСХОДНИКИ (ТЕПЕРЬ ВОЗВРАЩАЕМ)
        # Ищем записи, которые:
        # а) Привязаны к этому комплекту
        # б) Находятся у текущего держателя
        cons_to_return = ConsumableBalance.objects.filter(kit=kit, holder=holder_was)
        
        for cons in cons_to_return:
            cons.holder = None
            cons.warehouse = wh # Возвращаем на склад (но оставляем в комплекте)
            cons.save()
            
            # (Опционально) Слияние дублей на складе, если вдруг там уже лежит такой же остаток
            # Но так как у нас уникальность (kit, warehouse, nomenclature), то дубля быть не должно, 
            # если мы выдавали "под чистую". А если выдавали частично - то на складе осталась другая запись.
            # В идеале тут можно добавить логику слияния, но для простоты пока просто вернем.
            
            log_items.append(f"🔩 {cons.nomenclature.name} {cons.nomenclature.article} ({cons.quantity} шт)")

        # 3. КОМПЛЕКТ
        if kit.co_workers.exists():
            names = [u.get_full_name() or u.username for u in kit.co_workers.all()]
            log_items.append(f"\n👥 Сдала бригада: {', '.join(names)}")
        
        kit.current_holder = None
        kit.co_workers.clear()
        kit.status = 'IN_STOCK'
        kit.save()
        
        if not log_items: log_items.append("Пустой кейс")
        
        comment = request.POST.get('comment', '')
        if request.user != holder_was and holder_was:
            comment += f" (Принял: {request.user.get_full_name()})"

        MovementLog.objects.create(
            initiator=request.user, 
            action_type='KIT_RETURN', 
            nomenclature_name=kit.name, 
            nomenclature_article="КОМПЛЕКТ", 
            source_user=holder_was, 
            target_warehouse=wh, 
            composition="\n".join(log_items),
            comment=comment
        )
    return redirect(f'/kits/?kit_id={kit.id}')

# ==========================================
# 6. МАССОВАЯ ВЫДАЧА
# ==========================================
@staff_member_required
def bulk_issue(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user = get_object_or_404(User, pk=data.get('employee_id'))
            for item in data.get('items', []):
                type_, id_ = item['type'], item['id']
                if type_ == 'tool':
                    tool = ToolInstance.objects.get(pk=id_)
                    if tool.status == 'BROKEN' or tool.condition == 'BROKEN':
                        continue # Пропускаем сломанные, не выдаем
                    if tool.status == 'IN_STOCK':
                        wh_was = tool.current_warehouse; kit_was = tool.kit
                        tool.current_holder = user; tool.current_warehouse = None; tool.status = 'ISSUED'; tool.save()
                        if kit_was: MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=tool.nomenclature, tool_instance=tool, source_kit=kit_was, target_user=user, comment="Массовая выдача (из комплекта)")
                        else: MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=tool.nomenclature, tool_instance=tool, source_warehouse=wh_was, target_user=user, comment="Массовая выдача")
                elif type_ == 'consumable':
                    qty = int(item['qty']); balance = ConsumableBalance.objects.get(pk=id_)
                    if balance.quantity >= qty:
                        wh_was = balance.warehouse
                        balance.quantity -= qty; balance.save()
                        target, _ = ConsumableBalance.objects.get_or_create(nomenclature=balance.nomenclature, holder=user, defaults={'quantity': 0})
                        target.quantity += qty; target.save()
                        MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=balance.nomenclature, quantity=qty, source_warehouse=wh_was, target_user=user, comment=f"Массовая выдача ({qty} шт)")
                        if balance.quantity == 0: balance.delete()
            return JsonResponse({'status': 'ok'})
        except Exception as e: return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    # GET
    # ... (начало bulk_issue c POST запросом оставляем как было) ...
    
    # --- GET ЗАПРОС (СБОР ДАННЫХ) ---
    
    # 1. ИНСТРУМЕНТЫ И ЭКИПИРОВКА
    tools_qs = ToolInstance.objects.filter(status='IN_STOCK', car__isnull=True).select_related('nomenclature', 'current_warehouse', 'kit')
    tools_data = []

    for t in tools_qs:
        wh_id = None
        display_name = t.nomenclature.name
        
        if t.current_warehouse:
            wh_id = t.current_warehouse.id
        elif t.kit and t.kit.warehouse:
            wh_id = t.kit.warehouse.id
            display_name += f" (📦 {t.kit.name})"

        if wh_id:
            tools_data.append({
                'id': t.id,
                'type': 'tool', # Технический тип для скрипта
                'type_label': t.nomenclature.get_item_type_display(), # НОВОЕ: Красивое название (Инструмент/Экипировка)
                'name': display_name,
                'art': t.nomenclature.article,
                'sn': t.inventory_id,
                'wh_id': wh_id
            })

    # 2. РАСХОДНИКИ
    cons_qs = ConsumableBalance.objects.filter(warehouse__isnull=False).select_related('nomenclature', 'warehouse')
    cons_data = []
    for c in cons_qs:
        cons_data.append({
            'id': c.id,
            'type': 'consumable',
            'type_label': 'Расходник', # НОВОЕ
            'name': c.nomenclature.name,
            'art': c.nomenclature.article,
            'max_qty': c.quantity,
            'wh_id': c.warehouse.id
        })

    return render(request, 'inventory/bulk_issue.html', {
        'employees': User.objects.filter(is_active=True),
        'warehouses': Warehouse.objects.all(),
        'tools_json': json.dumps(tools_data), 
        'consumables_json': json.dumps(cons_data)
    })

# ==========================================
# 7. ОСТАЛЬНОЕ И API
# ==========================================
@staff_member_required
def get_employee_items(request, employee_id):
    user = get_object_or_404(User, pk=employee_id)
    
    data = {
        'tools': [{
            'id': t.id,
            'name': t.nomenclature.name,       # Чистое название
            'art': t.nomenclature.article,     # Отдельно артикул
            'sn': t.inventory_id,
            'type_label': t.nomenclature.get_item_type_display() # "Инструмент" или "Экипировка"
        } for t in ToolInstance.objects.filter(current_holder=user)],
        
        'consumables': [{
            'id': c.id,
            'name': c.nomenclature.name,
            'art': c.nomenclature.article,
            'qty': c.quantity,
            'type_label': 'Расходник'
        } for c in ConsumableBalance.objects.filter(holder=user)]
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
            item_type, item_id, comment, qty = data.get('type'), data.get('id'), data.get('comment', 'Списание'), int(data.get('qty', 1))
            if item_type == 'tool':
                tool = ToolInstance.objects.get(pk=item_id)
                MovementLog.objects.create(initiator=request.user, action_type='WRITEOFF', nomenclature=tool.nomenclature, nomenclature_name=tool.nomenclature.name, nomenclature_article=tool.nomenclature.article, serial_number=tool.inventory_id, source_user=tool.current_holder, comment=f"СПИСАНИЕ. Причина: {comment}"); tool.delete()
            elif item_type == 'consumable':
                balance = ConsumableBalance.objects.get(pk=item_id)
                if balance.quantity >= qty:
                    balance.quantity -= qty; balance.save()
                    MovementLog.objects.create(initiator=request.user, action_type='WRITEOFF', nomenclature=balance.nomenclature, nomenclature_name=balance.nomenclature.name, nomenclature_article=balance.nomenclature.article, quantity=qty, source_user=balance.holder, comment=f"СПИСАНИЕ {qty} шт. Причина: {comment}")
                    if balance.quantity == 0: balance.delete()
            return JsonResponse({'status': 'ok'})
        except Exception as e: return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    return JsonResponse({'status': 'error'}, status=405)

# ==========================================
# 8. СПРАВОЧНИКИ И СКЛАДЫ
# ==========================================
@staff_member_required
def nomenclature_list(request):
    items_qs = Nomenclature.objects.all().order_by('name')
    if request.method == 'POST':
        form = NomenclatureForm(request.POST)
        if form.is_valid(): form.save(); messages.success(request, "✅ Номенклатура успешно добавлена!"); return redirect('nomenclature_list')
    else: form = NomenclatureForm()
    paginator = Paginator(items_qs, 10); items_page = paginator.get_page(request.GET.get('page'))
    context = {'items': items_page, 'form': form}
    if request.headers.get('x-requested-with') == 'XMLHttpRequest': return render(request, 'inventory/nomenclature_list_content.html', context)
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
def employee_list(request):
    employees = User.objects.all().order_by('username')
    return render(request, 'inventory/employee_list.html', {'employees': employees})
@staff_member_required
def employee_add(request):
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            if form.cleaned_data.get('new_password'): user.set_password(form.cleaned_data.get('new_password'))
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
            if form.cleaned_data.get('new_password'): user.set_password(form.cleaned_data.get('new_password'))
            user.save()
            return redirect('employee_list')
    else: form = EmployeeForm(instance=employee)
    return render(request, 'inventory/form_edit.html', {'form': form, 'title': f'Редактирование: {employee.username}'})
@staff_member_required
def employee_delete(request, user_id):
    user_to_delete = get_object_or_404(User, pk=user_id)
    if request.method == 'POST' and user_to_delete.id != request.user.id: user_to_delete.delete()
    return redirect('employee_list')

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

# --- 9. ИСТОРИЯ (С ПАГИНАЦИЕЙ) ---
@login_required
def history_list(request):
    logs_qs = MovementLog.objects.exclude(action_type__in=['CAR_ISSUE', 'CAR_RETURN', 'CAR_TO_MAINT', 'CAR_FROM_MAINT', 'CAR_TO_TI', 'CAR_FROM_TI']).order_by('-date')
    employees = User.objects.all().order_by('username')
    
    search = request.GET.get('search', '')
    emp_id = request.GET.get('employee', '')
    d_from = request.GET.get('date_from', '')
    d_to = request.GET.get('date_to', '')

    if search: logs_qs = logs_qs.filter(Q(nomenclature_name__icontains=search)|Q(serial_number__icontains=search))
    if emp_id: logs_qs = logs_qs.filter(Q(source_user_id=emp_id)|Q(target_user_id=emp_id)|Q(initiator_id=emp_id))
    if d_from: logs_qs = logs_qs.filter(date__gte=d_from)
    if d_to: logs_qs = logs_qs.filter(date__lte=d_to)

    paginator = Paginator(logs_qs, 10) 
    logs_page = paginator.get_page(request.GET.get('page'))

    context = {'logs': logs_page, 'employees': employees}
    if request.headers.get('x-requested-with') == 'XMLHttpRequest': return render(request, 'inventory/history_content.html', context)
    return render(request, 'inventory/history.html', context)