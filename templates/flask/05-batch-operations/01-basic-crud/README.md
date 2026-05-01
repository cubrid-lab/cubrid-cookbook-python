# 01 Basic CRUD

Standalone Flask recipe for JSON Product CRUD APIs using Flask-SQLAlchemy.

## Endpoints

- `GET /api/products`
- `GET /api/products/<id>`
- `POST /api/products`
- `PUT /api/products/<id>`
- `DELETE /api/products/<id>`

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## Curl examples

```bash
curl -X POST http://localhost:5000/api/products \
  -H "Content-Type: application/json" \
  -d '{"name":"Keyboard","description":"TKL","price":"99.99","category":"Peripherals","in_stock":1}'

curl http://localhost:5000/api/products

curl -X PUT http://localhost:5000/api/products/1 \
  -H "Content-Type: application/json" \
  -d '{"price":"109.99","in_stock":0}'

curl -X DELETE http://localhost:5000/api/products/1
```

## Test

```bash
python -m pytest tests/ -v
```
