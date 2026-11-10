# Evidencia TDD — Mejora de precisión GPS (RF-18 a RF-21)

Rama: `feature/gps-precision-esquinas` · Fecha: 2026-11-10 · Casos de uso: CU-02, base de CU-09 y CU-10
(ver `docs/casos-de-uso.md`).

## 1. Recorridos de usuario

- Como **usuario medidor**, quiero quedarme quieto en cada esquina del terreno para que el plano use esas
  esquinas promediadas y sea más preciso que caminar sin parar.
- Como **usuario medidor**, quiero volver a fijar la primera esquina al final para saber el error real
  de mi recorrido.
- Como **usuario medidor**, quiero que se descarten las lecturas con mala señal (pocos satélites o C/N0 bajo).
- Como **usuario medidor / perito**, quiero ver siempre el área y el perímetro con su incertidumbre al 95 %.

## 2. Ciclo RED → GREEN → REFACTOR

| Etapa | Commit | Comando | Resultado |
|-------|--------|---------|-----------|
| RED | `d94f08a` | `pytest tests/unit/test_gps_precision.py` | Error de importación: `app.services.gps_precision` no existe |
| RED | `d94f08a` | `pytest tests/integration/test_gps_precision_api.py tests/functional/test_flujo_exterior.py` | 5 fallan (`KeyError: 'uncertainty'`, la API no valida la señal) |
| GREEN | `885493b` | `pytest` (SQLite) y `TEST_DATABASE_URL=… pytest` (PostgreSQL 16) | 116 pasan en ambos |
| REFACTOR | este commit | `pytest` en SQLite y PostgreSQL 16 | 118 pasan en ambos |

Las pruebas se ejecutan en Docker (`python:3.12-slim`, igual que el CI) porque en la máquina de desarrollo
Windows bloquea una DLL de pandas.

### Ajustes de expectativas durante GREEN (no se eligieron semillas a conveniencia)

- **BU-64, BI-34, BF-09:** los umbrales iniciales (área ± 2 %, U95 < 5 %) no eran coherentes con el ruido
  simulado (σ = 1,5 m por lectura): la teoría da U95 ≈ 5,5 % con 30 s por esquina. Se cambiaron a
  "el área real queda dentro de ± U95"; BI-34 y BF-09 usan 60 s por esquina.
- **BF-09:** con un cierre grande la incertidumbre sube honestamente; la garantía correcta es que fijar
  esquinas da menos incertidumbre que el recorrido continuo, no un porcentaje fijo.

### Cambios del REFACTOR (revisiones)

Revisión de código (agente `ecc:fastapi-reviewer`):
- `uncertainty` ya no puede ser nula: con menos de 3 vértices o área nula se lanza `GeometryError` (antes podía dar HTTP 500 o `inf`).
- Se eliminó la importación circular `gps` ↔ `gps_precision` con el módulo nuevo `gps_core` (lectura y proyección); `gps` lo reexporta.
- El cierre GPS ya no se guarda en `closure_error_m`, que es una variable del modelo de ML (solo va en `uncertainty`).
- `POST /gps/area` acepta `transport`.

Revisión física (ingeniero electrónico):
- σ del vértice: σ_v² = máx(dispersión, σ reportada)² / n_ef + σ_b², con σ_b = 0,5 m (error que no se reduce al promediar).
- La duración de una esquina suma solo el tiempo quieto de cada visita.
- Piso por cierre: d/√π (la distancia de cierre sigue una Rayleigh de parámetro σ√2), no d/2.
- `closure_consistent = False` si el cierre supera el percentil 95 esperado (2,448·√(σ₁² + σ₂²)).
- k = 2,5 cuando la σ sale del error de cierre (una sola muestra).
- La app debe enviar `satellites` = usados en la solución y `cn0_dbhz` = media de los 4 usados más fuertes.

## 3. Especificación de pruebas

| # | Qué se garantiza | Prueba | Tipo | Resultado |
|---|------------------|--------|------|-----------|
| BU-61 | Conversión de la precisión de Android (radio 68 %) a σ por eje | `test_gps_precision.py::test_sigma_desde_precision_android` | unitaria | PASA |
| BU-62 | El filtro de señal descarta < 6 satélites o C/N0 < 30 y conserva lecturas sin datos | `::test_filtro_por_senal` | unitaria | PASA |
| BU-63 | Una esquina se fija a < 0,8 m del punto real descartando 3 saltos de 25 m | `::test_fijar_esquina_descarta_atipicos` | unitaria | PASA |
| BU-64 | El polígono se arma con las esquinas fijadas y el área real queda dentro de ± U95 | `::test_poligono_stop_and_go` | unitaria | PASA |
| BU-65 | Volver a la primera esquina mide el cierre y eleva σ | `::test_cierre_estima_sigma` | unitaria | PASA |
| BU-66 | σ_A = √2·σ·L en un cuadrado; σ_P = 2√2·σ | `::test_incertidumbre_cuadrado` | unitaria | PASA |
| BU-67 | La fórmula analítica coincide con Monte Carlo (± 8 %) | `::test_analitico_vs_montecarlo` | unitaria | PASA |
| BU-68 | El intervalo ± U95 contiene el área real en ≥ 90 % de 60 recorridos | `::test_cobertura_incertidumbre` | unitaria | PASA |
| BU-69 | El recorrido continuo sigue funcionando y reporta incertidumbre conservadora | `::test_recorrido_continuo_compatible` | unitaria | PASA |
| BU-70 | Sin lecturas con señal suficiente se responde EX-04 | `::test_poligono_descarta_por_senal` | unitaria | PASA |
| BU-71 | Un cierre incoherente se marca y amplía k a 2,5 | `::test_cierre_incoherente` | unitaria | PASA |
| BU-72 | Una esquina medida 5 minutos no baja de σ_b = 0,5 m | `::test_piso_no_promediable` | unitaria | PASA |
| BI-34 | `POST /gps/area` devuelve método, incertidumbre, cierre y descartes por señal | `test_gps_precision_api.py::test_gps_area_stop_and_go` | integración | PASA |
| BI-35 | La incertidumbre se guarda en el recorrido y se devuelve en el GET | `::test_recorrido_exterior_guarda_incertidumbre` | integración | PASA |
| BI-36 | Los recorridos interiores devuelven `uncertainty = null` | `::test_recorrido_interior_sin_incertidumbre` | integración | PASA |
| BI-37 | La API rechaza datos de señal imposibles (HTTP 422) | `::test_validacion_datos_senal` | integración | PASA |
| BF-09 | Fijar esquinas reduce la incertidumbre frente al recorrido continuo | `test_flujo_exterior.py::test_esquinas_fijadas_reducen_incertidumbre` | funcional | PASA |

## 4. Cobertura y pendientes

`pytest --cov`: total 89 %; `gps.py` 96 %, `gps_core.py` 96 %, `gps_precision.py` 96 %, `uncertainty.py` 95 %.

Migración `7d3e9a1f4b2c` verificada en PostgreSQL 16: `upgrade head` → `downgrade -1` → `upgrade head`.

Pendiente fuera de este alcance:
- App Android: enviar `vertex_id`, `satellites` y `cn0_dbhz`; botón "Fijar esquina"; intervalo GPS por transporte;
  advertencia en modo continuo de que caminar desplazado del lindero no se refleja en la incertidumbre.
- Validación con mediciones reales de campo (las pruebas usan recorridos simulados).
