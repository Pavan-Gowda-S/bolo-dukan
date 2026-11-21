"""SQLite storage. One small file in data/, no server needed."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS restaurants (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    language TEXT NOT NULL DEFAULT 'kn-IN',
    wifi_name TEXT NOT NULL DEFAULT '',
    wifi_password TEXT NOT NULL DEFAULT '',
    table_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS owners (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
    name TEXT NOT NULL,
    name_local TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'Menu',
    price_paise INTEGER NOT NULL,
    available INTEGER NOT NULL DEFAULT 1,
    photo_url TEXT NOT NULL DEFAULT '',
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
    number INTEGER NOT NULL,
    token TEXT NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS table_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER NOT NULL REFERENCES tables(id),
    join_code TEXT NOT NULL,
    status TEXT NOT NULL,
    guest_phone TEXT NOT NULL DEFAULT '',
    started_at TEXT NOT NULL,
    closed_at TEXT,
    settled_paise INTEGER NOT NULL DEFAULT 0,
    settled_at TEXT,
    pay_method TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS session_guests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES table_sessions(id),
    token TEXT NOT NULL UNIQUE,
    device_id TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES table_sessions(id),
    status TEXT NOT NULL,
    reject_reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    menu_item_id INTEGER NOT NULL REFERENCES menu_items(id),
    name TEXT NOT NULL,
    qty INTEGER NOT NULL,
    unit_price_paise INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES table_sessions(id),
    link_id TEXT NOT NULL UNIQUE,
    link_url TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL DEFAULT '',
    paid_at TEXT
);
CREATE TABLE IF NOT EXISTS waiter_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES table_sessions(id),
    reason TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    done INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS game_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
    game TEXT NOT NULL,
    player TEXT NOT NULL,
    table_number INTEGER NOT NULL,
    score INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scores ON game_scores(restaurant_id, game, score);
CREATE TABLE IF NOT EXISTS announcements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
    table_number INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    text_kn TEXT NOT NULL,
    text_en TEXT NOT NULL,
    claimed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_announce ON announcements(restaurant_id, id);
CREATE TABLE IF NOT EXISTS quiz_rounds (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
    starts_at REAL NOT NULL,
    questions TEXT NOT NULL,
    finalized INTEGER NOT NULL DEFAULT 0,
    winner_session_id INTEGER,
    winner_table INTEGER,
    winner_score INTEGER NOT NULL DEFAULT 0,
    reward_status TEXT NOT NULL DEFAULT 'none',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quiz_rest ON quiz_rounds(restaurant_id, id);
CREATE TABLE IF NOT EXISTS quiz_players (
    round_id INTEGER NOT NULL REFERENCES quiz_rounds(id),
    session_id INTEGER NOT NULL REFERENCES table_sessions(id),
    table_number INTEGER NOT NULL,
    joined_at REAL NOT NULL,
    PRIMARY KEY (round_id, session_id)
);
CREATE TABLE IF NOT EXISTS quiz_answers (
    round_id INTEGER NOT NULL REFERENCES quiz_rounds(id),
    session_id INTEGER NOT NULL REFERENCES table_sessions(id),
    q_index INTEGER NOT NULL,
    choice INTEGER NOT NULL,
    correct INTEGER NOT NULL,
    points INTEGER NOT NULL,
    answered_at REAL NOT NULL,
    PRIMARY KEY (round_id, session_id, q_index)
);
CREATE TABLE IF NOT EXISTS bill_shares (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES table_sessions(id),
    label TEXT NOT NULL,
    guest_id INTEGER,
    amount_paise INTEGER NOT NULL,
    phone TEXT NOT NULL DEFAULT '',
    link_id TEXT,
    link_url TEXT,
    link_count INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'PENDING',
    mode TEXT NOT NULL DEFAULT 'equal',
    cancelled INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    paid_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_shares_session ON bill_shares(session_id);
CREATE INDEX IF NOT EXISTS idx_shares_link ON bill_shares(link_id);
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL REFERENCES restaurants(id),
    name TEXT NOT NULL,
    brand TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'Other',
    pack_size REAL NOT NULL,
    pack_unit TEXT NOT NULL,
    price_paise INTEGER NOT NULL,
    stock INTEGER NOT NULL DEFAULT 100,
    available INTEGER NOT NULL DEFAULT 1,
    ingredient_id TEXT,
    image_url TEXT NOT NULL DEFAULT '',
    topup INTEGER NOT NULL DEFAULT 0,
    diet TEXT NOT NULL DEFAULT 'veg',
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_products_store ON products(store_id, deleted);
CREATE TABLE IF NOT EXISTS store_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id INTEGER NOT NULL REFERENCES restaurants(id),
    status TEXT NOT NULL,
    customer_name TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    total_paise INTEGER NOT NULL,
    source TEXT NOT NULL DEFAULT 'direct',
    plan TEXT NOT NULL DEFAULT '',
    token TEXT NOT NULL,
    link_id TEXT,
    link_url TEXT,
    link_count INTEGER NOT NULL DEFAULT 0,
    expires_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    paid_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_store_orders ON store_orders(store_id, status);
CREATE TABLE IF NOT EXISTS store_order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER NOT NULL REFERENCES store_orders(id),
    product_id INTEGER NOT NULL REFERENCES products(id),
    name TEXT NOT NULL,
    packs INTEGER NOT NULL,
    pack_size REAL NOT NULL,
    pack_unit TEXT NOT NULL,
    unit_price_paise INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS translations (
    lang TEXT NOT NULL,
    src TEXT NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (lang, src)
);
CREATE TABLE IF NOT EXISTS join_attempts (
    device_key TEXT PRIMARY KEY,
    fails INTEGER NOT NULL DEFAULT 0,
    blocked_until REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_sessions_table ON table_sessions(table_id, status);
CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session_id);
CREATE INDEX IF NOT EXISTS idx_items_order ON order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_menu_rest ON menu_items(restaurant_id);
"""

