import sqlite3

conn = sqlite3.connect(":memory:")
conn.execute("PRAGMA foreign_keys=ON")

conn.execute("CREATE TABLE books (id TEXT PRIMARY KEY)")
conn.execute("""CREATE TABLE chapters (
    id TEXT PRIMARY KEY,
    book_id TEXT,
    FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
)""")

# Insert book
conn.execute("INSERT INTO books VALUES ('book1')")

# Insert chapter
conn.execute("INSERT INTO chapters VALUES ('chap1', 'book1')")
conn.commit()

count1 = conn.execute("SELECT count(*) FROM chapters").fetchone()[0]
print(f"Chapters after insert: {count1}")

# Now UPDATE the book using INSERT OR REPLACE
conn.execute("INSERT OR REPLACE INTO books VALUES ('book1')")
conn.commit()

count2 = conn.execute("SELECT count(*) FROM chapters").fetchone()[0]
print(f"Chapters after INSERT OR REPLACE into books: {count2}")
