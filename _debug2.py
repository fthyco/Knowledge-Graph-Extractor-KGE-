from warehouse import Warehouse
from warehouse.models import Chapter, Book

w = Warehouse()

print("Clearing DB...")
w.storage.clear_all_books()

b = Book.create("Test", "test.pdf", "test.pdf")
print("Saving book...")
w.storage.save_book(b, defer_index=False)

ch = Chapter(id="c1", book_id=b.id, number=1, title="Test Chapter")
print("Saving chapter...")
# Try saving
try:
    w.storage.save_chapter(ch, auto_commit=True)
    print("Chapter saved!")
except Exception as e:
    print(f"Error: {e}")

print("Chapters in DB:", w.storage._conn.execute("SELECT count(*) FROM chapters").fetchone()[0])
