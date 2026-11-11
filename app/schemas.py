from pydantic import BaseModel, ConfigDict, Field


class BookCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    author: str = Field(min_length=1, max_length=200)
    isbn: str = Field(pattern=r"^[0-9-]{10,20}$")
    category: str = Field(min_length=1, max_length=80)
    price: float = Field(gt=0, le=100000)
    stock: int = Field(ge=0, le=100000)
    description: str = Field(default="", max_length=2000)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "title": "Paper Lanterns",
                "author": "Nila Varma",
                "isbn": "9781000000099",
                "category": "Fiction",
                "price": 350,
                "stock": 4,
                "description": "A short novel about a bookshop that stays open late.",
            }
        }
    )


class BookUpdate(BaseModel):
    """Partial update of catalogue details. Stock changes use the stock-adjustment command."""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    author: str | None = Field(default=None, min_length=1, max_length=200)
    category: str | None = Field(default=None, min_length=1, max_length=80)
    price: float | None = Field(default=None, gt=0, le=100000)
    description: str | None = Field(default=None, max_length=2000)


class StockAdjustment(BaseModel):
    delta: int = Field(ge=-100000, le=100000)

    model_config = ConfigDict(json_schema_extra={"example": {"delta": -1}})


class ReservationItem(BaseModel):
    bookId: str = Field(min_length=1)
    quantity: int = Field(gt=0, le=20)


class ReservationRequest(BaseModel):
    orderId: str = Field(min_length=1, max_length=80)
    items: list[ReservationItem] = Field(min_length=1, max_length=10)
