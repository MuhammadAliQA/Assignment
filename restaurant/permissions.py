from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


ROLE_GROUPS = {
    "manager": "Manager",
    "waiter": "Waiter",
    "chef": "Chef",
    "cashier": "Cashier",
    "customer": "Customer",
}


def role_required(*roles):
    allowed_groups = {ROLE_GROUPS[r] for r in roles if r in ROLE_GROUPS}

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect("restaurant:login")
            if user.is_superuser:
                return view_func(request, *args, **kwargs)
            user_groups = set(user.groups.values_list("name", flat=True))
            if allowed_groups.intersection(user_groups):
                return view_func(request, *args, **kwargs)
            messages.error(request, "You do not have permission to access this page.")
            return redirect("restaurant:dashboard")

        return _wrapped

    return decorator
