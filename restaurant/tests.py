from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Bill, BillLineItem, MenuItem, Order, OrderHistoryLog, OrderItem, Reservation, Table, Waiter


class RestaurantFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin", password="secret123", email="a@a.com")
        self.client.login(username="admin", password="secret123")
        self.table = Table.objects.create(table_number=1, seats=4, status=Table.STATUS_AVAILABLE)
        self.waiter = Waiter.objects.create(name="Ali", phone="+998901112233")
        self.menu = MenuItem.objects.create(name="Burger", description="", price=Decimal("25.00"), category="main_course")
        self.order = Order.objects.create(table=self.table, waiter=self.waiter, status=Order.STATUS_NEW)
        self.item = OrderItem.objects.create(order=self.order, menu_item=self.menu, quantity=2)

    def test_send_to_kitchen_updates_status(self):
        response = self.client.post(reverse("restaurant:send_to_kitchen", args=[self.order.id]))
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_SENT_TO_KITCHEN)

    def test_generate_and_pay_bill_updates_order_and_table_and_history(self):
        self.client.post(reverse("restaurant:generate_bill", args=[self.order.id]))
        bill = Bill.objects.get(order=self.order)

        response = self.client.post(
            reverse("restaurant:bill_detail", args=[bill.id]),
            {"discount_amount": "5.00", "status": Bill.STATUS_PAID},
        )
        self.assertEqual(response.status_code, 302)

        self.order.refresh_from_db()
        self.table.refresh_from_db()
        history = OrderHistoryLog.get_instance()

        self.assertEqual(self.order.status, Order.STATUS_COMPLETED)
        self.assertEqual(self.table.status, Table.STATUS_AVAILABLE)
        self.assertIn(f"Order #{self.order.id}", history.logs)

    def test_reports_page_loads_without_field_error(self):
        bill = Bill.objects.create(
            order=self.order,
            status=Bill.STATUS_PAID,
            discount_amount=Decimal("2.50"),
            bill_date=timezone.now(),
        )
        BillLineItem.objects.create(
            bill=bill,
            description="Burger",
            quantity=2,
            unit_price=Decimal("25.00"),
        )

        response = self.client.get(reverse("restaurant:manager_report"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Manager Reports")

    def test_paid_bill_does_not_duplicate_history_log(self):
        self.client.post(reverse("restaurant:generate_bill", args=[self.order.id]))
        bill = Bill.objects.get(order=self.order)

        self.client.post(reverse("restaurant:bill_detail", args=[bill.id]), {"discount_amount": "0.00", "status": Bill.STATUS_PAID})
        self.client.post(reverse("restaurant:bill_detail", args=[bill.id]), {"discount_amount": "0.00", "status": Bill.STATUS_PAID})

        history = OrderHistoryLog.get_instance().logs
        self.assertEqual(history.count(f"Order #{self.order.id}"), 1)

    def test_generate_bill_refreshes_line_items(self):
        self.client.post(reverse("restaurant:generate_bill", args=[self.order.id]))
        self.item.quantity = 3
        self.item.save()
        self.client.post(reverse("restaurant:generate_bill", args=[self.order.id]))
        bill = Bill.objects.get(order=self.order)
        line = bill.lines.first()
        self.assertEqual(line.quantity, 3)

    def test_kitchen_undo_restores_previous_status(self):
        self.client.post(reverse("restaurant:update_order_status", args=[self.order.id]), {"status": Order.STATUS_PREPARING})
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_PREPARING)
        self.assertIn("kitchen_last_command", self.client.session)
        response = self.client.post(reverse("restaurant:undo_last_kitchen_action"))
        self.assertEqual(response.status_code, 302)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, Order.STATUS_NEW)

    def test_pricing_strategy_applies_discount(self):
        self.client.post(reverse("restaurant:generate_bill", args=[self.order.id]))
        bill = Bill.objects.get(order=self.order)
        self.client.post(
            reverse("restaurant:bill_detail", args=[bill.id]),
            {"discount_amount": "0.00", "status": Bill.STATUS_UNPAID, "pricing_mode": "happy_hour"},
        )
        bill.refresh_from_db()
        self.assertEqual(bill.discount_amount, Decimal("10.00"))

    def test_report_csv_export(self):
        bill = Bill.objects.create(order=self.order, status=Bill.STATUS_PAID, discount_amount=Decimal("1.00"))
        BillLineItem.objects.create(bill=bill, description="Burger", quantity=2, unit_price=Decimal("25.00"))
        response = self.client.get(reverse("restaurant:manager_report_csv"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "text/csv")

    def test_bill_receipt_page(self):
        self.client.post(reverse("restaurant:generate_bill", args=[self.order.id]))
        bill = Bill.objects.get(order=self.order)
        response = self.client.get(reverse("restaurant:bill_receipt", args=[bill.id]), {"tip": "5.00"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Payment Check")


class ReservationFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(username="admin2", password="secret123", email="a2@a.com")
        self.client.login(username="admin2", password="secret123")

    def test_reservation_with_table_marks_table_reserved(self):
        table = Table.objects.create(table_number=7, seats=4, status=Table.STATUS_AVAILABLE)
        response = self.client.post(
            reverse("restaurant:reservation_create"),
            {
                "customer_name": "John",
                "customer_phone": "+998900000001",
                "reservation_time": "2026-06-01T19:30",
                "number_of_guests": 2,
                "table": table.id,
                "status": Reservation.STATUS_CONFIRMED,
            },
        )
        self.assertEqual(response.status_code, 302)
        table.refresh_from_db()
        self.assertEqual(table.status, Table.STATUS_RESERVED)

    def test_reservation_rejects_past_time(self):
        table = Table.objects.create(table_number=8, seats=4, status=Table.STATUS_AVAILABLE)
        response = self.client.post(
            reverse("restaurant:reservation_create"),
            {
                "customer_name": "Past User",
                "customer_phone": "+998900000002",
                "reservation_time": "2020-01-01T10:00",
                "number_of_guests": 2,
                "table": table.id,
                "status": Reservation.STATUS_PENDING,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reservation time cannot be in the past.")


class SingletonTests(TestCase):
    def test_order_history_log_is_singleton_record(self):
        one = OrderHistoryLog.get_instance()
        two = OrderHistoryLog.get_instance()
        self.assertEqual(one.id, two.id)
        self.assertEqual(OrderHistoryLog.objects.count(), 1)


class AccessControlTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="waiter1", password="secret123")
        waiter_group, _ = Group.objects.get_or_create(name="Waiter")
        self.user.groups.add(waiter_group)

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse("restaurant:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login/", response.url)

    def test_waiter_cannot_access_manager_report(self):
        self.client.login(username="waiter1", password="secret123")
        response = self.client.get(reverse("restaurant:manager_report"))
        self.assertEqual(response.status_code, 302)

    def test_authenticated_user_can_access_menu_list(self):
        self.client.login(username="waiter1", password="secret123")
        response = self.client.get(reverse("restaurant:menu_list"))
        self.assertEqual(response.status_code, 200)

    def test_register_creates_customer_and_logs_in(self):
        response = self.client.post(
            reverse("restaurant:register"),
            {
                "username": "customer1",
                "email": "customer1@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            },
        )
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username="customer1")
        self.assertTrue(user.groups.filter(name="Customer").exists())

    def test_customer_can_create_reservation(self):
        customer = User.objects.create_user(username="cust2", password="secret123")
        group, _ = Group.objects.get_or_create(name="Customer")
        customer.groups.add(group)
        self.client.login(username="cust2", password="secret123")
        table = Table.objects.create(table_number=12, seats=4, status=Table.STATUS_AVAILABLE)
        response = self.client.post(
            reverse("restaurant:reservation_create"),
            {
                "customer_name": "Cust User",
                "customer_phone": "+998900000111",
                "reservation_time": "2026-06-02T20:00",
                "number_of_guests": 2,
                "table": table.id,
                "status": Reservation.STATUS_PENDING,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertEqual(Reservation.objects.get().customer, customer)

    def test_customer_dashboard_renders_instead_of_redirecting_to_menu(self):
        customer = User.objects.create_user(username="custdash", password="secret123")
        group, _ = Group.objects.get_or_create(name="Customer")
        customer.groups.add(group)
        self.client.login(username="custdash", password="secret123")

        response = self.client.get(reverse("restaurant:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Your BitePlate Space")

    def test_customer_can_create_and_view_only_their_order(self):
        customer = User.objects.create_user(username="custorder", password="secret123")
        other_customer = User.objects.create_user(username="custother", password="secret123")
        group, _ = Group.objects.get_or_create(name="Customer")
        customer.groups.add(group)
        other_customer.groups.add(group)
        table = Table.objects.create(table_number=22, seats=4, status=Table.STATUS_AVAILABLE)
        other_table = Table.objects.create(table_number=23, seats=4, status=Table.STATUS_AVAILABLE)
        menu = MenuItem.objects.create(name="Soup", description="", price=Decimal("12.00"), category="starter")
        other_order = Order.objects.create(table=other_table, customer=other_customer, status=Order.STATUS_NEW)
        OrderItem.objects.create(order=other_order, menu_item=menu, quantity=1)

        self.client.login(username="custorder", password="secret123")
        response = self.client.post(
            reverse("restaurant:order_create"),
            {
                "table": table.id,
                "reservation": "",
                "notes": "No onions",
                "menu_item": menu.id,
                "quantity": 2,
            },
        )

        self.assertEqual(response.status_code, 302)
        created_order = Order.objects.exclude(id=other_order.id).get()
        self.assertEqual(created_order.customer, customer)
        self.assertIsNone(created_order.waiter)

        list_response = self.client.get(reverse("restaurant:order_list"))
        self.assertContains(list_response, f"#{created_order.id}")
        self.assertNotContains(list_response, reverse("restaurant:order_detail", args=[other_order.id]))

        foreign_detail = self.client.get(reverse("restaurant:order_detail", args=[other_order.id]))
        self.assertEqual(foreign_detail.status_code, 404)

    def test_set_language_endpoint_works(self):
        response = self.client.post("/i18n/setlang/", {"language": "ru", "next": "/"})
        self.assertEqual(response.status_code, 302)
