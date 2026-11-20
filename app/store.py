"""Supermarket mode (filled in during Part B)."""


def store_sales(conn, store_id, date_str=None):
    return {"collected_paise": 0, "bills": 0, "average_paise": 0, "online_paise": 0, "cash_paise": 0,
            "online_count": 0, "cash_count": 0, "top_items": [], "bill_list": []}


def check_order_link(link_id):
    return "UNKNOWN"
