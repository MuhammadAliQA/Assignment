from .models import Order, Waiter


class OrderObserver:
    def update(self, order, message):
        raise NotImplementedError


class WaiterNotificationObserver(OrderObserver):
    def update(self, order, message):
        waiter = order.waiter
        if isinstance(waiter, Waiter):
            print(f"[Observer] Notify waiter {waiter.name}: {message}")


class KitchenNotificationObserver(OrderObserver):
    def update(self, order, message):
        print(f"[Observer] Kitchen update for Order #{order.id}: {message}")


class OrderNotifier:
    def __init__(self):
        self._observers = []

    def attach(self, observer):
        self._observers.append(observer)

    def notify(self, order, message):
        for observer in self._observers:
            observer.update(order, message)


def build_default_notifier():
    notifier = OrderNotifier()
    notifier.attach(WaiterNotificationObserver())
    notifier.attach(KitchenNotificationObserver())
    return notifier
