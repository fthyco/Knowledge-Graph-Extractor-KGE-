"""Minimal test: does INSERT OR REPLACE silently fail with FK?"""
import sqlite3

conn = sqlite3.connect(":memory:")
conn.execute("PRAGMA foreign_keys=ON")

conn.execute("CREATE TABLE parent (id TEXT PRIMARY KEY)")
conn.execute("""CREATE TABLE child (
    id TEXT PRIMARY KEY, 
    parent_id TEXT, 
    FOREIGN KEY (parent_id) REFERENCES parent(id)
)""")

# Insert parent but don't commit
conn.execute("INSERT INTO parent VALUES ('p1')")
# Don't commit!

# Try inserting child
try:
    conn.execute("INSERT OR REPLACE INTO child VALUES ('c1', 'p1')")
    print("Child insert OK (same connection, same transaction)")
except Exception as e:
    print(f"Child insert FAILED: {e}")

# Check
count = conn.execute("SELECT COUNT(*) FROM child").fetchone()[0]
print(f"Children: {count}")

# Now commit
conn.commit()
count2 = conn.execute("SELECT COUNT(*) FROM child").fetchone()[0]
print(f"Children after commit: {count2}")
