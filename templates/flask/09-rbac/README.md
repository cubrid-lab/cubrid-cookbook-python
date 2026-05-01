# 09 RBAC (Hierarchical Permissions)

Standalone Flask recipe for hierarchical role-based access control (RBAC) over document APIs.

## Endpoints

- `PUT /roles/<role_key>`
- `POST /users`
- `POST /users/<user_key>/roles/<role_key>`
- `POST /documents`
- `GET /documents/<document_key>?as_user_key=<user_key>`
- `PUT /documents/<document_key>`

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python run.py
```

## Test

```bash
python -m pytest tests/ -v
```

## Notes

- Role inheritance traverses parent chains to collect effective permissions.
- Owner access is always allowed for read/write on owned documents.
- `admin:*` bypasses specific document permission checks.
- Role update cycle detection walks deep parent chains and rejects loops.
