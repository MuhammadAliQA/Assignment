from dataclasses import dataclass

from .models import Order


class Command:
    def execute(self):
        raise NotImplementedError

    def undo(self):
        raise NotImplementedError


@dataclass
class PrepareOrderCommand(Command):
    order: Order
    new_status: str
    previous_status: str = ""

    def execute(self):
        self.previous_status = self.order.status
        self.order.status = self.new_status
        self.order.save(update_fields=["status"])
        return self.order

    def undo(self):
        self.order.status = self.previous_status
        self.order.save(update_fields=["status"])
        return self.order


@dataclass
class CancelOrderCommand(Command):
    order: Order
    previous_status: str = ""

    def execute(self):
        self.previous_status = self.order.status
        self.order.status = Order.STATUS_CANCELLED
        self.order.save(update_fields=["status"])
        return self.order

    def undo(self):
        self.order.status = self.previous_status
        self.order.save(update_fields=["status"])
        return self.order


class KitchenQueueInvoker:
    SESSION_KEY = "kitchen_last_command"

    @classmethod
    def run(cls, request, command):
        result = command.execute()
        request.session[cls.SESSION_KEY] = {
            "order_id": result.id,
            "previous_status": command.previous_status,
        }
        request.session.modified = True
        return result

    @classmethod
    def undo_last(cls, request):
        payload = request.session.get(cls.SESSION_KEY)
        if not payload:
            return None
        order = Order.objects.filter(id=payload.get("order_id")).first()
        if not order:
            return None
        order.status = payload.get("previous_status", order.status)
        order.save(update_fields=["status"])
        request.session.pop(cls.SESSION_KEY, None)
        request.session.modified = True
        return order
