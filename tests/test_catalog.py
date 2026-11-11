import asyncio

from fastapi.testclient import TestClient

from app.main import create_app
from app.repository import InMemoryBookRepository
from app.service import BookService


def client_with_books():
    repo = InMemoryBookRepository()
    app = create_app(repo=repo)
    client = TestClient(app)
    created = client.post(
        "/api/v1/books",
        json={
            "title": "Rivers of Code",
            "author": "Meera Iyer",
            "isbn": "9781000000001",
            "category": "Technology",
            "price": 749,
            "stock": 2,
            "description": "A field guide.",
        },
    )
    assert created.status_code == 201
    return client, created.json()


def test_health_and_ready():
    client = TestClient(create_app(repo=InMemoryBookRepository()))
    assert client.get("/health").json()["status"] == "up"
    assert client.get("/ready").json()["status"] == "ready"


def test_create_get_and_search():
    client, book = client_with_books()
    fetched = client.get(f"/api/v1/books/{book['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Rivers of Code"

    listed = client.get("/api/v1/books", params={"q": "meera", "category": "technology"})
    body = listed.json()
    assert body["total"] == 1
    assert body["items"][0]["isbn"] == "9781000000001"


def test_duplicate_isbn_is_rejected():
    client, _book = client_with_books()
    again = client.post(
        "/api/v1/books",
        json={
            "title": "Another title",
            "author": "Someone",
            "isbn": "9781000000001",
            "category": "Fiction",
            "price": 100,
            "stock": 1,
        },
    )
    assert again.status_code == 409
    assert again.json()["error"] == "DUPLICATE_ISBN"


def test_update_details_does_not_require_stock():
    client, book = client_with_books()
    updated = client.put(f"/api/v1/books/{book['id']}", json={"price": 700, "category": "Computing"})
    assert updated.status_code == 200
    assert updated.json()["price"] == 700
    assert updated.json()["stock"] == 2


def test_stock_adjustment_and_availability_query():
    client, book = client_with_books()
    refused = client.post(f"/api/v1/books/{book['id']}/stock-adjustments", json={"delta": -5})
    assert refused.status_code == 409

    adjusted = client.post(f"/api/v1/books/{book['id']}/stock-adjustments", json={"delta": 3})
    assert adjusted.json()["stock"] == 5

    available = client.get(f"/api/v1/books/{book['id']}/availability", params={"quantity": 5})
    assert available.json()["available"] is True


def test_reserve_reduces_stock_and_is_idempotent():
    client, book = client_with_books()
    payload = {"orderId": "order-1", "items": [{"bookId": book["id"], "quantity": 2}]}
    first = client.post("/api/v1/reservations", json=payload)
    assert first.status_code == 200
    assert first.json()["items"][0]["unitPrice"] == 749
    assert client.get(f"/api/v1/books/{book['id']}").json()["stock"] == 0

    second = client.post("/api/v1/reservations", json=payload)
    assert second.status_code == 200
    assert client.get(f"/api/v1/books/{book['id']}").json()["stock"] == 0


def test_reserve_insufficient_stock_leaves_stock_unchanged():
    client, book = client_with_books()
    other = client.post(
        "/api/v1/books",
        json={
            "title": "Kitchen Orbits",
            "author": "Farhan Qureshi",
            "isbn": "9781000000004",
            "category": "Cooking",
            "price": 450,
            "stock": 5,
        },
    ).json()
    response = client.post(
        "/api/v1/reservations",
        json={
            "orderId": "order-2",
            "items": [
                {"bookId": other["id"], "quantity": 1},
                {"bookId": book["id"], "quantity": 9},
            ],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"] == "INSUFFICIENT_STOCK"
    assert client.get(f"/api/v1/books/{other['id']}").json()["stock"] == 5
    assert client.get(f"/api/v1/books/{book['id']}").json()["stock"] == 2


def test_reserve_unknown_book():
    client = TestClient(create_app(repo=InMemoryBookRepository()))
    response = client.post(
        "/api/v1/reservations",
        json={"orderId": "order-3", "items": [{"bookId": "missing", "quantity": 1}]},
    )
    assert response.status_code == 404
    assert response.json()["error"] == "BOOK_NOT_FOUND"


def test_release_restores_stock_and_is_idempotent():
    client, book = client_with_books()
    client.post(
        "/api/v1/reservations",
        json={"orderId": "order-4", "items": [{"bookId": book["id"], "quantity": 1}]},
    )
    released = client.post("/api/v1/reservations/order-4/release")
    assert released.status_code == 200
    assert released.json()["status"] == "RELEASED"
    assert client.get(f"/api/v1/books/{book['id']}").json()["stock"] == 2

    again = client.post("/api/v1/reservations/order-4/release")
    assert again.status_code == 200
    assert client.get(f"/api/v1/books/{book['id']}").json()["stock"] == 2


def test_release_unknown_order():
    client = TestClient(create_app(repo=InMemoryBookRepository()))
    response = client.post("/api/v1/reservations/missing-order/release")
    assert response.status_code == 404


def test_cannot_delete_a_reserved_book():
    client, book = client_with_books()
    client.post(
        "/api/v1/reservations",
        json={"orderId": "order-5", "items": [{"bookId": book["id"], "quantity": 1}]},
    )
    blocked = client.delete(f"/api/v1/books/{book['id']}")
    assert blocked.status_code == 409
    client.post("/api/v1/reservations/order-5/release")
    deleted = client.delete(f"/api/v1/books/{book['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/books/{book['id']}").status_code == 404


def test_release_restores_stock_exactly_once():
    client, book = client_with_books()
    client.post(
        "/api/v1/reservations",
        json={"orderId": "order-6", "items": [{"bookId": book["id"], "quantity": 2}]},
    )
    assert client.get(f"/api/v1/books/{book['id']}").json()["stock"] == 0

    first = client.post("/api/v1/reservations/order-6/release")
    second = client.post("/api/v1/reservations/order-6/release")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert client.get(f"/api/v1/books/{book['id']}").json()["stock"] == 2


def test_claim_release_flips_only_once():
    client, book = client_with_books()
    repo = client.app.state.repo
    client.post(
        "/api/v1/reservations",
        json={"orderId": "order-7", "items": [{"bookId": book["id"], "quantity": 1}]},
    )

    async def scenario():
        first = await repo.claim_release("order-7", "2026-01-01T00:00:00Z")
        second = await repo.claim_release("order-7", "2026-01-01T00:00:01Z")
        missing = await repo.claim_release("nope", "2026-01-01T00:00:02Z")
        return first, second, missing

    first, second, missing = asyncio.run(scenario())
    assert first is not None
    assert first["status"] == "RELEASED"
    assert first["items"][0]["bookId"] == book["id"]
    assert second is None
    assert missing is None


def test_concurrent_release_restores_stock_once():
    client, book = client_with_books()
    repo = client.app.state.repo
    client.post(
        "/api/v1/reservations",
        json={"orderId": "order-8", "items": [{"bookId": book["id"], "quantity": 2}]},
    )
    service = BookService(repo)

    async def scenario():
        return await asyncio.gather(service.release("order-8"), service.release("order-8"))

    results = asyncio.run(scenario())
    assert all(result["status"] == "RELEASED" for result in results)
    assert client.get(f"/api/v1/books/{book['id']}").json()["stock"] == 2


def test_validation_error_uses_error_envelope():
    client = TestClient(create_app(repo=InMemoryBookRepository()))
    response = client.post("/api/v1/reservations", json={"orderId": "o-1", "items": [{"bookId": "b", "quantity": 0}]})
    assert response.status_code == 422
    body = response.json()
    assert body["error"] == "VALIDATION_ERROR"
    assert "items.0.quantity" in body["message"]
