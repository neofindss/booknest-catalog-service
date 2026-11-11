"""Sample catalogue used the first time the catalog database is empty."""


def build_seed_books(now: str) -> list[dict]:
    books = [
        {
            "id": "book-rivers-of-code",
            "title": "Rivers of Code",
            "author": "Meera Iyer",
            "isbn": "9781000000001",
            "category": "Technology",
            "price": 749.0,
            "stock": 8,
            "description": "A field guide to building services that stay calm under load.",
        },
        {
            "id": "book-monsoon-markets",
            "title": "Monsoon Markets",
            "author": "Arjun Patel",
            "isbn": "9781000000002",
            "category": "Business",
            "price": 599.0,
            "stock": 5,
            "description": "How small shops plan stock before the rains arrive.",
        },
        {
            "id": "book-quiet-server",
            "title": "The Quiet Server",
            "author": "Leela Nair",
            "isbn": "9781000000003",
            "category": "Technology",
            "price": 820.0,
            "stock": 10,
            "description": "Stories from the night shift of a growing platform.",
        },
        {
            "id": "book-kitchen-orbits",
            "title": "Kitchen Orbits",
            "author": "Farhan Qureshi",
            "isbn": "9781000000004",
            "category": "Cooking",
            "price": 450.0,
            "stock": 2,
            "description": "Forty weeknight recipes that share one pantry.",
        },
        {
            "id": "book-maps-of-small-towns",
            "title": "Maps of Small Towns",
            "author": "Kavya Reddy",
            "isbn": "9781000000005",
            "category": "Fiction",
            "price": 399.0,
            "stock": 15,
            "description": "Fiction about three siblings and a bus route.",
        },
        {
            "id": "book-field-notes-kubernetes",
            "title": "Field Notes on Kubernetes",
            "author": "Rohan Das",
            "isbn": "9781000000006",
            "category": "Technology",
            "price": 999.0,
            "stock": 4,
            "description": "A practical notebook for packaging and running services.",
        },
    ]
    for book in books:
        book["createdAt"] = now
        book["updatedAt"] = now
    return books
