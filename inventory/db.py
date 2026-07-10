import sqlite3


def create_inventory_table(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brand TEXT NOT NULL,
        model_name TEXT NOT NULL,
        size REAL NOT NULL,
        size_unit TEXT NOT NULL CHECK(size_unit IN ('US', 'UK', 'EU')),
        condition_score INTEGER NOT NULL CHECK(condition_score BETWEEN 1 AND 10),
        base_price REAL NOT NULL,
        in_stock BOOLEAN NOT NULL DEFAULT 1,
        description TEXT
    );
    """)
    conn.commit()


def find_matches(conn, brand, model_name, size, size_unit):
    conn.row_factory = sqlite3.Row  # lets us access columns by name

    # Step 1: try exact match
    cursor = conn.execute(
        "SELECT * FROM inventory WHERE brand = ? AND model_name = ? AND size = ? AND size_unit = ? AND in_stock = 1",
        (brand, model_name, size, size_unit)
    )
    exact_matches = cursor.fetchall()

    if exact_matches:
        return exact_matches

    # Step 2: no exact match — find same shoe in other sizes
    cursor = conn.execute(
        "SELECT * FROM inventory WHERE brand = ? AND model_name = ? AND in_stock = 1",
        (brand, model_name)
    )
    alternatives = cursor.fetchall()

    return alternatives


if __name__ == "__main__":
    conn = sqlite3.connect("dna_thrift.db")
    create_inventory_table(conn)
    print("Table created successfully.")
    conn.close()