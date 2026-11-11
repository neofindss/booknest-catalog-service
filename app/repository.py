import copy
import re
from typing import Any

from app.errors import DuplicateISBN, DuplicateReservation


def _copy(document: dict | None) -> dict | None:
    if document is None:
        return None
    cleaned = dict(document)
    cleaned.pop("_id", None)
    return cleaned


class InMemoryBookRepository:
    """Test and local stand-in that follows the same rules as the MongoDB repository."""

    def __init__(self):
        self.books: dict[str, dict] = {}
        self.reservations: dict[str, dict] = {}

    async def ensure_indexes(self) -> None:
        return None

    async def count_books(self) -> int:
        return len(self.books)

    async def insert_book(self, book: dict) -> dict:
        if any(existing["isbn"] == book["isbn"] for existing in self.books.values()):
            raise DuplicateISBN()
        self.books[book["id"]] = copy.deepcopy(book)
        return copy.deepcopy(book)

    async def insert_many_books(self, books: list[dict]) -> None:
        for book in books:
            await self.insert_book(book)

    async def get_book(self, book_id: str) -> dict | None:
        return _copy(self.books.get(book_id))

    async def update_book(self, book_id: str, fields: dict) -> dict | None:
        book = self.books.get(book_id)
        if book is None:
            return None
        book.update(fields)
        return _copy(book)

    async def delete_book(self, book_id: str) -> bool:
        return self.books.pop(book_id, None) is not None

    async def list_books(
        self, text: str | None, category: str | None, skip: int, limit: int
    ) -> tuple[list[dict], int]:
        items = list(self.books.values())
        if category:
            items = [book for book in items if book["category"].lower() == category.lower()]
        if text:
            needle = text.lower()
            items = [
                book
                for book in items
                if needle in book["title"].lower()
                or needle in book["author"].lower()
                or needle in book["isbn"].lower()
            ]
        items.sort(key=lambda book: book["title"].lower())
        total = len(items)
        page = [_copy(book) for book in items[skip : skip + limit]]
        return page, total

    async def decrement_stock(self, book_id: str, quantity: int, updated_at: str) -> dict | None:
        book = self.books.get(book_id)
        if book is None or book["stock"] < quantity:
            return None
        book["stock"] -= quantity
        book["updatedAt"] = updated_at
        return _copy(book)

    async def increment_stock(self, book_id: str, quantity: int, updated_at: str) -> dict | None:
        book = self.books.get(book_id)
        if book is None:
            return None
        book["stock"] += quantity
        book["updatedAt"] = updated_at
        return _copy(book)

    async def adjust_stock(self, book_id: str, delta: int, updated_at: str) -> dict | None:
        book = self.books.get(book_id)
        if book is None:
            return None
        if book["stock"] + delta < 0:
            return None
        book["stock"] += delta
        book["updatedAt"] = updated_at
        return _copy(book)

    async def get_reservation(self, order_id: str) -> dict | None:
        return _copy(self.reservations.get(order_id))

    async def save_reservation(self, reservation: dict) -> None:
        if reservation["orderId"] in self.reservations:
            raise DuplicateReservation()
        self.reservations[reservation["orderId"]] = copy.deepcopy(reservation)

    async def mark_released(self, order_id: str, updated_at: str) -> dict | None:
        reservation = self.reservations.get(order_id)
        if reservation is None:
            return None
        reservation["status"] = "RELEASED"
        reservation["updatedAt"] = updated_at
        return _copy(reservation)

    async def claim_release(self, order_id: str, updated_at: str) -> dict | None:
        """Atomically flip RESERVED -> RELEASED; return the reservation only if this call flipped it."""
        reservation = self.reservations.get(order_id)
        if reservation is None or reservation["status"] != "RESERVED":
            return None
        reservation["status"] = "RELEASED"
        reservation["updatedAt"] = updated_at
        return _copy(reservation)

    async def count_active_reservations(self, book_id: str) -> int:
        total = 0
        for reservation in self.reservations.values():
            if reservation["status"] != "RESERVED":
                continue
            if any(item["bookId"] == book_id for item in reservation["items"]):
                total += 1
        return total


