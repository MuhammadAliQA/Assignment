from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import Group
from django.http import HttpResponse
from django.db import transaction
from datetime import datetime
from datetime import timedelta
from decimal import Decimal
from decimal import InvalidOperation

from django.db.models import Count, DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .adapters import KitchenDisplayAdapter, LegacyKitchenDisplaySystem
from .commands import CancelOrderCommand, KitchenQueueInvoker, PrepareOrderCommand
from .forms import BillForm, MenuItemForm, OrderForm, OrderItemForm, OrderStatusForm, RegisterForm, ReservationForm, StaffCreateForm, TableForm
from .models import Bill, BillLineItem, Cashier, Chef, Manager, MenuItem, Order, OrderHistoryLog, OrderItem, Reservation, Table, Waiter
from .observers import build_default_notifier
from .permissions import role_required
from .pricing import PricingEngine


def _is_customer(user):
    return user.is_authenticated and user.groups.filter(name="Customer").exists() and not user.is_superuser


def _customer_dashboard_context(user):
    customer_orders = Order.objects.filter(customer=user).prefetch_related("items__menu_item")
    customer_reservations = Reservation.objects.filter(customer=user)
    active_order = customer_orders.exclude(status__in=[Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]).first()
    return {
        "reservation_count": customer_reservations.count(),
        "active_orders": customer_orders.exclude(status__in=[Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]).count(),
        "completed_orders": customer_orders.filter(status=Order.STATUS_COMPLETED).count(),
        "latest_reservation": customer_reservations.order_by("-reservation_time").first(),
        "latest_order": customer_orders.first(),
        "active_order": active_order,
        "menu_count": MenuItem.objects.filter(is_active=True).count(),
    }


def _get_customer_owned_order(request, order_id):
    queryset = Order.objects.select_related("table", "waiter", "customer", "reservation").prefetch_related("items__menu_item")
    if _is_customer(request.user):
        return get_object_or_404(queryset, id=order_id, customer=request.user)
    return get_object_or_404(queryset, id=order_id)


def _get_customer_owned_reservation(request, reservation_id):
    queryset = Reservation.objects.select_related("table", "customer")
    if _is_customer(request.user):
        return get_object_or_404(queryset, id=reservation_id, customer=request.user)
    return get_object_or_404(queryset, id=reservation_id)


