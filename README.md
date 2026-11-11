# BookNest catalog service

This repository is the BookNest catalogue bounded context. It owns book details and available stock. It has its own MongoDB database and does not read the order database.

The order service collaborates with this service over HTTP when a customer places or cancels an order.

## Run the tests

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

## Run with Docker Compose

From the assignment folder that contains `docker-compose.yml`:

```powershell
docker compose up --build
```

Catalog API: `http://localhost:8001`  
Interactive API docs: `http://localhost:8001/docs`

## Run on Kubernetes

Deploy the whole BookNest system from the assignment root. If the images are missing, run `docker compose build`, then `.\scripts\deploy-minikube.ps1`. This service's manifests are applied as part of that. The deployment uses image `booknest-catalog:1.0.0` with `imagePullPolicy: Never`, so a same-tag update needs the script's rollout restart (the script already does it). The full start-to-stop list is in `docs/STEP_BY_STEP.md`.

The optional autoscaler is in `k8s/optional/catalog-hpa.yaml`. Apply it after the metrics-server addon is enabled.

## API

| Method | Path | Kind |
| --- | --- | --- |
| POST | `/api/v1/books` | Command: AddBook |
| PUT | `/api/v1/books/{bookId}` | Command: UpdateBookDetails |
| DELETE | `/api/v1/books/{bookId}` | Command: RemoveBook |
| POST | `/api/v1/books/{bookId}/stock-adjustments` | Command: AdjustStock |
| POST | `/api/v1/reservations` | Command: ReserveStock |
| POST | `/api/v1/reservations/{orderId}/release` | Command: ReleaseStock |
| GET | `/api/v1/books` | Query: SearchBooks |
| GET | `/api/v1/books/{bookId}` | Query: GetBook |
| GET | `/api/v1/books/{bookId}/availability` | Query: CheckAvailability |
| GET | `/health` | Liveness |
| GET | `/ready` | Readiness, checks MongoDB |

Seeded book ids include `book-kitchen-orbits` and `book-rivers-of-code`.