class MongoBookRepository:
    """MongoDB persistence owned exclusively by the catalog service."""

    def __init__(self, database: Any):
        self.books = database["books"]
        self.reservations = database["reservations"]

    async def ensure_indexes(self) -> None:
        await self.books.create_index("id", unique=True, name="book_id_unique")
        await self.books.create_index("isbn", unique=True, name="isbn_unique")
        await self.books.create_index("category", name="category_idx")
        await self.reservations.create_index("orderId", unique=True, name="order_id_unique")

    async def count_books(self) -> int:
        return await self.books.count_documents({})

    async def insert_book(self, book: dict) -> dict:
        from pymongo.errors import DuplicateKeyError

        try:
            await self.books.insert_one(dict(book))
        except DuplicateKeyError as exc:
            raise DuplicateISBN() from exc
        return dict(book)

    async def insert_many_books(self, books: list[dict]) -> None:
        if books:
            await self.books.insert_many([dict(book) for book in books])

    async def get_book(self, book_id: str) -> dict | None:
        return _copy(await self.books.find_one({"id": book_id}))

    async def update_book(self, book_id: str, fields: dict) -> dict | None:
        from pymongo import ReturnDocument

        updated = await self.books.find_one_and_update(
            {"id": book_id},
            {"$set": fields},
            return_document=ReturnDocument.AFTER,
        )
        return _copy(updated)

    async def delete_book(self, book_id: str) -> bool:
        result = await self.books.delete_one({"id": book_id})
        return result.deleted_count == 1

    async def list_books(
        self, text: str | None, category: str | None, skip: int, limit: int
    ) -> tuple[list[dict], int]:
        query: dict = {}
        if category:
            query["category"] = {"$regex": f"^{re.escape(category)}$", "$options": "i"}
        if text:
            pattern = re.escape(text)
            query["$or"] = [
                {"title": {"$regex": pattern, "$options": "i"}},
                {"author": {"$regex": pattern, "$options": "i"}},
                {"isbn": {"$regex": pattern, "$options": "i"}},
            ]
        total = await self.books.count_documents(query)
        cursor = self.books.find(query).sort("title", 1).skip(skip).limit(limit)
        items = [_copy(document) async for document in cursor]
        return items, total

    async def decrement_stock(self, book_id: str, quantity: int, updated_at: str) -> dict | None:
        from pymongo import ReturnDocument

        updated = await self.books.find_one_and_update(
            {"id": book_id, "stock": {"$gte": quantity}},
            {"$inc": {"stock": -quantity}, "$set": {"updatedAt": updated_at}},
            return_document=ReturnDocument.AFTER,
        )
        return _copy(updated)

    async def increment_stock(self, book_id: str, quantity: int, updated_at: str) -> dict | None:
        from pymongo import ReturnDocument

        updated = await self.books.find_one_and_update(
            {"id": book_id},
            {"$inc": {"stock": quantity}, "$set": {"updatedAt": updated_at}},
            return_document=ReturnDocument.AFTER,
        )
        return _copy(updated)

    async def adjust_stock(self, book_id: str, delta: int, updated_at: str) -> dict | None:
        from pymongo import ReturnDocument

        query: dict = {"id": book_id}
        if delta < 0:
            query["stock"] = {"$gte": -delta}
        updated = await self.books.find_one_and_update(
            query,
            {"$inc": {"stock": delta}, "$set": {"updatedAt": updated_at}},
            return_document=ReturnDocument.AFTER,
        )
        return _copy(updated)

    async def get_reservation(self, order_id: str) -> dict | None:
        return _copy(await self.reservations.find_one({"orderId": order_id}))

    async def save_reservation(self, reservation: dict) -> None:
        from pymongo.errors import DuplicateKeyError

        try:
            await self.reservations.insert_one(dict(reservation))
        except DuplicateKeyError as exc:
            raise DuplicateReservation() from exc

    async def mark_released(self, order_id: str, updated_at: str) -> dict | None:
        from pymongo import ReturnDocument

        updated = await self.reservations.find_one_and_update(
            {"orderId": order_id},
            {"$set": {"status": "RELEASED", "updatedAt": updated_at}},
            return_document=ReturnDocument.AFTER,
        )
        return _copy(updated)

    async def claim_release(self, order_id: str, updated_at: str) -> dict | None:
        """Atomically flip RESERVED -> RELEASED; return the reservation only if this call flipped it."""
        from pymongo import ReturnDocument

        claimed = await self.reservations.find_one_and_update(
            {"orderId": order_id, "status": "RESERVED"},
            {"$set": {"status": "RELEASED", "updatedAt": updated_at}},
            return_document=ReturnDocument.AFTER,
        )
        return _copy(claimed)

    async def count_active_reservations(self, book_id: str) -> int:
        return await self.reservations.count_documents(
            {"status": "RESERVED", "items.bookId": book_id}
        )