def register(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            customer_group, _ = Group.objects.get_or_create(name="Customer")
            user.groups.add(customer_group)
            login(request, user)
            messages.success(request, "Registration complete. Welcome to BitePlate.")
            return redirect("restaurant:dashboard")
    else:
        form = RegisterForm()
    return render(request, "restaurant/register.html", {"form": form})


@login_required
def dashboard(request):
    if _is_customer(request.user):
        return render(request, "restaurant/customer_dashboard.html", _customer_dashboard_context(request.user))
    menu_breakdown = MenuItem.objects.values("category").annotate(count=Count("id")).order_by("category")
    context = {
        "reservation_count": Reservation.objects.count(),
        "active_orders": Order.objects.exclude(status__in=[Order.STATUS_COMPLETED, Order.STATUS_CANCELLED]).count(),
        "available_tables": Table.objects.filter(status=Table.STATUS_AVAILABLE).count(),
        "unpaid_bills": Bill.objects.filter(status=Bill.STATUS_UNPAID).count(),
        "menu_count": MenuItem.objects.count(),
        "menu_breakdown": menu_breakdown,
    }
    return render(request, "restaurant/dashboard.html", context)


@role_required("manager", "waiter", "customer")
def reservation_list(request):
    reservations = Reservation.objects.select_related("table", "customer")
    if _is_customer(request.user):
        reservations = reservations.filter(customer=request.user)
    return render(request, "restaurant/reservation_list.html", {"reservations": reservations})


@role_required("manager", "waiter", "customer")
def reservation_create(request):
    if request.method == "POST":
        form = ReservationForm(request.POST, user=request.user)
        if form.is_valid():
            reservation = form.save(commit=False)
            if _is_customer(request.user):
                reservation.customer = request.user
                reservation.status = Reservation.STATUS_PENDING
            reservation.save()
            if reservation.table and reservation.status in [Reservation.STATUS_PENDING, Reservation.STATUS_CONFIRMED]:
                reservation.table.status = Table.STATUS_RESERVED
                reservation.table.save(update_fields=["status"])
            messages.success(request, "Reservation created.")
            return redirect("restaurant:reservation_list")
    else:
        initial = {}
        if _is_customer(request.user):
            initial["customer_name"] = request.user.get_full_name() or request.user.username
        form = ReservationForm(initial=initial, user=request.user)
    return render(request, "restaurant/form.html", {"form": form, "title": "Create Reservation"})


@role_required("manager", "waiter", "customer")
def reservation_edit(request, reservation_id):
    reservation = _get_customer_owned_reservation(request, reservation_id)
    if request.method == "POST":
        form = ReservationForm(request.POST, instance=reservation, user=request.user)
        if form.is_valid():
            reservation = form.save(commit=False)
            if _is_customer(request.user):
                reservation.status = Reservation.STATUS_PENDING
            reservation.save()
            messages.success(request, "Reservation updated.")
            return redirect("restaurant:reservation_list")
    else:
        form = ReservationForm(instance=reservation, user=request.user)
    return render(request, "restaurant/form.html", {"form": form, "title": "Edit Reservation"})


@role_required("manager", "waiter", "customer")
def reservation_delete(request, reservation_id):
    reservation = _get_customer_owned_reservation(request, reservation_id)
    if request.method == "POST":
        if reservation.table and reservation.table.status == Table.STATUS_RESERVED and reservation.table.reservations.exclude(id=reservation.id).count() == 0:
            reservation.table.status = Table.STATUS_AVAILABLE
            reservation.table.save(update_fields=["status"])
        reservation.delete()
        messages.success(request, "Reservation deleted.")
        return redirect("restaurant:reservation_list")
    return render(request, "restaurant/confirm_delete.html", {"title": "Delete Reservation", "object": reservation})


@role_required("manager", "waiter")
def table_list(request):
    return render(request, "restaurant/table_list.html", {"tables": Table.objects.all()})


@role_required("manager", "waiter")
def table_create(request):
    if request.method == "POST":
        form = TableForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Table saved.")
            return redirect("restaurant:table_list")
    else:
        form = TableForm()
    return render(request, "restaurant/form.html", {"form": form, "title": "Create Table"})


@login_required
def menu_list(request):
    menu_items = MenuItem.objects.all()
    return render(request, "restaurant/menu_list.html", {"menu_items": menu_items})


@role_required("manager")
def menu_create(request):
    if request.method == "POST":
        form = MenuItemForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Menu item created.")
            return redirect("restaurant:menu_list")
    else:
        form = MenuItemForm()
    return render(request, "restaurant/form.html", {"form": form, "title": "Create Menu Item"})


@role_required("manager")
def menu_edit(request, menu_id):
    menu_item = get_object_or_404(MenuItem, id=menu_id)
    if request.method == "POST":
        form = MenuItemForm(request.POST, instance=menu_item)
        if form.is_valid():
            form.save()
            messages.success(request, "Menu item updated.")
            return redirect("restaurant:menu_list")
    else:
        form = MenuItemForm(instance=menu_item)
    return render(request, "restaurant/form.html", {"form": form, "title": "Edit Menu Item"})


@role_required("manager")
def menu_delete(request, menu_id):
    menu_item = get_object_or_404(MenuItem, id=menu_id)
    if request.method == "POST":
        menu_item.delete()
        messages.success(request, "Menu item deleted.")
        return redirect("restaurant:menu_list")
    return render(request, "restaurant/confirm_delete.html", {"title": "Delete Menu Item", "object": menu_item})


@role_required("manager", "waiter", "chef", "cashier", "customer")
def order_list(request):
    orders = Order.objects.select_related("table", "waiter", "customer").prefetch_related("items__menu_item")
    if _is_customer(request.user):
        orders = orders.filter(customer=request.user)
    return render(request, "restaurant/order_list.html", {"orders": orders})


@role_required("manager", "waiter", "customer")
def order_create(request):
    if request.method == "POST":
        order_form = OrderForm(request.POST, user=request.user)
        item_form = OrderItemForm(request.POST)
        if order_form.is_valid() and item_form.is_valid():
            order = order_form.save(commit=False)
            if _is_customer(request.user):
                order.customer = request.user
                if order.reservation and order.reservation.customer_id != request.user.id:
                    messages.error(request, "You can only use your own reservation.")
                    return render(
                        request,
                        "restaurant/order_create.html",
                        {"order_form": order_form, "item_form": item_form, "title": "Create Order"},
                    )
            order.save()
            order_item = item_form.save(commit=False)
            order_item.order = order
            order_item.save()
            order.table.status = Table.STATUS_OCCUPIED
            order.table.save(update_fields=["status"])
            messages.success(request, "Order created with first item.")
            return redirect("restaurant:order_detail", order_id=order.id)
    else:
        order_form = OrderForm(user=request.user)
        item_form = OrderItemForm()
    return render(
        request,
        "restaurant/order_create.html",
        {"order_form": order_form, "item_form": item_form, "title": "Create Order"},
    )


@role_required("manager", "waiter", "customer")
def order_detail(request, order_id):
    order = _get_customer_owned_order(request, order_id)
    if request.method == "POST":
        if order.status in [Order.STATUS_CANCELLED, Order.STATUS_COMPLETED]:
            messages.error(request, "Cannot modify a cancelled/completed order.")
            return redirect("restaurant:order_detail", order_id=order.id)
        form = OrderItemForm(request.POST)
        if form.is_valid():
            order_item = form.save(commit=False)
            order_item.order = order
            order_item.save()
            messages.success(request, "Item added.")
            return redirect("restaurant:order_detail", order_id=order.id)
    else:
        form = OrderItemForm()
    return render(request, "restaurant/order_detail.html", {"order": order, "form": form})


@require_POST
@role_required("manager", "waiter")
def send_to_kitchen(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if order.status not in [Order.STATUS_NEW, Order.STATUS_SERVED]:
        messages.error(request, "Order cannot be sent to kitchen from current status.")
        return redirect("restaurant:order_detail", order_id=order.id)
    if not order.items.exists():
        messages.error(request, "Order must contain at least one item.")
        return redirect("restaurant:order_detail", order_id=order.id)
    order.status = Order.STATUS_SENT_TO_KITCHEN
    order.save(update_fields=["status"])

    adapter = KitchenDisplayAdapter(LegacyKitchenDisplaySystem())
    adapter_response = adapter.send_order(order)

    notifier = build_default_notifier()
    notifier.notify(order, "Order sent to kitchen")

    messages.success(request, f"Order sent to kitchen. {adapter_response}")
    return redirect("restaurant:order_detail", order_id=order.id)


@role_required("manager", "chef")
def kitchen_queue(request):
    queue = Order.objects.filter(status__in=[Order.STATUS_SENT_TO_KITCHEN, Order.STATUS_PREPARING, Order.STATUS_READY])
    return render(request, "restaurant/kitchen_queue.html", {"queue": queue})


@role_required("manager", "chef")
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == "POST":
        form = OrderStatusForm(request.POST)
        if form.is_valid():
            new_status = form.cleaned_data["status"]
            if new_status == Order.STATUS_CANCELLED:
                command = CancelOrderCommand(order=order)
            else:
                command = PrepareOrderCommand(order=order, new_status=new_status)
            KitchenQueueInvoker.run(request, command)
            notifier = build_default_notifier()
            notifier.notify(order, f"Status changed to {order.get_status_display()}")
            messages.success(request, "Order status updated.")
    return redirect("restaurant:kitchen_queue")


@require_POST
@role_required("manager", "chef")
def undo_last_kitchen_action(request):
    order = KitchenQueueInvoker.undo_last(request)
    if order:
        messages.success(request, f"Last action undone for Order #{order.id}.")
    else:
        messages.warning(request, "No kitchen action to undo.")
    return redirect("restaurant:kitchen_queue")


@role_required("manager", "cashier")
def bill_list(request):
    bills = Bill.objects.select_related("order", "order__table").prefetch_related("lines")
    return render(request, "restaurant/bill_list.html", {"bills": bills})


@require_POST
@role_required("manager", "cashier")
def generate_bill(request, order_id):
    order = get_object_or_404(Order.objects.prefetch_related("items__menu_item"), id=order_id)
    if order.status == Order.STATUS_CANCELLED:
        messages.error(request, "Cannot generate bill for cancelled order.")
        return redirect("restaurant:order_detail", order_id=order.id)
    if not order.items.exists():
        messages.error(request, "Cannot generate bill for empty order.")
        return redirect("restaurant:order_detail", order_id=order.id)
    bill, created = Bill.objects.get_or_create(order=order)

    with transaction.atomic():
        bill.lines.all().delete()
        for item in order.items.all():
            BillLineItem.objects.create(
                bill=bill,
                description=item.menu_item.name,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )

    messages.success(request, "Bill generated/refreshed.")
    return redirect("restaurant:bill_detail", bill_id=bill.id)


@role_required("manager", "cashier")
def bill_detail(request, bill_id):
    bill = get_object_or_404(Bill.objects.select_related("order", "order__table"), id=bill_id)
    subtotal = sum((line.sub_total for line in bill.lines.all()), Decimal("0.00"))
    if request.method == "POST":
        previous_status = bill.status
        form = BillForm(request.POST, instance=bill)
        if form.is_valid():
            pricing_mode = form.cleaned_data.get("pricing_mode") or "standard"
            strategy = PricingEngine.get_strategy(pricing_mode)
            strategy_total, strategy_discount, strategy_label = strategy.calculate_total(subtotal)
            manual_discount = form.cleaned_data["discount_amount"]
            total_discount = strategy_discount + manual_discount
            bill = form.save(commit=False)
            bill.discount_amount = total_discount
            bill.save()
            if bill.status == Bill.STATUS_PAID and previous_status != Bill.STATUS_PAID:
                order = bill.order
                order.status = Order.STATUS_COMPLETED
                order.save(update_fields=["status"])
                order.table.status = Table.STATUS_AVAILABLE
                order.table.save(update_fields=["status"])
                OrderHistoryLog.get_instance().add_order(order)
            messages.success(request, "Bill updated.")
            return redirect("restaurant:bill_detail", bill_id=bill.id)
    else:
        form = BillForm(instance=bill)
    preview_mode = form["pricing_mode"].value() or "standard"
    preview_strategy = PricingEngine.get_strategy(preview_mode)
    preview_total, preview_discount, preview_label = preview_strategy.calculate_total(subtotal)
    context = {
        "bill": bill,
        "form": form,
        "strategy_preview_total": preview_total,
        "strategy_preview_discount": preview_discount,
        "strategy_preview_label": preview_label,
    }
    return render(request, "restaurant/bill_detail.html", context)


@role_required("manager", "cashier")
def bill_receipt(request, bill_id):
    bill = get_object_or_404(Bill.objects.select_related("order", "order__table"), id=bill_id)
    subtotal = sum((line.sub_total for line in bill.lines.all()), Decimal("0.00"))
    tax_rate = Decimal("0.12")
    tax_amount = (subtotal * tax_rate).quantize(Decimal("0.01"))
    try:
        tip_amount = Decimal(request.GET.get("tip", "0") or "0").quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        tip_amount = Decimal("0.00")
    net_before_tax = max(subtotal - bill.discount_amount, Decimal("0.00"))
    grand_total = (net_before_tax + tax_amount + tip_amount).quantize(Decimal("0.01"))
    context = {
        "bill": bill,
        "subtotal": subtotal,
        "tax_rate": tax_rate,
        "tax_amount": tax_amount,
        "tip_amount": tip_amount,
        "grand_total": grand_total,
    }
    return render(request, "restaurant/receipt.html", context)


@role_required("manager")
def order_history(request):
    history = OrderHistoryLog.get_instance()
    history_rows = [row for row in history.logs.split("\n") if row.strip()]
    return render(request, "restaurant/order_history.html", {"history_rows": history_rows})


@role_required("manager")
def manager_report(request):
    report_date = timezone.localdate()
    date_input = request.GET.get("date")
    if date_input:
        try:
            report_date = datetime.strptime(date_input, "%Y-%m-%d").date()
        except ValueError:
            messages.warning(request, "Invalid date filter; showing today's report.")
    today = Bill.objects.filter(status=Bill.STATUS_PAID, bill_date__date=report_date)

    today_sales = BillLineItem.objects.filter(bill__in=today).aggregate(
        gross=Coalesce(
            Sum(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=12, decimal_places=2)),
            Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
        )
    )["gross"]
    discount_total = today.aggregate(
        discount=Coalesce(
            Sum("discount_amount"),
            Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
        )
    )["discount"]
    net_sales = today_sales - discount_total
    avg_ticket = (net_sales / today.count()).quantize(Decimal("0.01")) if today.count() else Decimal("0.00")

    top_items = (
        OrderItem.objects.values("menu_item__name")
        .annotate(quantity_sold=Sum("quantity"), order_count=Count("order", distinct=True))
        .order_by("-quantity_sold")[:5]
    )

    order_status_map = dict(Order.STATUS_CHOICES)
    order_status_summary = [
        {"status": row["status"], "label": order_status_map.get(row["status"], row["status"]), "count": row["count"]}
        for row in Order.objects.values("status").annotate(count=Count("id")).order_by("status")
    ]

    top_waiters = (
        Order.objects.filter(status=Order.STATUS_COMPLETED, order_date__date=report_date, waiter__isnull=False)
        .values("waiter__name")
        .annotate(completed_orders=Count("id"))
        .order_by("-completed_orders")[:5]
    )

    start_date = report_date - timedelta(days=6)
    trend_queryset = (
        BillLineItem.objects.filter(
            bill__status=Bill.STATUS_PAID,
            bill__bill_date__date__gte=start_date,
            bill__bill_date__date__lte=report_date,
        )
        .annotate(day=TruncDate("bill__bill_date"))
        .values("day")
        .annotate(
            total=Coalesce(
                Sum(F("quantity") * F("unit_price"), output_field=DecimalField(max_digits=12, decimal_places=2)),
                Value(Decimal("0.00"), output_field=DecimalField(max_digits=12, decimal_places=2)),
            )
        )
        .order_by("day")
    )
    sales_map = {row["day"]: row["total"] for row in trend_queryset}
    sales_trend = []
    for i in range(7):
        d = start_date + timedelta(days=i)
        sales_trend.append({"day": d.strftime("%Y-%m-%d"), "value": sales_map.get(d, Decimal("0.00"))})

    context = {
        "total_paid_bills": today.count(),
        "today_sales": today_sales,
        "discount_total": discount_total,
        "net_sales": net_sales,
        "avg_ticket": avg_ticket,
        "top_items": top_items,
        "top_waiters": top_waiters,
        "sales_trend": sales_trend,
        "order_status_summary": order_status_summary,
        "report_date": report_date,
    }
    return render(request, "restaurant/manager_report.html", context)


@role_required("manager")
def manager_report_csv(request):
    report_date = timezone.localdate()
    date_input = request.GET.get("date")
    if date_input:
        try:
            report_date = datetime.strptime(date_input, "%Y-%m-%d").date()
        except ValueError:
            pass

    paid_bills = Bill.objects.filter(status=Bill.STATUS_PAID, bill_date__date=report_date)
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="biteplate-report-{report_date}.csv"'
    response.write("order_id,table,total,discount,bill_date\n")
    for bill in paid_bills.select_related("order", "order__table"):
        response.write(
            f"{bill.order.id},{bill.order.table.table_number},{bill.total_amount},{bill.discount_amount},{bill.bill_date:%Y-%m-%d %H:%M:%S}\n"
        )
    return response


@role_required("manager")
def manage_staff(request):
    context = {
        "waiters": Waiter.objects.all(),
        "chefs": Chef.objects.all(),
        "cashiers": Cashier.objects.all(),
        "managers": Manager.objects.all(),
    }
    return render(request, "restaurant/manage_staff.html", context)


@role_required("manager")
def staff_create(request):
    if request.method == "POST":
        form = StaffCreateForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data["role"]
            payload = {"name": form.cleaned_data["name"], "phone": form.cleaned_data["phone"]}
            role_map = {
                "waiter": Waiter,
                "chef": Chef,
                "cashier": Cashier,
                "manager": Manager,
            }
            role_map[role].objects.create(**payload)
            messages.success(request, f"{role.title()} created.")
            return redirect("restaurant:manage_staff")
    else:
        form = StaffCreateForm()
    return render(request, "restaurant/form.html", {"form": form, "title": "Create Staff"})


def _get_staff_model(role):
    return {"waiter": Waiter, "chef": Chef, "cashier": Cashier, "manager": Manager}.get(role)


@role_required("manager")
def staff_edit(request, role, staff_id):
    model = _get_staff_model(role)
    if not model:
        return redirect("restaurant:manage_staff")
    staff = get_object_or_404(model, id=staff_id)
    if request.method == "POST":
        name = request.POST.get("name", "").strip()
        phone = request.POST.get("phone", "").strip()
        if name and phone:
            staff.name = name
            staff.phone = phone
            staff.save(update_fields=["name", "phone"])
            messages.success(request, "Staff updated.")
            return redirect("restaurant:manage_staff")
        messages.error(request, "Name and phone are required.")
    return render(request, "restaurant/staff_edit.html", {"staff": staff, "role": role})


@role_required("manager")
def staff_delete(request, role, staff_id):
    model = _get_staff_model(role)
    if not model:
        return redirect("restaurant:manage_staff")
    staff = get_object_or_404(model, id=staff_id)
    if request.method == "POST":
        staff.delete()
        messages.success(request, "Staff deleted.")
        return redirect("restaurant:manage_staff")
    return render(request, "restaurant/confirm_delete.html", {"title": "Delete Staff", "object": staff})
