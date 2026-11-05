# MetriK — Backend (FastAPI)

API REST de MetriK: usuarios, proyectos, recorridos, suavizado del plano, modo GPS,
exportación DXF, validación contra wincha y modelos de ML.

## Requisitos

- Python 3.12+ (probado con 3.14)
- PostgreSQL 14+ (probado con 16 y 18)

## Instalación

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements-dev.txt
copy .env.example .env          # y editar DATABASE_URL y SECRET_KEY
```

Crear la base de datos (una sola vez) y aplicar las migraciones:

```bash
psql -U postgres -c "CREATE DATABASE metrik;"
alembic upgrade head
```

## Ejecutar

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Documentación interactiva (Swagger): http://localhost:8000/docs
- Desde el **emulador** Android: `http://10.0.2.2:8000`
- Desde el **celular** (misma red Wi-Fi): `http://<IP-de-tu-PC>:8000`

## Endpoints principales (`/api/v1`)

| Grupo | Endpoints |
|-------|-----------|
| Autenticación | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` |
| Proyectos | `GET/POST /projects`, `GET/PATCH/DELETE /projects/{id}` |
| Recorridos | `POST /projects/{id}/surveys` (interior · exterior · importado), `GET /surveys/{id}` |
| Geometría | `POST /geometry/analyze`, `/smooth`, `/distance`, `/scale`, `/calibrate-image` |
| GPS | `POST /gps/error`, `/gps/area`, `/gps/distance` |
| DXF | `GET /surveys/{id}/export/dxf?scale=100` |
| Validación | `PUT /surveys/{id}/references`, `GET /surveys/{id}/validation`, `GET /projects/{id}/validation(.csv)` |
| ML | `GET /ml/info`, `GET /surveys/{id}/ml` |

## Pruebas

```bash
pytest                       # 89 pruebas (SQLite en memoria)
pytest --cov                 # con cobertura
set TEST_DATABASE_URL=postgresql+asyncpg://usuario:clave@localhost:5432/metrik_test
pytest                       # integración contra PostgreSQL real
python scripts/generar_evidencias.py   # captura .png + descripción .txt por prueba
```

| Tipo | Carpeta | Cantidad |
|------|---------|----------|
| Unitarias | `tests/unit/` | 53 |
| Integración | `tests/integration/` | 28 |
| Funcionales | `tests/functional/` | 8 |

Evidencias en [`../evidencias/backend/`](../evidencias/backend/README.md).

## Migraciones

```bash
alembic revision --autogenerate -m "descripción del cambio"
alembic upgrade head
alembic downgrade -1
```

## Estructura

```
app/
├── core/       configuración, base de datos, seguridad (JWT/bcrypt), dependencias
├── models/     SQLAlchemy: User, Project, Survey, ReferenceMeasurement
├── schemas/    Pydantic: entrada/salida de la API
├── services/   lógica: geometría, suavizado, GPS, escalas, DXF, validación, ML
└── routes/     endpoints FastAPI
alembic/        migraciones
scripts/        generación de evidencias
tests/          unit / integration / functional
```
