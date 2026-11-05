<div align="center">

# 📐 MetriK — Backend

**API REST del odómetro digital que convierte el recorrido de un celular en un plano de planta a escala.**

[![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.162-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.1_async-D71F00?logo=sqlalchemy&logoColor=white)](https://www.sqlalchemy.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.9-F7931E?logo=scikitlearn&logoColor=white)](https://scikit-learn.org/)
<br>
[![Docker](https://img.shields.io/badge/Docker-imagen-2496ED?logo=docker&logoColor=white)](Dockerfile)
[![Cloud Run](https://img.shields.io/badge/Google_Cloud_Run-producción-4285F4?logo=googlecloud&logoColor=white)](#despliegue)
[![GitHub Actions](https://img.shields.io/badge/GitHub_Actions-CI%2FCD-2088FF?logo=githubactions&logoColor=white)](.github/workflows)
[![Pruebas](https://img.shields.io/badge/pruebas-102_pasando-2EA44F?logo=pytest&logoColor=white)](#pruebas)

[Inicio rápido](#inicio-rapido) ·
[Arquitectura](#arquitectura) ·
[Despliegue](#despliegue) ·
[CI/CD](#cicd) ·
[Variables](#variables) ·
[API](#api)

</div>

---

## 📖 ¿Qué hace?

La app Android de MetriK registra el recorrido de una persona caminando por el borde de un ambiente
(giroscopio, acelerómetro, ARCore o GPS). Este backend recibe ese recorrido y lo convierte en un
**plano limpio y a escala**:

| Capacidad | Descripción |
|-----------|-------------|
| 🏠 **Modo interior** | Suaviza el trazo ruidoso del odómetro: simplificación RDP, ortogonalización a 90° y cierre del polígono con la regla del tránsito. |
| 🌳 **Modo exterior** | Convierte coordenadas GPS a metros, filtra lecturas imprecisas y calcula área, perímetro y margen de error. |
| 🖼️ **Modo importado** | Mide sobre un plano existente, calibrado con una distancia conocida. |
| 📏 **Escalas** | Sugiere y valida la escala de impresión (1:50, 1:100, …). |
| 📐 **Exportación DXF** | Genera el plano en formato CAD abierto (AutoCAD, LibreCAD). |
| ✅ **Validación** | Compara las medidas de la app con la wincha o con referencias externas (cancha, catastro, satélite). |
| 🤖 **Machine Learning** | M1 corrige la longitud de cada muro y M2 clasifica la confiabilidad del recorrido. |
| 📥 **Importación de campo** | Carga mediciones reales desde un volcado `pg_dump`. |

---

<a id="arquitectura"></a>

## 🏗️ Arquitectura

### Vista general (producción)

```mermaid
flowchart LR
    subgraph Cliente
        APP["📱 App Android<br/>MetriK"]
        WEB["💻 Swagger / navegador"]
    end

    subgraph GCP["☁️ Google Cloud"]
        direction TB
        RUN["🚀 Cloud Run<br/>metrik-api<br/>(FastAPI + Uvicorn)"]
        JOB["⚙️ Cloud Run Job<br/>metrik-api-migraciones<br/>(alembic upgrade head)"]
        SM["🔐 Secret Manager<br/>DATABASE_URL · SECRET_KEY"]
        AR["📦 Artifact Registry<br/>imágenes Docker"]
    end

    DB[("🐘 PostgreSQL<br/>gestionado (Neon)")]
    GH["🐙 GitHub Actions<br/>CI/CD"]

    APP -- "HTTPS + JWT" --> RUN
    WEB -- HTTPS --> RUN
    RUN -- "asyncpg + SSL" --> DB
    JOB -- migraciones --> DB
    SM -. secretos al iniciar .-> RUN
    SM -. secretos .-> JOB
    GH -- "docker push" --> AR
    AR -- imagen --> RUN
    AR -- imagen --> JOB
    GH -- "gcloud run deploy" --> RUN
```

### Capas internas

```mermaid
flowchart TB
    REQ(["Petición HTTP"]) --> ROUTES

    subgraph API["app/"]
        ROUTES["<b>routes/</b><br/>endpoints FastAPI<br/>auth · projects · geometry · gps · validation · ml · field"]
        SCHEMAS["<b>schemas/</b><br/>validación Pydantic<br/>entrada y salida"]
        DEPS["<b>core/deps</b><br/>usuario actual (JWT)<br/>sesión de BD"]
        SERVICES["<b>services/</b><br/>lógica de negocio<br/>suavizado · geometría · GPS · escala · DXF · validación · ML"]
        MODELS["<b>models/</b><br/>ORM SQLAlchemy"]
    end

    ML[["ml/modelos/*.joblib<br/>scikit-learn"]]
    DB[("PostgreSQL")]

    ROUTES <--> SCHEMAS
    ROUTES --> DEPS
    ROUTES --> SERVICES
    SERVICES --> MODELS
    SERVICES --> ML
    MODELS --> DB
```

### Procesamiento de un recorrido

Cada recorrido que llega por `POST /projects/{id}/surveys` sigue este camino según su modo:

```mermaid
flowchart TD
    IN["📥 Recorrido recibido"] --> MODE{"¿Modo?"}

    MODE -- interior --> I1["Trazo crudo del odómetro"]
    I1 --> I2["Simplificación<br/>Ramer-Douglas-Peucker"]
    I2 --> I3["Orientación dominante<br/>del ambiente"]
    I3 --> I4["Ortogonalización<br/>lados a 0° / 90°"]
    I4 --> I5["Fusión de lados colineales"]
    I5 --> I6["Cierre del polígono<br/>regla del tránsito"]

    MODE -- exterior --> E1["Lecturas GPS"]
    E1 --> E2["Filtro por precisión<br/>≤ GPS_MAX_ACCURACY_M"]
    E2 --> E3["Lat/Lon → metros"]

    MODE -- importado --> P1["Puntos sobre plano<br/>calibrado"]

    I6 --> G["📐 Análisis geométrico<br/>área · perímetro · ángulos · concavidad"]
    E3 --> G
    P1 --> G
    G --> S["Escala sugerida<br/>1:50 · 1:100 · …"]
    S --> DB[("💾 Guardar recorrido")]

    DB --> OUT1["📄 Exportar DXF"]
    DB --> OUT2["✅ Validar vs. wincha / referencia"]
    DB --> OUT3["🤖 Análisis ML<br/>M1 corrige muros · M2 confiabilidad"]
```

### Secuencia: de la app al plano

```mermaid
sequenceDiagram
    autonumber
    actor U as Usuario
    participant A as App Android
    participant API as API (Cloud Run)
    participant S as Servicios
    participant DB as PostgreSQL

    U->>A: Inicia sesión
    A->>API: POST /api/v1/auth/login
    API->>DB: Buscar usuario y verificar bcrypt
    API-->>A: access_token (JWT)

    U->>A: Camina por el borde del ambiente
    A->>API: POST /api/v1/projects/{id}/surveys (Bearer JWT)
    API->>S: Suavizar + analizar geometría + escala
    S-->>API: Vértices, área, perímetro, escala
    API->>DB: INSERT surveys
    API-->>A: 201 Recorrido procesado

    U->>A: Descargar plano
    A->>API: GET /api/v1/surveys/{id}/export/dxf?scale=100
    API-->>A: Archivo .dxf
```

### Modelo de datos

```mermaid
erDiagram
    USERS ||--o{ PROJECTS : "es dueño de"
    PROJECTS ||--o{ SURVEYS : contiene
    SURVEYS ||--o{ REFERENCE_MEASUREMENTS : "se valida con"
    SURVEYS ||--o{ SENSOR_READINGS : registra
    USERS ||--o{ GPS_TRIALS : realiza
    USERS ||--o{ SENSOR_CALIBRATIONS : calibra

    USERS {
        int id PK
        string email UK
        string full_name
        string hashed_password
        bool is_active
    }
    PROJECTS {
        int id PK
        int owner_id FK
        string name
        text description
    }
    SURVEYS {
        int id PK
        int project_id FK
        string mode "interior, exterior o imported"
        json raw_points
        json vertices
        json wall_lengths_m
        float area_m2
        float perimeter_m
        float closure_error_m
        int scale_denominator
        string source "app o campo"
    }
    REFERENCE_MEASUREMENTS {
        int id PK
        int survey_id FK
        int wall_index
        json readings_m "lecturas de wincha"
        float real_length_m
    }
    SENSOR_READINGS {
        bigint id PK
        int survey_id FK
        int seq
        string kind "motion, gps o corner"
        float gyro_z_dps
        float lat
        float lon
    }
    GPS_TRIALS {
        int id PK
        int owner_id FK
        float real_distance_m
        float measured_distance_m
        float error_m
    }
    SENSOR_CALIBRATIONS {
        int id PK
        int owner_id FK
        string kind
        json params
    }
```

---

<a id="inicio-rapido"></a>

## 🚀 Inicio rápido

**Requisitos:** Python 3.12+ · PostgreSQL 14+ (local o en la nube) · *(opcional)* Docker

```bash
# 1. Clonar e instalar
git clone https://github.com/Taller-Metrik/backend.git
cd backend
python -m venv .venv
.venv\Scripts\activate                 # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt

# 2. Configurar
copy .env.example .env                 # Linux/macOS: cp  → editar DATABASE_URL y SECRET_KEY

# 3. Base de datos
psql -U postgres -c "CREATE DATABASE metrik;"
alembic upgrade head

# 4. Levantar
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

| Desde | URL |
|-------|-----|
| Navegador (Swagger) | http://localhost:8000/docs |
| Navegador (ReDoc) | http://localhost:8000/redoc |
| Emulador Android | `http://10.0.2.2:8000` |
| Celular en la misma red Wi-Fi | `http://<IP-de-tu-PC>:8000` |

### Con Docker (igual que en producción)

```bash
docker build -t metrik-api .
docker run --rm -p 8080:8080 --env-file .env metrik-api
# → http://localhost:8080/docs
```

---

<a id="despliegue"></a>

## ☁️ Despliegue en Google Cloud

La API de producción corre en **[Google Cloud Run](https://cloud.google.com/run)**, un servicio
*serverless* de contenedores: Google ejecuta la imagen Docker, le da una URL HTTPS pública y la escala
según el tráfico, sin administrar servidores.

### ¿Dónde vive cada pieza?

| Pieza | Servicio | Detalle |
|-------|----------|---------|
| 🚀 API | **Cloud Run**, servicio `metrik-api` | 1 vCPU · 1 GiB RAM · 0 a 3 instancias · puerto 8080 |
| ⚙️ Migraciones | **Cloud Run Jobs**, `metrik-api-migraciones` | Ejecuta `alembic upgrade head` antes de cada despliegue |
| 📦 Imágenes | **Artifact Registry**, repositorio `metrik` | Una imagen por commit (`:<sha>`), lo que permite volver atrás |
| 🔐 Secretos | **Secret Manager** | `metrik-database-url` y `metrik-secret-key`; el CD los sincroniza desde los secretos de GitHub y nunca quedan en la imagen |
| 🐘 Base de datos | **PostgreSQL gestionado** (Neon) | Fuera de GCP; conexión con SSL y compatible con su *pooler* |
| 🔑 Acceso de GitHub | **Cuenta de servicio** `metrik-cicd` | Su llave JSON se guarda como secreto `GCP_CREDENTIALS`; el proyecto y la cuenta se leen del propio JSON |

- **Región:** `southamerica-west1` (Santiago), la más cercana a Perú. Se cambia con la variable `GCP_REGION`.
- **URL pública:** Cloud Run asigna una del tipo `https://metrik-api-<hash>.<región>.run.app`. Se ve en
  **GitHub → Actions → CD → entorno `produccion`** o con
  `gcloud run services describe metrik-api --region <REGIÓN> --format='value(status.url)'`.
  Esa es la URL que se configura en la app Android.
- **Escalado y costo:** con `min-instances 0` el servicio se apaga cuando nadie lo usa, así que el
  tráfico de un proyecto académico entra en la capa gratuita de Cloud Run. La contrapartida es que la
  primera petición después de un rato tarda unos segundos (*arranque en frío*).

### ¿Cómo llega el código a producción?

```mermaid
flowchart TB
    subgraph REV["1 · Revisión de código"]
        direction LR
        DEV["👩‍💻 Commit en<br/>feature/*"] --> PR1["PR → develop"]
        PR1 --> CI1{"CI"}
        CI1 -- "✅" --> D["develop"]
        CI1 -. "❌ corregir" .-> DEV
        D --> PR2["PR develop → main"]
        PR2 --> CI2{"CI"}
        CI2 -- "✅" --> M["main"]
    end

    subgraph PIPE["2 · Despliegue automático (cd.yml)"]
        direction LR
        C0["Validar JSON<br/>GCP_CREDENTIALS"] --> C1["CI completo"]
        C1 --> C2["docker build"]
        C2 --> C3["push a<br/>Artifact Registry"]
        C3 --> C4["Cloud Run Job<br/>alembic upgrade head"]
        C4 --> C5["gcloud run deploy<br/>nueva revisión"]
        C5 --> C6["Prueba de humo<br/>GET /health"]
    end

    M --> C0
    C6 --> PROD(["🌐 Producción en Cloud Run<br/>https://metrik-api-….run.app"])
```

Si las migraciones fallan, **no se despliega** la nueva versión y la anterior sigue atendiendo.
Cada despliegue crea una **revisión** nueva de Cloud Run; volver atrás es redirigir el tráfico a la
revisión anterior, sin reconstruir nada.

### Puesta en marcha (una sola vez)

1. Crear un proyecto en Google Cloud con facturación activa.
2. Seguir [`docs/RUNBOOK.md` § 1](docs/RUNBOOK.md#1-configuración-inicial-en-google-cloud-una-sola-vez),
   por consola o con `gcloud`: activar las APIs, crear la cuenta de servicio `metrik-cicd` con sus roles,
   **descargar su llave JSON**.
3. En GitHub, crear los secretos **`GCP_CREDENTIALS`** (el JSON completo) y **`DATABASE_URL`** ([detalle abajo](#variables-en-github-para-el-despliegue)).
4. Hacer merge a `main`. El primer despliegue se ejecuta solo y crea el repositorio de imágenes si no existe.

---

<a id="cicd"></a>

## 🔄 CI/CD

| Workflow | Se ejecuta en | Pasos |
|----------|---------------|-------|
| [`ci.yml`](.github/workflows/ci.yml) | PR a `develop` o `main` · push a `develop` | • Pruebas con **SQLite** y con **PostgreSQL 16** (matriz)<br/>• Cobertura de `app/`<br/>• `alembic upgrade head` sobre una base vacía<br/>• `docker build` + arranque del contenedor<br/>• Prueba de humo: `/health` y `/api/v1/ml/info` |
| [`cd.yml`](.github/workflows/cd.yml) | Push a `main` · manual (*Run workflow*) | • Reutiliza todo el CI<br/>• Valida la llave JSON `GCP_CREDENTIALS` y lee de ella el proyecto y la cuenta<br/>• Sincroniza `DATABASE_URL` / `SECRET_KEY` de GitHub con Secret Manager<br/>• Imagen → Artifact Registry (`:<sha>`; crea el repositorio si no existe)<br/>• Migraciones en Cloud Run Job<br/>• Despliegue en Cloud Run con secretos de Secret Manager<br/>• Prueba de humo contra la URL pública |

### Flujo de ramas

```mermaid
gitGraph
    commit id: "chore: inicializar"
    branch develop
    checkout develop
    branch feature/modo-gps
    checkout feature/modo-gps
    commit id: "feat(gps): modo exterior"
    checkout develop
    merge feature/modo-gps id: "merge modo-gps"
    branch fix/conexion-pooler
    checkout fix/conexion-pooler
    commit id: "fix(bd): pooler Neon"
    checkout develop
    merge fix/conexion-pooler id: "merge pooler"
    checkout main
    merge develop id: "🚀 CD → Cloud Run"
```

| Rama | Propósito | Despliega |
|------|-----------|:---------:|
| `main` | Producción | ✅ automático |
| `develop` | Integración: lo que irá en el próximo despliegue | Solo CI |
| `feature/<nombre>` | Nueva funcionalidad, creada desde `develop` | Solo CI en el PR |
| `fix/<nombre>` | Corrección, creada desde `develop` | Solo CI en el PR |

Commits con [Conventional Commits](https://www.conventionalcommits.org/es/): `feat(gps): …`,
`fix(bd): …`, `docs: …`, `test: …`, `chore: …`.

---

<a id="variables"></a>

## 🔧 Variables de entorno

### De la aplicación

Se leen de `.env` (desarrollo) o del entorno del contenedor (producción) a través de
[`app/core/config.py`](app/core/config.py). Plantilla: [`.env.example`](.env.example).

<!-- AUTO-GENERATED: app/core/config.py + .env.example -->
| Variable | Obligatoria | Por defecto | Descripción |
|----------|:-----------:|-------------|-------------|
| `DATABASE_URL` | **Sí** | `postgresql+asyncpg://postgres:postgres@localhost:5432/metrik` | Conexión a PostgreSQL. Acepta `postgres://`, `postgresql://` o `postgresql+asyncpg://` y convierte `?sslmode=require`. Con un *pooler* (Neon `-pooler`) desactiva las sentencias preparadas. |
| `SECRET_KEY` | **Sí** | clave de desarrollo | Firma de los JWT. Mínimo 32 caracteres: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `1440` | Duración del token de sesión (minutos). |
| `DEBUG` | No | `false` | Modo depuración. |
| `ALLOWED_ORIGINS` | No | `["*"]` | Orígenes CORS, **en formato JSON**: `["https://app.metrik.pe"]`. |
| `JWT_ALGORITHM` | No | `HS256` | Algoritmo de firma JWT. |
| `ML_MODELS_DIR` | No | `ml/modelos` | Carpeta con `corrector_muros.joblib` y `clasificador_recorrido.joblib`. |
| `APP_NAME` · `APP_VERSION` · `API_PREFIX` | No | `MetriK API` · `0.1.0` · `/api/v1` | Metadatos y prefijo de la API. |
| `RDP_EPSILON_M` | No | `0.10` | Tolerancia de simplificación del trazo (m). |
| `SNAP_TOLERANCE_DEG` | No | `15.0` | Tolerancia para enderezar ángulos (°). |
| `CLOSURE_TOLERANCE_M` | No | `1.0` | Tolerancia base de cierre (m). Con esquinas marcadas es fija; con trazo crece al 5 % de lo recorrido, hasta 3 m. |
| `GPS_MAX_ACCURACY_M` | No | `10.0` | Precisión GPS máxima aceptada por lectura (m). |
| `GPS_CALIBRATION_THRESHOLD_M` | No | `8.0` | Umbral de error para recomendar calibración (m). |
| `TEST_DATABASE_URL` | No | SQLite en memoria | Solo pruebas: PostgreSQL real para la integración. |
<!-- /AUTO-GENERATED -->

### Variables en GitHub para el despliegue

**Solo hacen falta dos secretos.** Se crean en **Settings → Secrets and variables → Actions → *Secrets* →
New repository secret**.

| Secreto | Obligatorio | Valor |
|---------|:-----------:|-------|
| `GCP_CREDENTIALS` | **Sí** | **El JSON completo** de la llave de la cuenta de servicio, tal como lo descarga Google Cloud (desde `{` hasta `}`) |
| `DATABASE_URL` | **Sí** | URL de conexión de Neon, tal cual (`postgresql://usuario:clave@host/metrik?sslmode=require`) |
| `SECRET_KEY` | No | Clave de 32+ caracteres para los tokens. Si no se define, el CD genera una la primera vez y la reutiliza |

El CD copia estos valores a **Secret Manager** (`metrik-database-url`, `metrik-secret-key`), y Cloud Run
los lee desde ahí. No hay que crear nada a mano en Secret Manager.

> ⚠️ Pega el archivo **tal como lo descarga Google Cloud**, abierto en el Bloc de notas y copiado con
> `Ctrl+A` / `Ctrl+C`. No le agregues comentarios ni lo reformatees: la `private_key` debe quedar en
> **una sola línea** con los saltos escritos como `\n`, y los `-----BEGIN/END PRIVATE KEY-----` son
> parte de la llave.

Del JSON, el CD toma automáticamente el proyecto (`project_id`) y la cuenta (`client_email`). Antes de
desplegar comprueba que el JSON sea válido y de una cuenta de servicio; si no, se detiene con un mensaje
claro. **Nunca subas este archivo al repositorio.**

Opcionalmente, en la pestaña ***Variables***, solo si quieres cambiar los valores por defecto:

| Variable | Por defecto |
|----------|-------------|
| `GCP_REGION` | `southamerica-west1` |
| `CLOUD_RUN_SERVICE` | `metrik-api` |
| `GAR_REPOSITORY` | `metrik` |
| `GCP_RUNTIME_SERVICE_ACCOUNT` | la cuenta del JSON |
| `ALLOWED_ORIGINS` | `["*"]` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` |

### En Cloud Run

| Variable | De dónde sale |
|----------|---------------|
| `DATABASE_URL` | Secreto de GitHub `DATABASE_URL` → Secret Manager `metrik-database-url` |
| `SECRET_KEY` | Secreto de GitHub `SECRET_KEY` (o generada) → Secret Manager `metrik-secret-key` |
| `DEBUG` | Fija en `false` |
| `ALLOWED_ORIGINS` · `ACCESS_TOKEN_EXPIRE_MINUTES` | Variables de GitHub (o el valor por defecto) |
| `PORT` | La inyecta Cloud Run (`8080`) |

---

<a id="api"></a>

## 🔌 Endpoints

Documentación interactiva en **`/docs`** (Swagger) y **`/redoc`**. Todas las rutas llevan el prefijo
`/api/v1`, salvo `/health`. Las protegidas requieren `Authorization: Bearer <token>`.

<!-- AUTO-GENERATED: app/routes/*.py -->
| Grupo | Endpoints |
|-------|-----------|
| 🩺 Sistema | `GET /health` |
| 🔑 Autenticación | `POST /auth/register` · `POST /auth/login` · `GET /auth/me` |
| 📁 Proyectos | `GET/POST /projects` · `GET/PATCH/DELETE /projects/{id}` |
| 🚶 Recorridos | `GET/POST /projects/{id}/surveys` · `GET/PATCH/DELETE /surveys/{id}` |
| 📐 Geometría | `POST /geometry/analyze` · `/smooth` · `/distance` · `/scale` · `/calibrate-image` |
| 🛰️ GPS | `POST /gps/error` · `/gps/area` · `/gps/distance` |
| 📍 Referencia GPS y calibración | `GET/PUT /surveys/{id}/gps-reference` · `GET/POST /calibrations` |
| 📄 DXF | `GET /surveys/{id}/export/dxf?scale=100` |
| ✅ Validación | `PUT /surveys/{id}/references` · `GET /surveys/{id}/validation` · `GET /projects/{id}/validation(.csv)` |
| 🤖 Machine Learning | `GET /ml/info` · `GET /surveys/{id}/ml` |
<!-- /AUTO-GENERATED -->

<details>
<summary><b>Ejemplo con <code>curl</code></b></summary>

```bash
API=http://localhost:8000/api/v1

# Registro e inicio de sesión
curl -X POST $API/auth/register -H "Content-Type: application/json" \
  -d '{"email":"ana@metrik.pe","full_name":"Ana","password":"clave-segura-123"}'
TOKEN=$(curl -s -X POST $API/auth/login -d "username=ana@metrik.pe&password=clave-segura-123" | jq -r .access_token)

# Crear un proyecto
curl -X POST $API/projects -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Pabellón A","description":"Aulas del 2.º piso"}'
```
</details>

---

<a id="pruebas"></a>

## 🧪 Pruebas

```bash
pytest                                  # SQLite en memoria, sin configuración
pytest --cov --cov-report=term-missing  # con cobertura

# Integración contra PostgreSQL real
set TEST_DATABASE_URL=postgresql+asyncpg://usuario:clave@localhost:5432/metrik_test   # Linux/macOS: export
pytest

python scripts/generar_evidencias.py    # captura .png + descripción .txt de cada prueba
```

<!-- AUTO-GENERATED: tests/ -->
| Tipo | Carpeta | Pruebas | Qué cubren |
|------|---------|--------:|------------|
| Unitarias | `tests/unit/` | 60 | Algoritmos aislados: geometría, suavizado, GPS, escala, DXF, ML, seguridad |
| Integración | `tests/integration/` | 34 | Endpoints con base de datos real |
| Funcionales | `tests/functional/` | 8 | Flujos completos de usuario, del registro al plano DXF |
| **Total** | | **102** | |
<!-- /AUTO-GENERATED -->

---

## 🛠️ Comandos útiles

<!-- AUTO-GENERATED: requirements*.txt, alembic.ini, scripts/ -->
| Comando | Descripción |
|---------|-------------|
| `uvicorn app.main:app --reload` | Servidor de desarrollo con recarga automática |
| `pytest` / `pytest --cov` | Pruebas / pruebas con cobertura |
| `alembic upgrade head` | Aplicar migraciones pendientes |
| `alembic revision --autogenerate -m "mensaje"` | Crear una migración a partir de los modelos |
| `alembic downgrade -1` | Revertir la última migración |
| `python scripts/importar_mediciones.py --archivo <dump.sql> --email <correo>` | Importar mediciones de campo (idempotente) |
| `python scripts/generar_evidencias.py` | Generar evidencias de cada prueba |
| `docker build -t metrik-api .` | Construir la imagen de producción |
<!-- /AUTO-GENERATED -->

<details>
<summary><b>Importar mediciones de campo</b></summary>

Carga un volcado `pg_dump` con lecturas reales de giroscopio, acelerómetro y GPS. El SQL se lee
como texto (**no se ejecuta**) y cada recorrido se procesa con los algoritmos de MetriK.

```bash
alembic upgrade head
python scripts/importar_mediciones.py --archivo C:/ruta/mediciones.sql \
  --email usuario@metrik.pe --nombre "Nombre" --password "<clave de la cuenta nueva>"
```

Opciones: `--proyecto` (por defecto *Mediciones de campo*) y `--prefijo`.
</details>

---

## 📂 Estructura

```
backend/
├── app/
│   ├── core/          configuración, base de datos, seguridad (JWT/bcrypt), dependencias
│   ├── models/        ORM SQLAlchemy: User, Project, Survey, ReferenceMeasurement, SensorReading, …
│   ├── schemas/       Pydantic: entrada y salida de la API
│   ├── services/      lógica: suavizado, geometría, GPS, escala, DXF, validación, ML, importación
│   ├── routes/        endpoints FastAPI
│   └── main.py        creación de la app, CORS y /health
├── alembic/           migraciones de la base de datos
├── ml/modelos/        modelos entrenados (.joblib) que carga la API
├── scripts/           importación de mediciones y generación de evidencias
├── tests/             unit · integration · functional
├── docs/RUNBOOK.md    configuración de GCP, despliegue, monitoreo y rollback
├── .github/workflows/ ci.yml · cd.yml
└── Dockerfile         imagen de producción (Cloud Run)
```

---

## 🆘 Problemas frecuentes

| Problema | Solución |
|----------|----------|
| `prepared statement "…" does not exist` | Ya está resuelto para el *pooler* de Neon: la URL debe contener `pooler` en el host. |
| `ModelsNotAvailableError` | Faltan los `.joblib` en `ml/modelos/`, o `ML_MODELS_DIR` apunta a otra carpeta. |
| Error de CORS desde un navegador | `ALLOWED_ORIGINS` debe ser una lista JSON: `["https://dominio"]`. |
| `SECRET_KEY` rechazada al iniciar | Debe tener al menos 32 caracteres. |
| La API tarda en la primera petición | Es el arranque en frío de Cloud Run (`min-instances 0`). |

Monitoreo, *rollback* y errores de despliegue: **[`docs/RUNBOOK.md`](docs/RUNBOOK.md)**.
