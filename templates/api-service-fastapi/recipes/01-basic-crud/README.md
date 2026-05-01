# 01 Basic CRUD

Task CRUD recipe with pagination and filters.

## Endpoints

- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /tasks`
- `PUT /tasks/{task_id}`
- `DELETE /tasks/{task_id}`

## Run

```bash
pip install -r requirements.txt
uvicorn main:app --reload
```

## Curl

```bash
curl -X POST "http://127.0.0.1:8000/tasks" -H "Content-Type: application/json" -d '{"title":"Write FastAPI cookbook","description":"Create CRUD recipe","completed":false,"priority":2}'
curl -X GET "http://127.0.0.1:8000/tasks?skip=0&limit=20"
curl -X PUT "http://127.0.0.1:8000/tasks/1" -H "Content-Type: application/json" -d '{"completed":true,"priority":1}'
curl -X DELETE "http://127.0.0.1:8000/tasks/1"
```
