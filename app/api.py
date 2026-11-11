from fastapi import APIRouter, Query, Request, Response
from fastapi.responses import JSONResponse

from app.schemas import BookCreate, BookUpdate, ReservationRequest, StockAdjustment
from app.service import BookService

router = APIRouter()


def _service(request: Request) -> BookService:
    return BookService(request.app.state.repo)


@router.get("/health")
async def health(request: Request):
    return {"status": "up", "service": request.app.state.service_name}


@router.get("/ready")
async def ready(request: Request):
    mongo = getattr(request.app.state, "mongo", None)
    if mongo is not None:
        try:
            await mongo.admin.command("ping")
        except Exception:
            return JSONResponse(
                status_code=503,
                content={"status": "not-ready", "service": request.app.state.service_name},
            )
    return {"status": "ready", "service": request.app.state.service_name}


@router.post("/api/v1/books", status_code=201)
async def create_book(body: BookCreate, request: Request):
    return await _service(request).create_book(body)


@router.get("/api/v1/books")
async def search_books(
    request: Request,
    q: str | None = Query(default=None, description="Match title, author, or ISBN"),
    category: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=10, ge=1, le=50),
):
    return await _service(request).search_books(q, category, page, pageSize)


@router.get("/api/v1/books/{book_id}/availability")
async def availability(book_id: str, request: Request, quantity: int = Query(default=1, ge=1, le=20)):
    return await _service(request).check_availability(book_id, quantity)


@router.get("/api/v1/books/{book_id}")
async def get_book(book_id: str, request: Request):
    return await _service(request).get_book(book_id)


@router.put("/api/v1/books/{book_id}")
async def update_book(book_id: str, body: BookUpdate, request: Request):
    return await _service(request).update_book(book_id, body)


@router.delete("/api/v1/books/{book_id}", status_code=204)
async def remove_book(book_id: str, request: Request):
    await _service(request).remove_book(book_id)
    return Response(status_code=204)


@router.post("/api/v1/books/{book_id}/stock-adjustments")
async def adjust_stock(book_id: str, body: StockAdjustment, request: Request):
    return await _service(request).adjust_stock(book_id, body.delta)


@router.post("/api/v1/reservations")
async def reserve(body: ReservationRequest, request: Request):
    return await _service(request).reserve(body.orderId, body.items)


@router.post("/api/v1/reservations/{order_id}/release")
async def release(order_id: str, request: Request):
    return await _service(request).release(order_id)
