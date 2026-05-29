from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class MenuItem(models.Model):
    CATEGORY_CHOICES = [
        ("starter", "Starter"),
        ("main_course", "Main Course"),
        ("dessert", "Dessert"),
        ("beverage", "Beverage"),
    ]

    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class Starter(MenuItem):
    class Meta:
        verbose_name = "Starter"
        verbose_name_plural = "Starters"

    def save(self, *args, **kwargs):
        self.category = "starter"
        super().save(*args, **kwargs)


class MainCourse(MenuItem):
    class Meta:
        verbose_name = "Main Course"
        verbose_name_plural = "Main Courses"

    def save(self, *args, **kwargs):
        self.category = "main_course"
        super().save(*args, **kwargs)


class Dessert(MenuItem):
    class Meta:
        verbose_name = "Dessert"
        verbose_name_plural = "Desserts"

    def save(self, *args, **kwargs):
        self.category = "dessert"
        super().save(*args, **kwargs)


class Beverage(MenuItem):
    class Meta:
        verbose_name = "Beverage"
        verbose_name_plural = "Beverages"

    def save(self, *args, **kwargs):
        self.category = "beverage"
        super().save(*args, **kwargs)


class Table(models.Model):
    STATUS_AVAILABLE = "available"
    STATUS_OCCUPIED = "occupied"
    STATUS_RESERVED = "reserved"

    STATUS_CHOICES = [
        (STATUS_AVAILABLE, "Available"),
        (STATUS_OCCUPIED, "Occupied"),
        (STATUS_RESERVED, "Reserved"),
    ]

    table_number = models.PositiveIntegerField(unique=True)
    seats = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_AVAILABLE)

    class Meta:
        ordering = ["table_number"]

    def __str__(self):
        return f"Table {self.table_number}"

    def is_available(self):
        return self.status == self.STATUS_AVAILABLE


class Reservation(models.Model):
    STATUS_PENDING = "pending"
    STATUS_CONFIRMED = "confirmed"
    STATUS_CANCELLED = "cancelled"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_CONFIRMED, "Confirmed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=30)
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="reservations")
    reservation_time = models.DateTimeField()
    number_of_guests = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    table = models.ForeignKey(Table, on_delete=models.SET_NULL, null=True, blank=True, related_name="reservations")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-reservation_time"]

    def __str__(self):
        return f"{self.customer_name} - {self.reservation_time:%Y-%m-%d %H:%M}"

    def clean(self):
        if self.number_of_guests < 1:
            raise ValidationError("Number of guests must be at least 1.")
        if self.reservation_time and self.reservation_time < timezone.now():
            raise ValidationError("Reservation time cannot be in the past.")
        if self.table and self.number_of_guests > self.table.seats:
            raise ValidationError("Guests exceed selected table capacity.")


class Staff(models.Model):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30)

    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class Waiter(Staff):
    pass


class Chef(Staff):
    pass


class Cashier(Staff):
    pass


class Manager(Staff):
    pass


class Order(models.Model):
    STATUS_NEW = "new"
    STATUS_SENT_TO_KITCHEN = "sent_to_kitchen"
    STATUS_PREPARING = "preparing"
    STATUS_READY = "ready"
    STATUS_SERVED = "served"
    STATUS_CANCELLED = "cancelled"
    STATUS_COMPLETED = "completed"

    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_SENT_TO_KITCHEN, "Sent to Kitchen"),
        (STATUS_PREPARING, "Preparing"),
        (STATUS_READY, "Ready"),
        (STATUS_SERVED, "Served"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_COMPLETED, "Completed"),
    ]

    table = models.ForeignKey(Table, on_delete=models.PROTECT, related_name="orders")
    waiter = models.ForeignKey(Waiter, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    customer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    reservation = models.ForeignKey(Reservation, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_NEW)
    order_date = models.DateTimeField(default=timezone.now)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-order_date"]

    def __str__(self):
        return f"Order #{self.id} - Table {self.table.table_number}"

    @property
    def total_amount(self):
        return sum((item.sub_total for item in self.items.all()), Decimal("0.00"))


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.menu_item.name} x{self.quantity}"

    def clean(self):
        if self.quantity < 1:
            raise ValidationError("Quantity must be at least 1.")

    @property
    def sub_total(self):
        return self.unit_price * self.quantity

    def save(self, *args, **kwargs):
        self.unit_price = self.menu_item.price
        super().save(*args, **kwargs)


class Bill(models.Model):
    STATUS_UNPAID = "unpaid"
    STATUS_PAID = "paid"

    STATUS_CHOICES = [
        (STATUS_UNPAID, "Unpaid"),
        (STATUS_PAID, "Paid"),
    ]

    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name="bill")
    bill_date = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_UNPAID)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    def __str__(self):
        return f"Bill #{self.id} for Order #{self.order.id}"

    def clean(self):
        if self.discount_amount < Decimal("0.00"):
            raise ValidationError("Discount cannot be negative.")

    @property
    def total_amount(self):
        subtotal = sum((line.sub_total for line in self.lines.all()), Decimal("0.00"))
        total = subtotal - self.discount_amount
        return max(total, Decimal("0.00"))


class BillLineItem(models.Model):
    bill = models.ForeignKey(Bill, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=140)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.description} x{self.quantity}"

    @property
    def sub_total(self):
        return self.quantity * self.unit_price


class OrderHistoryLog(models.Model):
    """
    Singleton history log persisted in DB.
    """

    singleton_key = models.CharField(max_length=30, unique=True, default="ORDER_HISTORY")
    logs = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Order History Log"
        verbose_name_plural = "Order History Log"

    def __str__(self):
        return "Order History Log"

    @classmethod
    def get_instance(cls):
        instance, _ = cls.objects.get_or_create(singleton_key="ORDER_HISTORY")
        return instance

    def add_order(self, order):
        line = (
            f"[{timezone.now():%Y-%m-%d %H:%M:%S}] "
            f"Order #{order.id} | Table {order.table.table_number} | Status: {order.status} | Total: {order.total_amount}\n"
        )
        self.logs = (self.logs or "") + line
        self.save(update_fields=["logs", "updated_at"])
