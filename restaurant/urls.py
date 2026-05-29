from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

app_name = "restaurant"

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(template_name="restaurant/login.html"), name="login"),
    path("register/", views.register, name="register"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", views.dashboard, name="dashboard"),
    path("menu/", views.menu_list, name="menu_list"),
    path("menu/new/", views.menu_create, name="menu_create"),
    path("menu/<int:menu_id>/edit/", views.menu_edit, name="menu_edit"),
    path("menu/<int:menu_id>/delete/", views.menu_delete, name="menu_delete"),
    path("reservations/", views.reservation_list, name="reservation_list"),
    path("reservations/new/", views.reservation_create, name="reservation_create"),
    path("reservations/<int:reservation_id>/edit/", views.reservation_edit, name="reservation_edit"),
    path("reservations/<int:reservation_id>/delete/", views.reservation_delete, name="reservation_delete"),
    path("tables/", views.table_list, name="table_list"),
    path("tables/new/", views.table_create, name="table_create"),
    path("orders/", views.order_list, name="order_list"),
    path("orders/new/", views.order_create, name="order_create"),
    path("orders/<int:order_id>/", views.order_detail, name="order_detail"),
    path("orders/<int:order_id>/send-to-kitchen/", views.send_to_kitchen, name="send_to_kitchen"),
    path("kitchen-queue/", views.kitchen_queue, name="kitchen_queue"),
    path("orders/<int:order_id>/update-status/", views.update_order_status, name="update_order_status"),
    path("kitchen-queue/undo/", views.undo_last_kitchen_action, name="undo_last_kitchen_action"),
    path("bills/", views.bill_list, name="bill_list"),
    path("orders/<int:order_id>/generate-bill/", views.generate_bill, name="generate_bill"),
    path("bills/<int:bill_id>/", views.bill_detail, name="bill_detail"),
    path("bills/<int:bill_id>/receipt/", views.bill_receipt, name="bill_receipt"),
    path("history/", views.order_history, name="order_history"),
    path("reports/", views.manager_report, name="manager_report"),
    path("reports/export.csv", views.manager_report_csv, name="manager_report_csv"),
    path("staff/", views.manage_staff, name="manage_staff"),
    path("staff/new/", views.staff_create, name="staff_create"),
    path("staff/<str:role>/<int:staff_id>/edit/", views.staff_edit, name="staff_edit"),
    path("staff/<str:role>/<int:staff_id>/delete/", views.staff_delete, name="staff_delete"),
]
