from decimal import Decimal


class PricingStrategy:
    def calculate_total(self, subtotal):
        raise NotImplementedError


class StandardPricing(PricingStrategy):
    def calculate_total(self, subtotal):
        return subtotal, Decimal("0.00"), "Standard Pricing"


class HappyHourPricing(PricingStrategy):
    def calculate_total(self, subtotal):
        discount = (subtotal * Decimal("0.20")).quantize(Decimal("0.01"))
        return subtotal - discount, discount, "Happy Hour -20%"


class LoyaltyCardPricing(PricingStrategy):
    def calculate_total(self, subtotal):
        discount = (subtotal * Decimal("0.10")).quantize(Decimal("0.01"))
        return subtotal - discount, discount, "Loyalty Card -10% (+ free drink)"


class PricingEngine:
    STRATEGIES = {
        "standard": StandardPricing,
        "happy_hour": HappyHourPricing,
        "loyalty": LoyaltyCardPricing,
    }

    @classmethod
    def get_strategy(cls, key):
        strategy_cls = cls.STRATEGIES.get(key, StandardPricing)
        return strategy_cls()
