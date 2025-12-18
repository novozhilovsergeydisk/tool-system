from django.shortcuts import redirect
from django.contrib import messages

def permission_required_custom(perm):
    """
    Умный декоратор:
    Пускает, если пользователь - Суперюзер/Админ (is_staff)
    ИЛИ если у него есть конкретная галочка (perm).
    """
    def decorator(view_func):
        def _wrapped_view(request, *args, **kwargs):
            # 1. Если пользователь не вошел - на вход
            if not request.user.is_authenticated:
                return redirect('login')
                
            # 2. Если Суперюзер или Персонал - пускаем везде
            if request.user.is_superuser or request.user.is_staff:
                return view_func(request, *args, **kwargs)
            
            # 3. Если есть конкретное право (которое мы передали в perm)
            if request.user.has_perm(perm):
                return view_func(request, *args, **kwargs)
            
            # 4. Иначе - отказ
            messages.error(request, "⛔ У вас нет прав для этой операции.")
            return redirect(request.META.get('HTTP_REFERER', 'index'))
            
        return _wrapped_view
    return decorator