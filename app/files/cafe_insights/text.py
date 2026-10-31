"""Plain-language formatting shared by the analyses and the app."""


def money(x: float, currency: str = "₹") -> str:
    """₹1,54,00,000 -> '₹1.54 crore'; €2,345 -> '€2.3K'; small amounts keep their decimals."""
    if x is None or x != x:  # None or NaN
        return "—"
    sign = "-" if x < 0 else ""
    x = abs(x)
    if currency == "₹":
        if x >= 1e7:
            return f"{sign}₹{x / 1e7:.2f} crore"
        if x >= 1e5:
            return f"{sign}₹{x / 1e5:.1f} lakh"
    else:
        if x >= 1e6:
            return f"{sign}{currency}{x / 1e6:.2f}M"
        if x >= 1e4:
            return f"{sign}{currency}{x / 1e3:.1f}K"
    if x >= 20 or x == round(x):
        return f"{sign}{currency}{x:,.0f}"
    return f"{sign}{currency}{x:,.2f}"


def nice_amount(x: float) -> float:
    """Round a suggested price change to something a menu could actually show."""
    return round(x) if x >= 20 else round(x, 2)


def times(x: float) -> str:
    """6.2 -> '6 times', 1.36 -> '1.4 times'."""
    return f"{x:.0f} times" if x >= 10 else f"{x:.1f} times"
