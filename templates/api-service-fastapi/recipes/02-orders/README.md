# 02 Orders

Orders recipe with optimistic locking on product stock updates.

## Endpoints

- `POST /customers`
- `GET /customers/{customer_id}`
- `POST /products`
- `GET /products/{product_id}`
- `POST /orders`
- `GET /orders/{order_id}`
- `POST /orders/{order_id}/cancel`

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Curl

```bash
curl -X POST "http://127.0.0.1:8000/customers" -H "Content-Type: application/json" -d '{"name":"Alice","email":"alice@example.com"}'
curl -X POST "http://127.0.0.1:8000/products" -H "Content-Type: application/json" -d '{"name":"Mouse","price":2500,"stock":5}'
curl -X POST "http://127.0.0.1:8000/orders" -H "Content-Type: application/json" -d '{"customer_id":1,"items":[{"product_id":1,"quantity":2}]}'
```
