class LegacyKitchenDisplaySystem:
    def push_text(self, raw_message):
        return f"Legacy display accepted: {raw_message}"


class KitchenDisplayAdapter:
    """
    Adapter that converts Order data into the legacy display format.
    """

    def __init__(self, legacy_display):
        self.legacy_display = legacy_display

    def send_order(self, order):
        item_parts = [f"{i.menu_item.name}x{i.quantity}" for i in order.items.all()]
        payload = f"ORD-{order.id}|TBL-{order.table.table_number}|" + ",".join(item_parts)
        return self.legacy_display.push_text(payload)
