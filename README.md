# College Result Analysis Backend

Setup:
1. python -m venv .venv && source .venv/bin/activate
2. pip install -r requirements.txt
3. cp .env.example .env   (then fill in real values)
4. alembic init alembic   (only if alembic/env.py is missing)
5. uvicorn app.main:app --reload

Health check: http://localhost:8000/api/v1/health
