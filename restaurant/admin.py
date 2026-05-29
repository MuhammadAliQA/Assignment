from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import (
    Beverage,
    Bill,
    BillLineItem,
    Cashier,
    Chef,
    Dessert,
    MainCourse,
    Manager,
    MenuItem,
    Order,
    OrderHistoryLog,
    OrderItem,
    Reservation,
    Starter,
    Table,
    Waiter,
)


class OrderItemInline(TabularInline):
    model = OrderItem
    extra = 0


class BillLineItemInline(TabularInline):
    model = BillLineItem
    extra = 0


@admin.register(Order)
class OrderAdmin(ModelAdmin):
    list_display = ("id", "table", "status", "order_date")
    list_filter = ("status",)
    inlines = [OrderItemInline]


@admin.register(Bill)
class BillAdmin(ModelAdmin):
    list_display = ("id", "order", "status", "bill_date")
    list_filter = ("status",)
    inlines = [BillLineItemInline]


admin.site.register([
    MenuItem,
    Starter,
    MainCourse,
    Dessert,
    Beverage,
    Table,
    Reservation,
    Waiter,
    Chef,
    Cashier,
    Manager,
    OrderHistoryLog,
])

admin.site.site_header = "BitePlate Administration"
admin.site.site_title = "BitePlate Admin"
admin.site.index_title = "Smart Restaurant Management"
