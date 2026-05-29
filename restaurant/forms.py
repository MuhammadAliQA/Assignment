from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.db.models import Q
from django.utils import timezone

from .models import Bill, MenuItem, Order, OrderItem, Reservation, Table


class ReservationForm(forms.ModelForm):
    class Meta:
        model = Reservation
        fields = ["customer_name", "customer_phone", "reservation_time", "number_of_guests", "table", "status"]
        widgets = {
            "reservation_time": forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reservation_time"].input_formats = ("%Y-%m-%dT%H:%M",)
        self.user = user
        self.fields["table"].queryset = Table.objects.filter(status=Table.STATUS_AVAILABLE)
        if user and user.is_authenticated and user.groups.filter(name="Customer").exists():
            self.fields["status"].widget = forms.HiddenInput()
            self.fields["status"].required = False

    def clean(self):
        cleaned = super().clean()
        reservation_time = cleaned.get("reservation_time")
        table = cleaned.get("table")
        guests = cleaned.get("number_of_guests")
        if reservation_time and reservation_time < timezone.now():
            self.add_error("reservation_time", "Reservation time cannot be in the past.")
        if table and guests and guests > table.seats:
            self.add_error("number_of_guests", "Guests exceed selected table capacity.")
        return cleaned


class TableForm(forms.ModelForm):
    class Meta:
        model = Table
        fields = ["table_number", "seats", "status"]


class MenuItemForm(forms.ModelForm):
    class Meta:
        model = MenuItem
        fields = ["name", "description", "price", "category", "is_active"]


class OrderForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["table", "waiter", "reservation", "notes"]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields["table"].queryset = Table.objects.exclude(status=Table.STATUS_OCCUPIED)
        if user and user.is_authenticated and user.groups.filter(name="Customer").exists():
            self.fields["waiter"].widget = forms.HiddenInput()
            self.fields["waiter"].required = False
            reserved_table_ids = Reservation.objects.filter(
                customer=user,
                status__in=[Reservation.STATUS_PENDING, Reservation.STATUS_CONFIRMED],
                table__isnull=False,
            ).values_list("table_id", flat=True)
            self.fields["table"].queryset = Table.objects.filter(
                Q(status=Table.STATUS_AVAILABLE) | Q(id__in=reserved_table_ids)
            ).distinct()
            self.fields["reservation"].queryset = Reservation.objects.filter(
                customer=user,
                status__in=[Reservation.STATUS_PENDING, Reservation.STATUS_CONFIRMED],
            )

    def clean_table(self):
        table = self.cleaned_data["table"]
        if table.status == Table.STATUS_OCCUPIED:
            raise forms.ValidationError("Selected table is occupied.")
        return table


class OrderItemForm(forms.ModelForm):
    class Meta:
        model = OrderItem
        fields = ["menu_item", "quantity"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["menu_item"].queryset = MenuItem.objects.filter(is_active=True)


class OrderStatusForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["status"]


class BillForm(forms.ModelForm):
    PRICING_CHOICES = [
        ("standard", "Standard Pricing"),
        ("happy_hour", "Happy Hour (-20%)"),
        ("loyalty", "Loyalty Card (-10% + free drink)"),
    ]
    pricing_mode = forms.ChoiceField(choices=PRICING_CHOICES, required=False, initial="standard")

    class Meta:
        model = Bill
        fields = ["discount_amount", "status"]

    def clean_discount_amount(self):
        discount = self.cleaned_data["discount_amount"]
        if discount < 0:
            raise forms.ValidationError("Discount cannot be negative.")
        return discount


class StaffCreateForm(forms.Form):
    ROLE_CHOICES = [
        ("waiter", "Waiter"),
        ("chef", "Chef"),
        ("cashier", "Cashier"),
        ("manager", "Manager"),
    ]

    role = forms.ChoiceField(choices=ROLE_CHOICES)
    name = forms.CharField(max_length=120)
    phone = forms.CharField(max_length=30)


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")
