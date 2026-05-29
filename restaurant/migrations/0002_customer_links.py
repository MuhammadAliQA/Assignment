from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("restaurant", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="customer",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="orders", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name="reservation",
            name="customer",
            field=models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="reservations", to=settings.AUTH_USER_MODEL),
        ),
    ]
