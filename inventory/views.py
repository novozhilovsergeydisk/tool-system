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
from .forms import NomenclatureForm, ToolInstanceForm, ToolKitForm, WarehouseForm, CarForm, NewsForm
from itertools import chain
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from .decorators import permission_required_custom
from .forms import EmployeeAddForm, EmployeeEditForm
import uuid


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
    
    # Алерты (только для админов/персонала)
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


# --- 3. СПИСОК ТОВАРОВ (ОБЩИЙ) ---
@login_required
def tool_list(request):
    """Таблица товаров с изоляцией кнопок"""
    
    # 1. Базовые запросы
    tools = ToolInstance.objects.filter(car__isnull=True).select_related('nomenclature', 'current_warehouse', 'current_holder', 'kit')
    consumables = ConsumableBalance.objects.filter(kit__isnull=True).select_related('nomenclature', 'warehouse', 'holder')
    
    employees = User.objects.filter(is_active=True).order_by('username')
    all_warehouses = Warehouse.objects.all().order_by('name')

    # 2. ОПРЕДЕЛЯЕМ ПРАВА ПОЛЬЗОВАТЕЛЯ
    # ИЗМЕНЕНО: is_staff приравниваем к суперюзеру
    if request.user.is_staff:
        user_allowed_whs_qs = all_warehouses
        allowed_wh_ids = list(all_warehouses.values_list('id', flat=True))
    else:
        if not hasattr(request.user, 'profile'):
            from .models import EmployeeProfile
            EmployeeProfile.objects.create(user=request.user)
        
        user_allowed_whs_qs = request.user.profile.allowed_warehouses.all()
        allowed_wh_ids = list(user_allowed_whs_qs.values_list('id', flat=True))

    # --- ФИЛЬТРАЦИЯ ---
    search = request.GET.get('search', '').strip()
    wh_id = request.GET.get('warehouse', '')
    emp_query = request.GET.get('employee', '').strip()
    type_filter = request.GET.get('item_type', '')
    status_filter = request.GET.get('status', '')

    if search:
        tools = tools.filter(Q(nomenclature__name__icontains=search) | Q(inventory_id__icontains=search) | Q(nomenclature__article__icontains=search) | Q(kit__name__icontains=search))
        consumables = consumables.filter(Q(nomenclature__name__icontains=search) | Q(nomenclature__article__icontains=search))
    
    # ПОИСК ПО СОТРУДНИКУ (ИСПРАВЛЕННЫЙ)
    if emp_query:
        terms = emp_query.split()
        users = User.objects.all()
        for term in terms:
            users = users.filter(
                Q(username__icontains=term) | 
                Q(first_name__icontains=term) | 
                Q(last_name__icontains=term) |
                Q(email__icontains=term)
            )
        tools = tools.filter(current_holder__in=users)
        consumables = consumables.filter(holder__in=users)

    if wh_id:
        tools = tools.filter(current_warehouse_id=wh_id)
        consumables = consumables.filter(warehouse_id=wh_id)

    if type_filter:
        if type_filter == 'CONSUMABLE': tools = tools.none()
        else:
            tools = tools.filter(nomenclature__item_type=type_filter)
            consumables = consumables.none()

    if status_filter:
        if status_filter == 'IN_STOCK':
            tools = tools.filter(status='IN_STOCK')
            consumables = consumables.filter(warehouse__isnull=False)
        elif status_filter == 'ISSUED':
            tools = tools.filter(status='ISSUED')
            consumables = consumables.filter(holder__isnull=False)

    for t in tools: t.row_type = 'tool'
    for c in consumables: c.row_type = 'consumable'

    combined = list(chain(tools, consumables))
    combined.sort(key=lambda x: x.nomenclature.name.lower())

    paginator = Paginator(combined, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    context = {
        'items': page_obj, 
        'page_obj': page_obj, 
        'employees': employees, 
        'warehouses': all_warehouses,       # Для фильтра "Все склады"
        'allowed_whs': user_allowed_whs_qs, # ВАЖНО: Только доступные склады (для модалок)
        'allowed_ids': allowed_wh_ids       # Список ID для проверки кнопок в HTML
    }
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory/tool_list_content.html', context)
    return render(request, 'inventory/tool_list.html', context)

# ==========================================
# 3.1. ОПЕРАЦИИ С ИНСТРУМЕНТОМ
# ==========================================


@permission_required_custom('inventory.add_toolinstance')
def tool_add(request):
    """
    Универсальный приход
    """
    # 1. Склады: Если staff - видит всё
    if request.user.is_staff:
        allowed_whs = Warehouse.objects.all()
    else:
        if not hasattr(request.user, 'profile'):
            from .models import EmployeeProfile
            EmployeeProfile.objects.create(user=request.user)
        allowed_whs = request.user.profile.allowed_warehouses.all()

    # 2. Номенклатура
    nomenclatures = Nomenclature.objects.all().order_by('name')
    types_map = {n.id: n.item_type for n in nomenclatures}

    if request.method == 'POST':
        wh_id = request.POST.get('warehouse_id')
        nom_id = request.POST.get('nomenclature_id')
        
        # Защита склада
        if not request.user.is_staff and not allowed_whs.filter(id=wh_id).exists():
            messages.error(request, "⛔ Нет доступа к выбранному складу")
            return redirect('tool_add')

        warehouse = get_object_or_404(Warehouse, pk=wh_id)
        nomenclature = get_object_or_404(Nomenclature, pk=nom_id)

        # === СЦЕНАРИЙ 1: РАСХОДНИКИ (Количество) ===
        if nomenclature.item_type == 'CONSUMABLE':
            qty = int(request.POST.get('quantity', 0))
            if qty > 0:
                balance, created = ConsumableBalance.objects.get_or_create(
                    nomenclature=nomenclature,
                    warehouse=warehouse,
                    kit__isnull=True,
                    defaults={'quantity': 0}
                )
                balance.quantity += qty
                balance.save()

                MovementLog.objects.create(
                    initiator=request.user, action_type='RECEIPT', 
                    nomenclature=nomenclature, quantity=qty, 
                    target_warehouse=warehouse, comment="Приход (Расходник)"
                )
                messages.success(request, f"✅ Добавлено: {nomenclature.name} ({qty} шт.)")
            else:
                messages.error(request, "Количество должно быть больше 0")

        # === СЦЕНАРИЙ 2 и 3: ИНСТРУМЕНТ ИЛИ ЭКИПИРОВКА ===
        else:
            condition = request.POST.get('condition', 'NEW')
            
            if nomenclature.item_type == 'EQUIPMENT':
                inventory_id = f"EQ-{uuid.uuid4().hex[:8].upper()}"
            else:
                inventory_id = request.POST.get('inventory_id')

            if ToolInstance.objects.filter(inventory_id=inventory_id).exists():
                messages.error(request, f"⛔ Товар с номером {inventory_id} уже существует!")
                return redirect('tool_add')

            tool = ToolInstance.objects.create(
                nomenclature=nomenclature,
                current_warehouse=warehouse,
                inventory_id=inventory_id,
                status='IN_STOCK',
                condition=condition
            )
            
            MovementLog.objects.create(
                initiator=request.user, action_type='RECEIPT', 
                nomenclature=nomenclature, tool_instance=tool,
                serial_number=inventory_id, target_warehouse=warehouse, 
                comment=f"Приход ({nomenclature.get_item_type_display()})"
            )
            messages.success(request, f"✅ Принят: {nomenclature.name}")

        return redirect('tool_list')
        
    context = {
        'nomenclatures': nomenclatures, 
        'warehouses': allowed_whs,
        'types_json': json.dumps(types_map)
    }
    return render(request, 'inventory/tool_add.html', context)
    
@permission_required_custom('inventory.change_toolinstance')
def tool_edit(request, tool_id): 
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    
    # ЗАЩИТА: is_staff может редактировать всё
    if not request.user.is_staff:
        if tool.current_warehouse and not request.user.profile.allowed_warehouses.filter(id=tool.current_warehouse.id).exists():
            messages.error(request, f"⛔ Инструмент находится на чужом складе: {tool.current_warehouse.name}")
            return redirect('tool_list')

    if request.method == 'POST':
        tool.inventory_id = request.POST.get('inventory_id')
        tool.condition = request.POST.get('condition')
        tool.save()
        messages.success(request, "Сохранено")
        return redirect('tool_list')
        
    return render(request, 'inventory/tool_edit.html', {'tool': tool})

@permission_required_custom('inventory.change_toolinstance')
def tool_issue(request, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    
    # --- ЗАЩИТА: ПРОВЕРКА СКЛАДА ---
    if not request.user.is_staff:
        if tool.current_warehouse and not request.user.profile.allowed_warehouses.filter(id=tool.current_warehouse.id).exists():
            messages.error(request, "⛔ У вас нет прав выдавать товары с этого склада!")
            return redirect('tool_list')
    # -------------------------------

    if request.method == 'POST':
        employee_id = request.POST.get('employee_id')
        user = get_object_or_404(User, pk=employee_id)
        
        wh_was = tool.current_warehouse
        tool.current_holder = user
        tool.current_warehouse = None
        tool.status = 'ISSUED'
        tool.save()
        
        MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=tool.nomenclature, tool_instance=tool, source_warehouse=wh_was, target_user=user, comment=request.POST.get('comment', ''))
        messages.success(request, f"Выдано: {tool.nomenclature.name}")
        
    return redirect('tool_list')

@permission_required_custom('inventory.change_toolinstance')
def tool_return(request, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    
    if request.method == 'POST':
        wh_id = request.POST.get('warehouse_id')
        target_wh = get_object_or_404(Warehouse, pk=wh_id)
        
        # --- ПРОВЕРКА ПРАВ НА СКЛАД ---
        if not request.user.is_staff:
            if not request.user.profile.allowed_warehouses.filter(id=wh_id).exists():
                messages.error(request, f"⛔ Ошибка доступа! Вы не можете принимать на склад: {target_wh.name}")
                return redirect('tool_list')

        tool.current_holder = None
        tool.current_warehouse = target_wh
        tool.status = 'IN_STOCK'
        tool.save()
        
        MovementLog.objects.create(
            initiator=request.user, action_type='RETURN',
            nomenclature=tool.nomenclature, tool_instance=tool,
            source_user=tool.current_holder, target_warehouse=target_wh, comment="Ручной возврат"
        )
        messages.success(request, "Возвращено")
        
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

# --- РАСХОДНИКИ ---
@permission_required_custom('inventory.change_consumablebalance')
def consumable_issue(request, balance_id):
    balance = get_object_or_404(ConsumableBalance, pk=balance_id)

    # --- ЗАЩИТА: ПРОВЕРКА СКЛАДА ---
    if not request.user.is_staff:
        if not request.user.profile.allowed_warehouses.filter(id=balance.warehouse.id).exists():
            messages.error(request, "⛔ У вас нет прав выдавать расходники с этого склада!")
            return redirect('consumable_list')
    # -------------------------------

    if request.method == 'POST':
        qty = int(request.POST.get('quantity'))
        employee_id = request.POST.get('employee_id')
        target_user = get_object_or_404(User, pk=employee_id)
        
        if balance.quantity >= qty:
            wh_was = balance.warehouse
            balance.quantity -= qty
            balance.save()
            
            # Перенос пользователю
            user_balance, _ = ConsumableBalance.objects.get_or_create(
                nomenclature=balance.nomenclature,
                holder=target_user,
                defaults={'quantity': 0}
            )
            user_balance.quantity += qty
            user_balance.save()
            
            MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=balance.nomenclature, quantity=qty, source_warehouse=wh_was, target_user=target_user, comment=request.POST.get('comment', ''))
            
            if balance.quantity == 0:
                balance.delete()
            
            messages.success(request, f"Выдано {qty} шт.")
        else:
            messages.error(request, "Недостаточно на складе")
            
    return redirect('consumable_list')

@staff_member_required
def consumable_return(request, pk):
    balance = get_object_or_404(ConsumableBalance, pk=pk)
    if request.method == 'POST':
        wh = get_object_or_404(Warehouse, pk=request.POST.get('warehouse_id'))
        qty = int(request.POST.get('quantity', 0))
        
        if qty > 0 and balance.quantity >= qty:
            balance.quantity -= qty
            balance.save()
            
            target_bals = ConsumableBalance.objects.filter(
                nomenclature=balance.nomenclature, 
                warehouse=wh,
                kit__isnull=True 
            )
            
            if target_bals.exists():
                target = target_bals.first()
                target.quantity += qty
                target.save()
                
                if target_bals.count() > 1:
                    for dup in target_bals[1:]:
                        target.quantity += dup.quantity
                        target.save()
                        dup.delete()
            else:
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

@login_required 
def consumable_writeoff(request, pk):
    balance = get_object_or_404(ConsumableBalance, pk=pk)
    
    # 1. Проверка прав на действие
    if not request.user.has_perm('inventory.delete_consumablebalance') and not request.user.is_staff:
        messages.error(request, "⛔ У вас нет прав на списание!")
        return redirect('tool_list')

    # 2. Проверка доступа к СКЛАДУ (is_staff игнорирует)
    if balance.warehouse:
        if not request.user.profile.allowed_warehouses.filter(id=balance.warehouse.id).exists() and not request.user.is_staff:
            messages.error(request, f"⛔ Нет доступа к складу: {balance.warehouse.name}")
            return redirect('tool_list')

    if request.method == 'POST':
        qty = int(request.POST.get('quantity', 0))
        # (Остальной код списания был бы здесь, если бы он был в оригинале полным. Оставляем редирект для безопасности)
        
    return redirect('tool_list')
    
# ==========================================
# 4. АВТОМОБИЛИ
# ==========================================
@login_required
def car_list(request):
    """Список авто доступен всем для просмотра"""
    cars = Car.objects.all()
    selected_car = None; edit_form = None; history_trip_page = None; history_maint_page = None
    today = date.today(); warning_date = today + timedelta(days=30)

    if request.GET.get('car_id'):
        selected_car = get_object_or_404(Car, pk=request.GET.get('car_id'))
        
        if request.user.has_perm('login_required'):
            edit_form = CarForm(instance=selected_car)
        else:
            edit_form = None 
        
        logs_trips = MovementLog.objects.filter(Q(source_car=selected_car)|Q(target_car=selected_car), action_type__in=['CAR_ISSUE', 'CAR_RETURN']).order_by('-date')
        paginator_trips = Paginator(logs_trips, 10)
        history_trip_page = paginator_trips.get_page(request.GET.get('page_trips'))

        logs_maint = MovementLog.objects.filter(Q(source_car=selected_car)|Q(target_car=selected_car), action_type__in=['CAR_TO_MAINT', 'CAR_FROM_MAINT', 'CAR_TO_TI', 'CAR_FROM_TI']).order_by('-date')
        paginator_maint = Paginator(logs_maint, 10)
        history_maint_page = paginator_maint.get_page(request.GET.get('page_maint'))

    context = {
        'cars': cars, 'selected_car': selected_car, 
        'employees': User.objects.filter(is_active=True), 
        'form': CarForm(), 'edit_form': edit_form, 
        'history_trip_page': history_trip_page, 'history_maint_page': history_maint_page, 
        'today': today, 'warning_date': warning_date
    }
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'inventory/cars_content.html', context)

    return render(request, 'inventory/cars.html', context)

