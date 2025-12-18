from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # ГЛАВНАЯ (ДАШБОРД)
    path('', views.index, name='index'),
    path('news/add/', views.news_add, name='news_add'),      
    path('news/<int:pk>/delete/', views.news_delete, name='news_delete'), 
    
    # СПИСОК ТОВАРОВ (БЫВШАЯ ГЛАВНАЯ)
    path('tools/', views.tool_list, name='tool_list'),

    path('login/', auth_views.LoginView.as_view(template_name='inventory/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    path('history/', views.history_list, name='history_list'),

    # Автомобили
    path('cars/', views.car_list, name='car_list'),
    path('cars/create/', views.car_create, name='car_create'),
    path('cars/<int:car_id>/edit/', views.car_edit, name='car_edit'),
    path('cars/<int:car_id>/delete/', views.car_delete, name='car_delete'),
    path('cars/<int:car_id>/issue/', views.car_issue, name='car_issue'),
    path('cars/<int:car_id>/return/', views.car_return, name='car_return'),
    path('cars/<int:car_id>/to_maintenance/', views.car_to_maintenance, name='car_to_maintenance'),
    path('cars/<int:car_id>/from_maintenance/', views.car_return_from_maintenance, name='car_return_from_maintenance'),
    path('cars/<int:car_id>/to_ti/', views.car_to_tech_inspection, name='car_to_tech_inspection'),
    path('cars/<int:car_id>/from_ti/', views.car_return_from_tech_inspection, name='car_return_from_tech_inspection'),
    path('cars/<int:car_id>/broken/', views.car_mark_broken, name='car_mark_broken'),
    path('cars/<int:car_id>/fixed/', views.car_mark_fixed, name='car_mark_fixed'),

    path('tool/add/', views.tool_add, name='tool_add'),
    path('tool/<int:tool_id>/edit/', views.tool_edit, name='tool_edit'),
    path('tool/<int:tool_id>/issue/', views.tool_issue, name='tool_issue'),
    path('tool/<int:tool_id>/return/', views.tool_return, name='tool_return'),
    path('tool/<int:tool_id>/writeoff/', views.tool_writeoff, name='tool_writeoff'),

    path('consumable/<int:pk>/issue/', views.consumable_issue, name='consumable_issue'),
    path('consumable/<int:pk>/return/', views.consumable_return, name='consumable_return'),
    path('consumable/<int:pk>/writeoff/', views.consumable_writeoff, name='consumable_writeoff'),

    path('kits/', views.kit_list, name='kit_list'),
    path('kits/create/', views.kit_create, name='kit_create'),
    path('kits/<int:kit_id>/edit/', views.kit_edit, name='kit_edit'),
    path('kits/<int:kit_id>/add_tool/', views.kit_add_tool, name='kit_add_tool'),
    path('kits/<int:kit_id>/remove_tool/<int:tool_id>/', views.kit_remove_tool, name='kit_remove_tool'),
    path('kits/<int:kit_id>/add_consumable/', views.kit_add_consumable, name='kit_add_consumable'),
    path('kits/<int:kit_id>/remove_consumable/<int:balance_id>/', views.kit_remove_consumable, name='kit_remove_consumable'),
    path('kits/<int:kit_id>/delete/', views.kit_delete, name='kit_delete'),
    path('kits/<int:kit_id>/issue/', views.kit_issue, name='kit_issue'),
    path('kits/<int:kit_id>/return/', views.kit_return, name='kit_return'),

    path('nomenclature/', views.nomenclature_list, name='nomenclature_list'),
    path('nomenclature/<int:pk>/edit/', views.nomenclature_edit, name='nomenclature_edit'),
    path('nomenclature/<int:pk>/delete/', views.nomenclature_delete, name='nomenclature_delete'),

    path('warehouses/', views.warehouse_list, name='warehouse_list'),
    path('warehouses/add/', views.warehouse_add, name='warehouse_add'),
    path('warehouses/<int:pk>/edit/', views.warehouse_edit, name='warehouse_edit'),
    path('warehouses/<int:pk>/delete/', views.warehouse_delete, name='warehouse_delete'),

    path('employees/', views.employee_list, name='employee_list'),
    path('employees/add/', views.employee_add, name='employee_add'),
    path('employees/<int:user_id>/edit/', views.employee_edit, name='employee_edit'),

    path('print/barcodes/', views.print_barcodes, name='print_barcodes'),
    path('quick/return/', views.quick_return, name='quick_return'),

    path('bulk_issue/', views.bulk_issue, name='bulk_issue'),
    path('api/employee/<int:employee_id>/items/', views.get_employee_items, name='get_employee_items'),
    path('api/return/item/', views.api_return_item, name='api_return_item'),
    path('api/writeoff/item/', views.api_writeoff_item, name='api_writeoff_item'),
    path('tool/<int:tool_id>/take_self/', views.tool_take_self, name='tool_take_self'),
    path('tool/<int:tool_id>/return_self/', views.tool_return_self, name='tool_return_self'),
    path('employees/<int:user_id>/permissions/', views.employee_permissions, name='employee_permissions'),
]