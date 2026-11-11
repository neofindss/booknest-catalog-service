import logging
import uuid

from app.errors import AppError, DuplicateISBN, DuplicateReservation
from app.schemas import BookCreate, BookUpdate, ReservationItem
from app.timeutil import copies, iso_now, money

logger = logging.getLogger("catalog-service")


class BookService:
    """Catalogue commands and queries. Stock changes stay inside this service."""

    def __init__(self, repo):
        self.repo = repo

    async def create_book(self, data: BookCreate) -> dict:
        now = iso_now()
        book = {
            "id": str(uuid.uuid4()),
            "title": data.title.strip(),
            "author": data.author.strip(),
            "isbn": data.isbn.strip(),
            "category": data.category.strip(),
            "price": money(data.price),
            "stock": data.stock,
            "description": data.description.strip(),
            "createdAt": now,
            "updatedAt": now,
        }
        try:
            return await self.repo.insert_book(book)
        except DuplicateISBN as exc:
            raise AppError(
                409,
                "DUPLICATE_ISBN",
                f"A book with ISBN {book['isbn']} already exists",
            ) from exc

    async def update_book(self, book_id: str, data: BookUpdate) -> dict:
        fields = data.model_dump(exclude_unset=True)
        if not fields:
            raise AppError(400, "EMPTY_UPDATE", "Provide at least one field to update")
        for key in ("title", "author", "category", "description"):
            if key in fields and isinstance(fields[key], str):
                fields[key] = fields[key].strip()
        if "price" in fields:
            fields["price"] = money(fields["price"])
        fields["updatedAt"] = iso_now()
        updated = await self.repo.update_book(book_id, fields)
        if updated is None:
            raise AppError(404, "BOOK_NOT_FOUND", "Book was not found")
        return updated

    async def remove_book(self, book_id: str) -> None:
        book = await self.repo.get_book(book_id)
        if book is None:
            raise AppError(404, "BOOK_NOT_FOUND", "Book was not found")
        active = await self.repo.count_active_reservations(book_id)
        if active:
            raise AppError(
                409,
                "BOOK_RESERVED",
                "This book has an active order reservation and cannot be removed",
            )
        await self.repo.delete_book(book_id)

    async def adjust_stock(self, book_id: str, delta: int) -> dict:
        if delta == 0:
            raise AppError(400, "ZERO_DELTA", "Stock delta cannot be zero")
        existing = await self.repo.get_book(book_id)
        if existing is None:
            raise AppError(404, "BOOK_NOT_FOUND", "Book was not found")
        updated = await self.repo.adjust_stock(book_id, delta, iso_now())
        if updated is None:
            raise AppError(
                409,
                "INSUFFICIENT_STOCK",
                f"Only {existing['stock']} {copies(existing['stock'])} of '{existing['title']}' are available",
            )
        return updated

    async def get_book(self, book_id: str) -> dict:
        book = await self.repo.get_book(book_id)
        if book is None:
            raise AppError(404, "BOOK_NOT_FOUND", "Book was not found")
        return book

    async def search_books(self, text: str | None, category: str | None, page: int, page_size: int) -> dict:
        items, total = await self.repo.list_books(text, category, (page - 1) * page_size, page_size)
        return {"items": items, "page": page, "pageSize": page_size, "total": total}

    async def check_availability(self, book_id: str, quantity: int) -> dict:
        book = await self.repo.get_book(book_id)
        if book is None:
            raise AppError(404, "BOOK_NOT_FOUND", "Book was not found")
        return {
            "bookId": book["id"],
            "title": book["title"],
            "requestedQuantity": quantity,
            "stock": book["stock"],
            "available": book["stock"] >= quantity,
        }

    async def reserve(self, order_id: str, items: list[ReservationItem]) -> dict:
        book_ids = [item.bookId for item in items]
        if len(set(book_ids)) != len(book_ids):
            raise AppError(400, "DUPLICATE_BOOK", "Each book can appear only once in a reservation")

        existing = await self.repo.get_reservation(order_id)
        if existing and existing["status"] == "RESERVED":
            logger.info("Reservation for order %s already exists", order_id)
            return {"orderId": order_id, "status": "RESERVED", "items": existing["items"]}
        if existing and existing["status"] == "RELEASED":
            raise AppError(409, "RESERVATION_CLOSED", "Stock for this order was already released")

        reserved_items: list[dict] = []
        try:
            for item in items:
                book = await self.repo.decrement_stock(item.bookId, item.quantity, iso_now())
                if book is None:
                    current = await self.repo.get_book(item.bookId)
                    if current is None:
                        raise AppError(404, "BOOK_NOT_FOUND", f"Book {item.bookId} was not found")
                    raise AppError(
                        409,
                        "INSUFFICIENT_STOCK",
                        f"Only {current['stock']} {copies(current['stock'])} of '{current['title']}' are available",
                    )
                reserved_items.append(
                    {
                        "bookId": book["id"],
                        "title": book["title"],
                        "author": book["author"],
                        "isbn": book["isbn"],
                        "unitPrice": book["price"],
                        "quantity": item.quantity,
                    }
                )
        except AppError:
            await self._restore(reserved_items)
            raise

        now = iso_now()
        reservation = {
            "orderId": order_id,
            "status": "RESERVED",
            "items": reserved_items,
            "createdAt": now,
            "updatedAt": now,
        }
        try:
            await self.repo.save_reservation(reservation)
        except DuplicateReservation:
            await self._restore(reserved_items)
            winner = await self.repo.get_reservation(order_id)
            if winner and winner["status"] == "RESERVED":
                return {"orderId": order_id, "status": "RESERVED", "items": winner["items"]}
            raise AppError(409, "RESERVATION_CONFLICT", "This order reservation could not be stored")

        logger.info("Reserved stock for order %s (%s line(s))", order_id, len(reserved_items))
        return {"orderId": order_id, "status": "RESERVED", "items": reserved_items}

    async def release(self, order_id: str) -> dict:
        now = iso_now()
        # Claim first: only the call that flips RESERVED -> RELEASED restores stock.
        claimed = await self.repo.claim_release(order_id, now)
        if claimed is None:
            existing = await self.repo.get_reservation(order_id)
            if existing is None:
                raise AppError(404, "RESERVATION_NOT_FOUND", "No stock reservation exists for this order")
            logger.info("Reservation for order %s is already released", order_id)
            return {"orderId": order_id, "status": "RELEASED", "items": existing["items"]}

        for item in claimed["items"]:
            restored = await self.repo.increment_stock(item["bookId"], item["quantity"], now)
            if restored is None:
                # remove_book blocks deleting reserved books, so this is not expected in normal use.
                raise AppError(404, "BOOK_NOT_FOUND", f"Book {item['bookId']} was not found")
        logger.info("Released stock for order %s", order_id)
        return {"orderId": order_id, "status": "RELEASED", "items": claimed["items"]}

    async def _restore(self, reserved_items: list[dict]) -> None:
        now = iso_now()
        for item in reserved_items:
            await self.repo.increment_stock(item["bookId"], item["quantity"], now)