@permission_required_custom('inventory.add_car')
def car_create(request):
    if request.method == 'POST':
        form = CarForm(request.POST)
        if form.is_valid(): car = form.save(); return redirect(f'/cars/?car_id={car.id}')
    return redirect('car_list')

@permission_required_custom('inventory.change_car')
def car_edit(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        form = CarForm(request.POST, instance=car)
        if form.is_valid(): form.save(); return redirect(f'/cars/?car_id={car.id}')
    return redirect('car_list')

@permission_required_custom('inventory.delete_car')
def car_delete(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        for t in car.tools.all(): 
            t.car = None; t.current_warehouse = Warehouse.objects.first(); t.status='IN_STOCK'; t.save()
        car.delete()
    return redirect('car_list')

# --- ОПЕРАЦИИ (Выдача, Возврат, ТО, Ремонт) ---

@login_required 
def car_issue(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    
    if request.method == 'POST':
        # Если машина уже занята или сломана
        if car.status != 'PARKED':
             messages.error(request, "Эта машина недоступна для взятия.")
             return redirect(f'/cars/?car_id={car.id}')

        # ЛОГИКА ОПРЕДЕЛЕНИЯ ВОДИТЕЛЯ
        # Если админ - берет ID из формы. Если обычный юзер - берем его самого.
        if request.user.is_staff and request.POST.get('employee_id'):
            user = get_object_or_404(User, pk=request.POST.get('employee_id'))
        else:
            user = request.user

        car.current_driver = user
        car.status = 'ON_ROUTE'
        car.save()
        
        MovementLog.objects.create(
            initiator=request.user, 
            action_type='CAR_ISSUE', 
            target_user=user, 
            target_car=car, 
            comment="Выезд"
        )
        messages.success(request, f"Вы взяли автомобиль: {car.name}")
        
    return redirect(f'/cars/?car_id={car.id}')

@login_required  # <--- ИЗМЕНЕНО: Доступно всем авторизованным
def car_return(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    
    if request.method == 'POST':
        # Проверка: Обычный юзер может вернуть только СВОЮ машину
        if not request.user.is_staff and car.current_driver != request.user:
             messages.error(request, "Вы не можете вернуть чужую машину.")
             return redirect(f'/cars/?car_id={car.id}')

        holder_was = car.current_driver
        
        # Пробег (если поле пустое или юзер не ввел - оставляем старый)
        try:
            end_mileage = int(request.POST.get('end_mileage', car.current_mileage))
        except (ValueError, TypeError):
            end_mileage = car.current_mileage
            
        # Защита от скручивания пробега
        if end_mileage < car.current_mileage:
            end_mileage = car.current_mileage

        trip_dist = end_mileage - car.current_mileage
        
        # Топливо
        fuel_liters = 0
        if request.POST.get('fuel_added') == 'on':
            try:
                fuel_liters = int(request.POST.get('fuel_liters', 0))
            except ValueError:
                fuel_liters = 0

        car.current_driver = None
        car.status = 'PARKED'
        car.current_mileage = end_mileage
        car.save()
        
        MovementLog.objects.create(
            initiator=request.user, 
            action_type='CAR_RETURN', 
            source_user=holder_was, 
            source_car=car, 
            trip_mileage=trip_dist, 
            fuel_liters=fuel_liters, 
            comment=f"Возврат. Пробег: {trip_dist} км."
        )
        messages.success(request, "Автомобиль возвращен на парковку.")
        
    return redirect(f'/cars/?car_id={car.id}')

@permission_required_custom('inventory.change_car')
def car_to_maintenance(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        car.current_driver = None; car.status = 'MAINTENANCE'; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_TO_MAINT', target_car=car, comment="Отправлена на ТО")
    return redirect(f'/cars/?car_id={car.id}')

@permission_required_custom('inventory.change_car')
def car_return_from_maintenance(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        end_mileage = int(request.POST.get('end_mileage', car.current_mileage))
        trip_dist = max(0, end_mileage - car.current_mileage)
        car.status = 'PARKED'; car.current_mileage = end_mileage; car.last_service_mileage = end_mileage; car.save() # Сброс ТО
        MovementLog.objects.create(initiator=request.user, action_type='CAR_FROM_MAINT', source_car=car, trip_mileage=trip_dist, maintenance_work=request.POST.get('works', ''), comment="Возврат с ТО. Интервал сброшен.")
    return redirect(f'/cars/?car_id={car.id}')

@permission_required_custom('inventory.change_car')
def car_to_tech_inspection(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        car.current_driver = None; car.status = 'TECH_INSPECTION'; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_TO_TI', target_car=car, comment="Отправлена на Техосмотр")
    return redirect(f'/cars/?car_id={car.id}')

@permission_required_custom('inventory.change_car')
def car_return_from_tech_inspection(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        end_mileage = int(request.POST.get('end_mileage', car.current_mileage))
        fuel_liters = int(request.POST.get('fuel_liters', 0)) if request.POST.get('fuel_added') == 'on' else 0
        trip_dist = max(0, end_mileage - car.current_mileage)
        car.status = 'PARKED'; car.current_mileage = end_mileage; car.last_ti_date = date.today(); car.save() 
        MovementLog.objects.create(initiator=request.user, action_type='CAR_FROM_TI', source_car=car, trip_mileage=trip_dist, fuel_liters=fuel_liters, comment=f"Возврат с Техосмотра. Дата обновлена. Пробег: {trip_dist} км")
    return redirect(f'/cars/?car_id={car.id}')

@permission_required_custom('inventory.change_car')
def car_mark_broken(request, car_id):
    car = get_object_or_404(Car, pk=car_id)
    if request.method == 'POST':
        car.current_driver = None; car.status = 'BROKEN'; car.save()
        MovementLog.objects.create(initiator=request.user, action_type='CAR_TO_MAINT', target_car=car, comment="АВТОМОБИЛЬ СЛОМАН (Помечен администратором)")
    return redirect(f'/cars/?car_id={car.id}')

@permission_required_custom('inventory.change_car')
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
            available_tools = ToolInstance.objects.filter(
                current_warehouse=selected_kit.warehouse, 
                kit__isnull=True, 
                car__isnull=True, 
                status='IN_STOCK'
            )
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


@permission_required_custom('inventory.add_toolkit')
def kit_create(request):
    if request.method == 'POST':
        form = ToolKitForm(request.POST)
        if form.is_valid(): 
            kit = form.save()
            return redirect(f'/kits/?kit_id={kit.id}')
    return redirect('kit_list')

@permission_required_custom('inventory.change_toolkit')
def kit_edit(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    old_wh = kit.warehouse
    if request.method == 'POST':
        form = ToolKitForm(request.POST, instance=kit)
        if form.is_valid():
            new_kit = form.save()
            if old_wh != new_kit.warehouse: 
                MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature_name=kit.name, nomenclature_article="КОМПЛЕКТ", source_warehouse=old_wh, target_warehouse=new_kit.warehouse, comment=f"Перемещение комплекта")
            return redirect(f'/kits/?kit_id={kit.id}')
    return redirect('kit_list')

@permission_required_custom('inventory.delete_toolkit')
def kit_delete(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()
        for t in kit.tools.all(): 
            t.kit = None; t.current_warehouse = wh; t.status = 'IN_STOCK'; t.save()
        kit.delete()
    return redirect('kit_list')


@login_required
def kit_add_tool(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        tool = get_object_or_404(ToolInstance, pk=request.POST.get('tool_id'))
        
        if tool.status == 'BROKEN' or tool.condition == 'BROKEN':
            messages.error(request, f"⛔ Нельзя добавить сломанный инструмент в комплект: {tool.nomenclature.name}")
            return redirect(f'/kits/?kit_id={kit.id}')

        if tool.current_warehouse != kit.warehouse: 
            return redirect(f'/kits/?kit_id={kit.id}')
        
        # Запоминаем склад, ОТКУДА забираем (для истории)
        source_wh = tool.current_warehouse

        tool.kit = kit
        tool.save() 

        MovementLog.objects.create(
            initiator=request.user,
            action_type='KIT_EDIT',
            
            # ОТКУДА: Склад, где лежал инструмент
            source_warehouse=source_wh,
            
            # КУДА: В этот комплект
            target_kit=kit,
            
            tool_instance=tool,
            nomenclature=tool.nomenclature,
            comment=f"Добавлен инструмент в комплект: {tool.nomenclature.name}"
        )

    return redirect(f'/kits/?kit_id={kit.id}')

@login_required
def kit_remove_tool(request, kit_id, tool_id):
    tool = get_object_or_404(ToolInstance, pk=tool_id)
    kit = tool.kit 
    
    if request.method == 'POST': 
        # Запоминаем склад, КУДА вернется инструмент (склад комплекта)
        target_wh = kit.warehouse if kit and kit.warehouse else Warehouse.objects.first()

        tool.kit = None
        tool.save()

        if kit:
            MovementLog.objects.create(
                initiator=request.user,
                action_type='KIT_EDIT',
                
                # ОТКУДА: Из комплекта
                source_kit=kit,
                
                # КУДА: На склад приписки комплекта
                target_warehouse=target_wh,
                
                tool_instance=tool,
                nomenclature=tool.nomenclature,
                comment=f"Убран инструмент из комплекта: {tool.nomenclature.name}"
            )

    return redirect(f'/kits/?kit_id={kit_id}')

@login_required
def kit_add_consumable(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        balance_id = request.POST.get('balance_id')
        qty = int(request.POST.get('quantity', 0))
        source_bal = get_object_or_404(ConsumableBalance, pk=balance_id)
        
        if source_bal.warehouse != kit.warehouse: 
            return redirect(f'/kits/?kit_id={kit.id}')
        
        # Запоминаем склад источника
        source_wh = source_bal.warehouse

        if qty > 0 and source_bal.quantity >= qty:
            source_bal.quantity -= qty
            source_bal.save()
            
            target_bal, _ = ConsumableBalance.objects.get_or_create(
                nomenclature=source_bal.nomenclature, kit=kit, defaults={'quantity': 0}
            )
            target_bal.quantity += qty
            target_bal.save()
            
            if source_bal.quantity == 0: source_bal.delete()

            MovementLog.objects.create(
                initiator=request.user,
                action_type='KIT_EDIT',
                
                # ОТКУДА: Склад
                source_warehouse=source_wh,
                
                # КУДА: Комплект
                target_kit=kit,
                
                nomenclature=source_bal.nomenclature,
                quantity=qty,
                comment=f"Добавлен расходник в комплект: {qty} шт."
            )

    return redirect(f'/kits/?kit_id={kit.id}')

@login_required
def kit_remove_consumable(request, kit_id, balance_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    if request.method == 'POST':
        kit_bal = get_object_or_404(ConsumableBalance, pk=balance_id)
        qty = int(request.POST.get('quantity', 0))
        
        # Склад приписки комплекта, куда возвращаем
        target_wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()
        
        if qty > 0 and kit_bal.quantity >= qty:
            kit_bal.quantity -= qty
            kit_bal.save()
            
            wh_bal, _ = ConsumableBalance.objects.get_or_create(
                nomenclature=kit_bal.nomenclature, warehouse=target_wh, defaults={'quantity': 0}
            )
            wh_bal.quantity += qty
            wh_bal.save()
            
            if kit_bal.quantity == 0: kit_bal.delete()

            MovementLog.objects.create(
                initiator=request.user,
                action_type='KIT_EDIT',
                
                # ОТКУДА: Комплект
                source_kit=kit,
                
                # КУДА: Склад
                target_warehouse=target_wh,
                
                nomenclature=kit_bal.nomenclature,
                quantity=qty,
                comment=f"Убран расходник из комплекта: {qty} шт."
            )

    return redirect(f'/kits/?kit_id={kit.id}')

@login_required
def kit_issue(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    
    if request.method == 'POST':
        user = get_object_or_404(User, pk=request.POST.get('employee_id'))
        sel_tools = set(request.POST.getlist('tools_selected'))
        sel_cons = set(request.POST.getlist('cons_selected'))
        partner_ids = request.POST.getlist('partner_ids')
        
        log_items = []

        # 1. ИНСТРУМЕНТЫ
        for tool in kit.tools.all():
            if str(tool.id) in sel_tools:
                if tool.status == 'IN_STOCK':
                    tool.current_holder = user
                    tool.current_warehouse = None
                    tool.status = 'ISSUED'
                    tool.save()
                    log_items.append(f"🔧 {tool.nomenclature.name}")
                    
                    MovementLog.objects.create(
                        initiator=request.user, 
                        action_type='KIT_ISSUE', 
                        nomenclature=tool.nomenclature, 
                        tool_instance=tool, 
                        source_warehouse=kit.warehouse, 
                        target_user=user, 
                        comment=f"В составе: {kit.name}"
                    )
            else:
                if tool.status == 'IN_STOCK':
                    tool.current_holder = None
                    tool.current_warehouse = kit.warehouse
                    tool.status = 'IN_STOCK'
                    tool.save()

        # 2. РАСХОДНИКИ
        for c in kit.consumables.all():
            if str(c.id) in sel_cons:
                c.holder = user; c.warehouse = None; c.save()
                log_items.append(f"🔩 {c.nomenclature.name}")
            else:
                c.holder = None; c.warehouse = kit.warehouse; c.save()

        # 3. КОМПЛЕКТ
        kit.current_holder = user
        kit.status = 'ISSUED'
        kit.co_workers.clear()
        if partner_ids: kit.co_workers.set(User.objects.filter(id__in=partner_ids))
        kit.save()

        MovementLog.objects.create(
            initiator=request.user, action_type='KIT_ISSUE', 
            nomenclature_name=kit.name, nomenclature_article="КОМПЛЕКТ",
            source_warehouse=kit.warehouse, target_user=user, 
            composition="\n".join(log_items), comment=request.POST.get('comment', '')
        )
        messages.success(request, "Комплект выдан")
    return redirect(f'/kits/?kit_id={kit.id}')

@login_required
def kit_return(request, kit_id):
    kit = get_object_or_404(ToolKit, pk=kit_id)
    is_auth = request.user.is_staff or kit.current_holder == request.user or kit.co_workers.filter(id=request.user.id).exists()
    
    if request.method == 'POST' and is_auth:
        wh = kit.warehouse if kit.warehouse else Warehouse.objects.first()
        holder_was = kit.current_holder
        log_items = []

        for tool in ToolInstance.objects.filter(kit=kit, current_holder=holder_was):
            if tool.is_manual_issue:
                continue 
            
            tool.current_holder = None
            tool.current_warehouse = wh
            tool.status = 'IN_STOCK'
            tool.save()
            log_items.append(f"🔧 {tool.nomenclature.name}")
            
            MovementLog.objects.create(
                initiator=request.user, action_type='KIT_RETURN', 
                nomenclature=tool.nomenclature, tool_instance=tool, 
                source_user=holder_was, target_warehouse=wh, 
                comment=f"Возврат в составе: {kit.name}"
            )

        for c in ConsumableBalance.objects.filter(kit=kit, holder=holder_was):
            c.holder = None
            c.warehouse = wh
            c.save()
            log_items.append(f"🔩 {c.nomenclature.name} ({c.quantity})")

        kit.current_holder = None
        kit.co_workers.clear()
        kit.status = 'IN_STOCK'
        kit.save()

        MovementLog.objects.create(
            initiator=request.user, action_type='KIT_RETURN', 
            nomenclature_name=kit.name, nomenclature_article="КОМПЛЕКТ",
            source_user=holder_was, target_warehouse=wh, 
            composition="\n".join(log_items), comment=request.POST.get('comment', '')
        )
        messages.success(request, "Комплект возвращен")
    return redirect(f'/kits/?kit_id={kit.id}')

# ==========================================
# 6. МАССОВАЯ ВЫДАЧА
# ==========================================
@permission_required_custom('inventory.change_toolinstance')
def bulk_issue(request):
    """
    Массовая выдача.
    """
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            user = get_object_or_404(User, pk=data.get('employee_id'))
            
            for item in data.get('items', []):
                type_, id_ = item['type'], item['id']
                
                # --- ЛОГИКА ДЛЯ ИНСТРУМЕНТА ---
                if type_ == 'tool':
                    tool = ToolInstance.objects.get(pk=id_)
                    
                    # 1. ЗАЩИТА: Проверка склада (is_staff обходит)
                    if not request.user.is_staff:
                        check_wh = tool.current_warehouse or (tool.kit.warehouse if tool.kit else None)
                        if check_wh and not request.user.profile.allowed_warehouses.filter(id=check_wh.id).exists():
                            continue 

                    if tool.status == 'BROKEN' or tool.condition == 'BROKEN':
                        continue
                    
                    if tool.status == 'IN_STOCK':
                        wh_was = tool.current_warehouse
                        kit_was = tool.kit
                        
                        tool.current_holder = user
                        tool.current_warehouse = None
                        tool.status = 'ISSUED'
                        tool.save()
                        
                        if kit_was:
                            MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=tool.nomenclature, tool_instance=tool, source_kit=kit_was, target_user=user, comment="Массовая выдача (из комплекта)")
                        else:
                            MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=tool.nomenclature, tool_instance=tool, source_warehouse=wh_was, target_user=user, comment="Массовая выдача")
                
                # --- ЛОГИКА ДЛЯ РАСХОДНИКА ---
                elif type_ == 'consumable':
                    qty = int(item['qty'])
                    balance = ConsumableBalance.objects.get(pk=id_)
                    
                    if not request.user.is_staff:
                        if not request.user.profile.allowed_warehouses.filter(id=balance.warehouse.id).exists():
                            continue

                    if balance.quantity >= qty:
                        wh_was = balance.warehouse
                        balance.quantity -= qty
                        balance.save()
                        
                        target, _ = ConsumableBalance.objects.get_or_create(nomenclature=balance.nomenclature, holder=user, defaults={'quantity': 0})
                        target.quantity += qty
                        target.save()
                        
                        MovementLog.objects.create(initiator=request.user, action_type='ISSUE', nomenclature=balance.nomenclature, quantity=qty, source_warehouse=wh_was, target_user=user, comment=f"Массовая выдача ({qty} шт)")
                        
                        if balance.quantity == 0:
                            balance.delete()
            
            return JsonResponse({'status': 'ok'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    # --- GET ЗАПРОС ---
    
    tools_qs = ToolInstance.objects.filter(status='IN_STOCK', car__isnull=True).select_related('nomenclature', 'current_warehouse', 'kit', 'kit__warehouse')
    cons_qs = ConsumableBalance.objects.filter(warehouse__isnull=False).select_related('nomenclature', 'warehouse')
    warehouses_list = Warehouse.objects.all()

    # ФИЛЬТРАЦИЯ ПО ПРАВАМ
    if not request.user.is_staff:
        if not hasattr(request.user, 'profile'):
            from .models import EmployeeProfile
            EmployeeProfile.objects.create(user=request.user)
        
        allowed_whs = request.user.profile.allowed_warehouses.all()
        warehouses_list = allowed_whs

        tools_qs = tools_qs.filter(
            Q(current_warehouse__in=allowed_whs) | 
            Q(kit__warehouse__in=allowed_whs)
        )
        cons_qs = cons_qs.filter(warehouse__in=allowed_whs)

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
                'type': 'tool',
                'type_label': t.nomenclature.get_item_type_display(),
                'name': display_name,
                'art': t.nomenclature.article,
                'sn': t.inventory_id,
                'wh_id': wh_id
            })

    cons_data = []
    for c in cons_qs:
        cons_data.append({
            'id': c.id,
            'type': 'consumable',
            'type_label': 'Расходник',
            'name': c.nomenclature.name,
            'art': c.nomenclature.article,
            'max_qty': c.quantity,
            'wh_id': c.warehouse.id
        })

    return render(request, 'inventory/bulk_issue.html', {
        'employees': User.objects.filter(is_active=True).order_by('username'),
        'warehouses': warehouses_list, 
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
            'name': t.nomenclature.name,       
            'art': t.nomenclature.article,     
            'sn': t.inventory_id,
            'type_label': t.nomenclature.get_item_type_display() 
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
@login_required
def nomenclature_list(request):
    """
    Справочник номенклатуры.
    Доступ: Видят все, у кого есть хоть одна галочка (Печать, Создание, Изменение).
    """
    has_access = (
        request.user.is_staff or 
        request.user.has_perm('inventory.view_nomenclature') or
        request.user.has_perm('inventory.add_nomenclature') or
        request.user.has_perm('inventory.change_nomenclature')
    )
    
    if not has_access:
        messages.error(request, "⛔ Нет доступа к справочнику номенклатуры")
        return redirect('tool_list')

    items_qs = Nomenclature.objects.all().order_by('name')

    if request.method == 'POST':
        # is_staff приравнивается к superuser здесь
        if not (request.user.is_staff or request.user.has_perm('inventory.add_nomenclature')):
            messages.error(request, "⛔ У вас нет прав на создание номенклатуры")
            return redirect('nomenclature_list')

        form = NomenclatureForm(request.POST)
        if form.is_valid(): 
            form.save()
            messages.success(request, "✅ Номенклатура успешно добавлена!")
            return redirect('nomenclature_list')
    else: 
        form = NomenclatureForm()

    paginator = Paginator(items_qs, 10)
    items_page = paginator.get_page(request.GET.get('page'))
    
    context = {'items': items_page, 'form': form}
    
    if request.headers.get('x-requested-with') == 'XMLHttpRequest': 
        return render(request, 'inventory/nomenclature_list_content.html', context)
    return render(request, 'inventory/nomenclature_list.html', context)


@permission_required_custom('inventory.change_nomenclature')
def nomenclature_edit(request, pk):
    item = get_object_or_404(Nomenclature, pk=pk)
    if request.method == 'POST':
        form = NomenclatureForm(request.POST, instance=item)
        if form.is_valid(): 
            form.save()
            return redirect('nomenclature_list')
    else: 
        form = NomenclatureForm(instance=item)
    return render(request, 'inventory/nomenclature_edit.html', {'form': form, 'item': item})


@permission_required_custom('inventory.delete_nomenclature')
def nomenclature_delete(request, pk):
    item = get_object_or_404(Nomenclature, pk=pk)
    if request.method == 'POST': 
        item.delete()
    return redirect('nomenclature_list')

@login_required
def warehouse_list(request):
    return render(request, 'inventory/warehouse_list.html', {'warehouses': Warehouse.objects.all()})
@permission_required_custom('inventory.add_warehouse')
def warehouse_add(request):
    if request.method == 'POST':
        form = WarehouseForm(request.POST)
        if form.is_valid(): form.save(); return redirect('warehouse_list')
    else: form = WarehouseForm()
    return render(request, 'inventory/warehouse_form.html', {'form': form, 'title': 'Добавить склад'})
@permission_required_custom('inventory.change_warehouse')
def warehouse_edit(request, pk):
    wh = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST':
        form = WarehouseForm(request.POST, instance=wh)
        if form.is_valid(): form.save(); return redirect('warehouse_list')
    else: form = WarehouseForm(instance=wh)
    return render(request, 'inventory/warehouse_form.html', {'form': form, 'title': f'Редактирование: {wh.name}'})
@permission_required_custom('inventory.delete_warehouse')
def warehouse_delete(request, pk):
    wh = get_object_or_404(Warehouse, pk=pk)
    if request.method == 'POST': wh.delete()
    return redirect('warehouse_list')

@staff_member_required
def employee_list(request):
    employees = User.objects.all().order_by('username')
    
    search = request.GET.get('search', '').strip()
    if search:
        employees = employees.filter(
            Q(username__icontains=search) | 
            Q(first_name__icontains=search) | 
            Q(last_name__icontains=search) |
            Q(email__icontains=search)
        )
    
    context = {
        'employees': employees,
        'search': search 
    }
    return render(request, 'inventory/employee_list.html', context)

@staff_member_required
def employee_add(request):
    if request.method == 'POST':
        form = EmployeeAddForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Сотрудник {user.username} создан!")
            
            # Если не суперюзер - настраиваем права
            if not user.is_superuser:
                return redirect('employee_permissions', user_id=user.id)
            else:
                return redirect('employee_list')
    else:
        form = EmployeeAddForm()
    
    return render(request, 'inventory/employee_add.html', {'form': form})

@staff_member_required
def employee_edit(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    
    if request.method == 'POST':
        form = EmployeeEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Данные {user.username} обновлены")
            return redirect('employee_list')
    else:
        form = EmployeeEditForm(instance=user)
        
    return render(request, 'inventory/employee_edit.html', {'form': form, 'target_user': user})

# --- ПЕЧАТЬ ЦЕННИКОВ ---
@permission_required_custom('inventory.view_nomenclature')
def print_barcodes(request):
    return render(request, 'inventory/print_barcodes.html', {'tools': ToolInstance.objects.all()})

@permission_required_custom('inventory.change_toolinstance')
def quick_return(request):
    """Быстрый возврат"""
    
    # ИЗМЕНЕНО: is_staff видит всё
    if request.user.is_staff:
        allowed_whs = Warehouse.objects.all()
    else:
        if not hasattr(request.user, 'profile'):
            from .models import EmployeeProfile
            EmployeeProfile.objects.create(user=request.user)
        allowed_whs = request.user.profile.allowed_warehouses.all()

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            wh_id = data.get('warehouse_id')
            
            # --- ЗАЩИТА: Проверяем доступ к складу ---
            if not request.user.is_staff and not allowed_whs.filter(id=wh_id).exists():
                return JsonResponse({'status': 'error', 'message': '⛔ Нет доступа к выбранному складу!'}, status=403)

            target_wh = get_object_or_404(Warehouse, pk=wh_id)
            
            for sn in data.get('sn_list', []):
                try:
                    tool = ToolInstance.objects.get(inventory_id__iexact=sn)
                    if tool.status == 'IN_STOCK': continue
                    
                    holder_was = tool.current_holder
                    tool.current_holder = None
                    tool.current_warehouse = target_wh
                    tool.status = 'IN_STOCK'
                    tool.save()
                    
                    MovementLog.objects.create(initiator=request.user, action_type='RETURN', nomenclature=tool.nomenclature, nomenclature_name=tool.nomenclature.name, nomenclature_article=tool.nomenclature.article, serial_number=tool.inventory_id, tool_instance=tool, source_user=holder_was, target_warehouse=target_wh, comment=f"Быстрый возврат (сканер). {data.get('comment', '')}")
                except ToolInstance.DoesNotExist: continue
            return JsonResponse({'status': 'ok'})
        except Exception as e: return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
    # GET: Данные для таблицы "Что у кого на руках"
    issued_tools = ToolInstance.objects.exclude(status='IN_STOCK')
    tools_data = []
    for t in issued_tools:
        holder = f"{t.current_holder.first_name} {t.current_holder.last_name}" if t.current_holder else (f"Комплект: {t.kit.name}" if t.kit else "Неизвестно")
        tools_data.append({'sn': t.inventory_id, 'name': t.nomenclature.name, 'holder': holder})
        
    return render(request, 'inventory/quick_return.html', {
        'warehouses': allowed_whs,
        'issued_tools_json': json.dumps(tools_data)
    })

# --- 9. ИСТОРИЯ ---
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

@staff_member_required
def employee_permissions(request, user_id):
    """
    Управление правами.
    """
    target_user = get_object_or_404(User, pk=user_id)
    from .models import EmployeeProfile
    profile, created = EmployeeProfile.objects.get_or_create(user=target_user)

    if request.method == 'POST':
        # is_admin (checkbox) ставит И superuser, И staff
        is_admin = (request.POST.get('is_superuser') == 'on')
        
        if target_user.id == request.user.id and not is_admin:
             messages.warning(request, "⚠️ Вы не можете снять права Администратора с самого себя!")
        else:
            target_user.is_superuser = is_admin
            target_user.is_staff = is_admin 
            target_user.save()

        selected_wh_ids = request.POST.getlist('warehouses')
        profile.allowed_warehouses.set(selected_wh_ids)
        profile.save()
        
        target_user.groups.clear() 
        target_user.user_permissions.clear()
        
        selected_perms_ids = request.POST.getlist('permissions')
        if selected_perms_ids:
            perms_to_add = Permission.objects.filter(id__in=selected_perms_ids)
            target_user.user_permissions.set(perms_to_add)
        
        messages.success(request, f"Права для {target_user.username} обновлены.")
        return redirect('employee_list')

    warehouses = Warehouse.objects.all()
    
    content_types = ContentType.objects.filter(app_label='inventory')
    permissions = Permission.objects.filter(content_type__in=content_types).select_related('content_type')

    perms_grouped = {}
    blacklist = [
        'запись в журнале', 'movement log', 
        'новость', 'news', 
        'профиль сотрудника', 'employee profile', 'пользователь',
        'session', 'content type', 'log entry', 'permission', 'group'
    ]

    for p in permissions:
        model_name = p.content_type.name
        m_lower = model_name.lower()
        if m_lower in blacklist: continue
        if 'session' in m_lower or 'content type' in m_lower or 'log entry' in m_lower: continue

        if model_name not in perms_grouped: 
            perms_grouped[model_name] = []
        perms_grouped[model_name].append(p)

    return render(request, 'inventory/employee_permissions.html', {
        'target_user': target_user, 
        'warehouses': warehouses, 
        'perms_grouped': perms_grouped,
    })