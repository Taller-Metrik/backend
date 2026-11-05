# RUNBOOK — Despliegue y operación de MetriK Backend

Producción corre en **Google Cloud Run**. La imagen se guarda en **Artifact Registry**, los secretos de la
app en **Secret Manager** y la base de datos es PostgreSQL externo (Neon). GitHub Actions se autentica con
la **llave JSON de una cuenta de servicio**, guardada como secreto `GCP_CREDENTIALS`.

```
GitHub (push a main)
  └─ cd.yml ─► CI (pruebas + docker) ─► Artifact Registry ─► Cloud Run Job "…-migraciones" (alembic upgrade head)
                                                           └─► Cloud Run "metrik-api"  ◄── Secret Manager (DATABASE_URL, SECRET_KEY)
```

---

## 1. Configuración inicial en Google Cloud (una sola vez)

Son tres cosas: **una cuenta de servicio con su llave JSON**, **dos secretos** y **las APIs activadas**.

### Opción A — Consola web

1. **Activar APIs.** En *APIs y servicios → Biblioteca*, habilitar **Cloud Run Admin API**,
   **Artifact Registry API** y **Secret Manager API**.
2. **Crear la cuenta de servicio.** En *IAM y administración → Cuentas de servicio → Crear cuenta de servicio*:
   - Nombre: `metrik-cicd`
   - Roles:

     | Rol | Para qué |
     |-----|----------|
     | **Administrador de Cloud Run** (`roles/run.admin`) | Desplegar el servicio y el job de migraciones |
     | **Administrador de Artifact Registry** (`roles/artifactregistry.admin`) | Crear el repositorio de imágenes la primera vez y subir imágenes |
     | **Usuario de cuenta de servicio** (`roles/iam.serviceAccountUser`) | Que Cloud Run ejecute con esta misma cuenta |
     | **Descriptor de acceso a secretos de Secret Manager** (`roles/secretmanager.secretAccessor`) | Que la API lea `DATABASE_URL` y `SECRET_KEY` |
     | **Visualizador de Secret Manager** (`roles/secretmanager.viewer`) | Que el CD compruebe que los secretos existen |
3. **Descargar la llave JSON.** Abrir la cuenta `metrik-cicd` → pestaña **Claves** → *Agregar clave →
   Crear clave nueva → JSON*. Se descarga un archivo `.json`: **ese es el que va a GitHub** (sección 2).
4. **Crear los secretos.** En *Seguridad → Secret Manager → Crear secreto*:

   | Nombre (exacto) | Valor |
   |-----------------|-------|
   | `metrik-database-url` | URL de conexión de Neon, tal cual (`postgresql://usuario:clave@host/metrik?sslmode=require`) |
   | `metrik-secret-key` | Clave aleatoria de 32 caracteres o más: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |

> Si la consola no permite crear la clave ("*Service account key creation is disabled*"), una política de
> la organización bloquea las llaves JSON. En ese caso hay que pedir una excepción al administrador.

### Opción B — `gcloud` (Cloud Shell o Git Bash)

```bash
PROJECT_ID="metrik-prod"      # ID del proyecto de GCP
gcloud config set project "$PROJECT_ID"

gcloud services enable run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

gcloud iam service-accounts create metrik-cicd --display-name="MetriK - CI/CD y ejecución"
SA="metrik-cicd@$PROJECT_ID.iam.gserviceaccount.com"
for ROLE in roles/run.admin roles/artifactregistry.admin roles/iam.serviceAccountUser \
            roles/secretmanager.secretAccessor roles/secretmanager.viewer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:$SA" --role="$ROLE" --condition=None
done

# Llave JSON → pegar su contenido en GitHub y luego BORRAR el archivo local
gcloud iam service-accounts keys create metrik-cicd.json --iam-account="$SA"

# Secretos de la app
printf '%s' 'postgresql://usuario:clave@host/metrik?sslmode=require' | gcloud secrets create metrik-database-url --data-file=-
python -c "import secrets; print(secrets.token_urlsafe(48), end='')"  | gcloud secrets create metrik-secret-key --data-file=-
```

---

## 2. Configuración en GitHub

### Secreto obligatorio (el único)

**Settings → Secrets and variables → Actions → pestaña *Secrets* → New repository secret**

| Nombre | Valor |
|--------|-------|
| `GCP_CREDENTIALS` | **El contenido completo del archivo `.json`** descargado en el paso 1, desde la primera `{` hasta la última `}`, sin modificarlo. |

Del JSON se obtienen automáticamente el **ID del proyecto** (`project_id`) y la **cuenta de servicio**
(`client_email`), así que no hay que escribirlos en ningún otro lugar.

> ⚠️ La llave da acceso al proyecto: **no la subas al repositorio** ni la compartas por chat. Después de
> pegarla en GitHub, borra el archivo descargado. Si se filtra, elimínala en *Cuentas de servicio → Claves*
> y crea una nueva.

### Variables opcionales

Pestaña *Variables*. Solo hacen falta si se quiere cambiar el valor por defecto.

