import sqlite3

conn = sqlite3.connect("carbon.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    vm_hours REAL,
    storage_gb REAL,
    network_gb REAL,
    region TEXT,
    energy REAL,
    carbon REAL
)
""")

conn.commit()


def save_report(vm, storage, network, region, energy, carbon):

    cursor.execute(
        "INSERT INTO reports VALUES (NULL,?,?,?,?,?,?)",
        (vm, storage, network, region, energy, carbon)
    )

    conn.commit()


def get_reports():

    cursor.execute("SELECT * FROM reports")
    return cursor.fetchall()