# Session statuses
WAITING_APPROVAL = "WAITING_APPROVAL"
OPEN = "OPEN"
BILL_REQUESTED = "BILL_REQUESTED"
PAID = "PAID"
CLOSED = "CLOSED"
REJECTED = "REJECTED"
PAID_CASH = "PAID_CASH"
ACTIVE_SESSION_STATUSES = (WAITING_APPROVAL, OPEN, BILL_REQUESTED, PAID)

# Order statuses
PENDING = "PENDING"
ACCEPTED = "ACCEPTED"
PREPARING = "PREPARING"
SERVED = "SERVED"
ORDER_REJECTED = "REJECTED"
BILLABLE_ORDER_STATUSES = (ACCEPTED, PREPARING, SERVED)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def db():
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    conn = connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        # Small migrations for databases made by older versions.
        owner_cols = {r[1] for r in conn.execute("PRAGMA table_info(owners)")}
        if "google_sub" not in owner_cols:
            conn.execute("ALTER TABLE owners ADD COLUMN google_sub TEXT NOT NULL DEFAULT ''")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_owners_google ON owners(google_sub)")
        order_cols = {r[1] for r in conn.execute("PRAGMA table_info(orders)")}
        if "guest_id" not in order_cols:  # which phone placed the order (for "pay for my items")
            conn.execute("ALTER TABLE orders ADD COLUMN guest_id INTEGER")
        menu_cols = {r[1] for r in conn.execute("PRAGMA table_info(menu_items)")}
        for col, decl in (("description", "TEXT NOT NULL DEFAULT ''"), ("is_veg", "INTEGER"), ("spice", "INTEGER"),
                          ("allergens", "TEXT NOT NULL DEFAULT ''"), ("kcal", "INTEGER"), ("protein_g", "REAL"),
                          ("carbs_g", "REAL"), ("fat_g", "REAL"), ("fibre_g", "REAL")):
            if col not in menu_cols:  # 4: optional dish details, entered by the owner (NULL = unknown)
                conn.execute(f"ALTER TABLE menu_items ADD COLUMN {col} {decl}")
        table_cols = {r[1] for r in conn.execute("PRAGMA table_info(tables)")}
        if "merged_into" not in table_cols:  # merged tables: this table's QR opens the host table's order
            conn.execute("ALTER TABLE tables ADD COLUMN merged_into INTEGER")
        if "seats" not in table_cols:  # 6: chairs per table
            conn.execute("ALTER TABLE tables ADD COLUMN seats INTEGER NOT NULL DEFAULT 4")
        rest_cols = {r[1] for r in conn.execute("PRAGMA table_info(restaurants)")}
        if "kitchen_token" not in rest_cols:  # 3: secret link for the kitchen TV
            conn.execute("ALTER TABLE restaurants ADD COLUMN kitchen_token TEXT NOT NULL DEFAULT ''")
        ann_cols = {r[1] for r in conn.execute("PRAGMA table_info(announcements)")}
        if "kitchen_claimed" not in ann_cols:  # 3: the kitchen TV claims its own copy
            conn.execute("ALTER TABLE announcements ADD COLUMN kitchen_claimed INTEGER NOT NULL DEFAULT 0")
        if "accepted_by" not in order_cols:  # 2: "owner" or "waiter:Ravi"
            conn.execute("ALTER TABLE orders ADD COLUMN accepted_by TEXT NOT NULL DEFAULT ''")
        sess_cols = {r[1] for r in conn.execute("PRAGMA table_info(table_sessions)")}
        if "approved_by" not in sess_cols:
            conn.execute("ALTER TABLE table_sessions ADD COLUMN approved_by TEXT NOT NULL DEFAULT ''")
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                restaurant_id INTEGER NOT NULL REFERENCES restaurants(id),
                name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'waiter', username TEXT NOT NULL,
                pin_hash TEXT NOT NULL, active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL,
                UNIQUE (restaurant_id, username));
            CREATE TABLE IF NOT EXISTS staff_tables (
                staff_id INTEGER NOT NULL REFERENCES staff(id), table_id INTEGER NOT NULL REFERENCES tables(id),
                PRIMARY KEY (staff_id, table_id));
        """)
        if "accepted_at" not in order_cols:
            conn.execute("ALTER TABLE orders ADD COLUMN accepted_at TEXT")
        if "business_type" not in rest_cols:
            conn.execute("ALTER TABLE restaurants ADD COLUMN business_type TEXT NOT NULL DEFAULT 'restaurant'")
        conn.commit()
    finally:
        conn.close()


def row(r):
    return dict(r) if r is not None else None


def rows(rs):
    return [dict(r) for r in rs]