| Variable | Por defecto | Uso |
|----------|-------------|-----|
| `GCP_REGION` | `southamerica-west1` | Región de Cloud Run y Artifact Registry |
| `CLOUD_RUN_SERVICE` | `metrik-api` | Nombre del servicio (el job de migraciones se llama `<servicio>-migraciones`) |
| `GAR_REPOSITORY` | `metrik` | Repositorio de Artifact Registry; se crea solo si no existe |
| `GCP_RUNTIME_SERVICE_ACCOUNT` | La cuenta del JSON | Para ejecutar la API con otra cuenta distinta a la que despliega |
| `ALLOWED_ORIGINS` | `["*"]` | CORS en formato JSON |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Duración del token |

**Entorno `produccion`:** se crea solo en el primer despliegue. En *Settings → Environments → produccion*
se pueden exigir revisores antes de cada despliegue y limitarlo a la rama `main`.

### Variables de la app en Cloud Run (las define `cd.yml`)

| Variable | Origen |
|----------|--------|
| `DATABASE_URL` | Secret Manager `metrik-database-url` |
| `SECRET_KEY` | Secret Manager `metrik-secret-key` |
| `DEBUG` | Fijo `false` |
| `ACCESS_TOKEN_EXPIRE_MINUTES`, `ALLOWED_ORIGINS` | Variables de GitHub (o su valor por defecto) |
| `PORT` | Lo inyecta Cloud Run (8080) |

---

## 3. Desplegar

1. Abrir un PR `develop → main`. El CI debe pasar en verde.
2. Hacer el merge. `cd.yml` valida el JSON, construye, migra y despliega automáticamente.
3. Revisar **Actions → CD (Google Cloud Run)**. La URL pública aparece en el entorno `produccion`.

Despliegue manual de la versión actual de `main`: **Actions → CD (Google Cloud Run) → Run workflow**.

---

## 4. Salud y monitoreo

| Comprobación | Cómo |
|--------------|------|
| Estado de la API | `GET <url>/health` → `{"status":"ok","version":"0.1.0"}` |
| Modelos de ML cargados | `GET <url>/api/v1/ml/info` → HTTP 200 |
| Logs | `gcloud run services logs read metrik-api --region <REGION> --limit 100` |
| Revisiones | `gcloud run revisions list --service metrik-api --region <REGION>` |
| Migraciones | `gcloud run jobs executions list --job metrik-api-migraciones --region <REGION>` |

---

## 5. Rollback

**Aplicación:** volver a dirigir el tráfico a la revisión anterior. Es inmediato y no reconstruye nada.

```bash
gcloud run revisions list --service metrik-api --region <REGION>
gcloud run services update-traffic metrik-api --region <REGION> --to-revisions=<REVISION_ANTERIOR>=100
```

Cuando el arreglo llegue a `main`, el siguiente despliegue vuelve a enviar el 100 % del tráfico a la revisión nueva.

**Base de datos:** revertir la última migración solo si el cambio de esquema lo requiere.

```bash
gcloud run jobs execute metrik-api-migraciones --region <REGION> --args=downgrade,-1 --wait
```

---

## 6. Problemas frecuentes

| Síntoma (en Actions) | Causa | Solución |
|----------------------|-------|----------|
| `Falta el secreto GCP_CREDENTIALS` | No se cargó el secreto | Paso 2: crear `GCP_CREDENTIALS` en la pestaña *Secrets* (no en *Variables*). |
| `GCP_CREDENTIALS no es una llave JSON … válida` | Se pegó incompleto o es otro tipo de archivo | Pegar el `.json` completo de una **cuenta de servicio** (`"type": "service_account"`). |
| `No existe el secreto 'metrik-…' en Secret Manager` | Falta el secreto, el nombre no coincide o falta `secretmanager.viewer` | Paso 1.4: revisar los nombres exactos y los roles. |
| `PERMISSION_DENIED` en Artifact Registry | Falta `artifactregistry.admin` | Agregar el rol a la cuenta (paso 1.2). |
| `iam.serviceAccounts.actAs` denegado | Falta `iam.serviceAccountUser` | Agregar el rol a la cuenta (paso 1.2). |
| `API … has not been used in project` | API sin habilitar | Paso 1.1. |
| `--allow-unauthenticated` falla | Una política de la organización bloquea `allUsers` | Pedir una excepción o quitar la opción y usar autenticación de Cloud Run. |
| `prepared statement "…" does not exist` | Pooler en modo transacción (Neon `-pooler`) | Ya está contemplado: la URL debe contener `pooler` en el host. |
| `ModelsNotAvailableError` | Faltan los `.joblib` | Deben estar en `ml/modelos/` del repositorio. |
| Error de CORS desde la web | `ALLOWED_ORIGINS` mal formado | Debe ser una lista JSON: `["https://dominio"]`. |

**Rotar la llave JSON:** crear una clave nueva en la cuenta de servicio, reemplazar `GCP_CREDENTIALS` en
GitHub y eliminar la clave anterior en Google Cloud.

**Rotar un secreto de la app:** `gcloud secrets versions add <secreto> --data-file=-` y volver a desplegar
(*Run workflow*). Como Cloud Run lee `:latest`, la nueva revisión toma el valor nuevo.
