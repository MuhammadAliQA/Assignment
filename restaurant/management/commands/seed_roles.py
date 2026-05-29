from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand

from restaurant.models import Bill, MenuItem, Order, Reservation, Table


class Command(BaseCommand):
    help = "Seed default role groups and permissions for BitePlate"

    def handle(self, *args, **options):
        role_map = {
            "Manager": ["view", "add", "change", "delete"],
            "Waiter": ["view", "add", "change"],
            "Chef": ["view", "change"],
            "Cashier": ["view", "change"],
            "Customer": ["view", "add"],
        }

        models = [Reservation, Table, Order, Bill, MenuItem]
        for role, actions in role_map.items():
            group, _ = Group.objects.get_or_create(name=role)
            group.permissions.clear()
            for model in models:
                ctype = ContentType.objects.get_for_model(model)
                for action in actions:
                    codename = f"{action}_{model._meta.model_name}"
                    permission = Permission.objects.filter(content_type=ctype, codename=codename).first()
                    if permission:
                        group.permissions.add(permission)
            self.stdout.write(self.style.SUCCESS(f"Updated group: {role}"))

        self.stdout.write(self.style.SUCCESS("Role permissions seeded successfully."))
