# Casos de uso de MetriK

Este documento amplía los casos de uso del documento de requerimientos del proyecto.
Los casos CU-01 a CU-06 ya están implementados. Los casos CU-07 a CU-10 y la mejora de precisión
GPS se definieron el 2026-11-10 con aportes de ingeniería electrónica (sensores) e ingeniería civil
(uso en obra y tolerancias).

## 1. Resumen

| ID | Caso de uso | Actor principal | Estado |
|----|-------------|-----------------|--------|
| CU-01 | Levantar plano de un ambiente (interior) | Usuario medidor | Implementado |
| CU-02 | Medir perímetro y área de un terreno (exterior, GPS) | Usuario medidor | Implementado; se mejora con RF-18 a RF-21 |
| CU-03 | Revisar y suavizar el esbozo | Usuario medidor | Implementado |
| CU-04 | Exportar plano a escala en DXF | Usuario medidor | Implementado |
| CU-05 | Medir sobre un plano a escala importado | Usuario medidor | Implementado |
| CU-06 | Registrar medidas reales y consultar margen de error | Analista | Implementado |
| CU-07 | Metrado y presupuesto de un ambiente | Contratista / residente de obra | Nuevo |
| CU-08 | Plano de vivienda con varios ambientes | Arquitecto / tasador / propietario | Nuevo |
| CU-09 | Cerco perimétrico de un terreno | Propietario rural / contratista / tasador | Nuevo |
| CU-10 | Informe técnico de la medición | Perito / tasador / ingeniero verificador | Nuevo |

## 2. Requisitos funcionales nuevos

| ID | Requisito | Prioridad | Caso de uso |
|----|-----------|-----------|-------------|
| RF-18 | **Esquinas fijadas (stop-and-go):** en modo exterior, el usuario se detiene 20–60 s en cada esquina; las lecturas de esa espera se promedian (ponderadas por 1/σ², descartando las que se alejan más de 2σ) para obtener el vértice. | Alta | CU-02, CU-09 |
| RF-19 | **Cierre del recorrido GPS:** al final, el usuario vuelve a fijar la primera esquina; la distancia entre las dos fijaciones es el estimador real del error del recorrido. | Alta | CU-02, CU-09 |
| RF-20 | **Filtro por calidad de señal:** descartar lecturas con menos de 6 satélites usados o con señal media (C/N0) menor a 30 dB-Hz, cuando la app los envía. | Alta | CU-02 |
| RF-21 | **Incertidumbre del área y del perímetro:** informar siempre el área y el perímetro con su incertidumbre expandida al 95 % (k = 2), en unidades y en porcentaje. | Alta | CU-02, CU-09, CU-10 |
| RF-22 | **Metrado de acabados:** a partir del plano, la altura y los vanos (puertas y ventanas), calcular piso, cielo raso, muro neto (tarrajeo, pintura) y contrazócalo, con desperdicio configurable. | Alta | CU-07 |
| RF-23 | **Catálogo de precios:** precios de materiales obtenidos de tiendas por scraping (una vez al día, con fuente y fecha); el usuario puede reemplazar cualquier precio. | Media | CU-07, CU-09 |
| RF-24 | **Presupuesto:** costo directo, gastos generales, utilidad e IGV; exportación a PDF y Excel. | Alta | CU-07, CU-09 |
| RF-25 | **Unión de ambientes:** unir recorridos por un muro compartido con su espesor (transformación rígida) y advertir muros de largo distinto, superposiciones y esquinas fuera de escuadra (> 2°). | Media | CU-08 |
| RF-26 | **Plano de vivienda:** exportar un DXF único con todos los ambientes, sus nombres y el cuadro de áreas. | Media | CU-08 |
| RF-27 | **Metrado de cerco:** calcular postes según la separación, metros de alambre o m² de muro y portones, y recomendar un rango de compra según la incertidumbre del perímetro. | Alta | CU-09 |
| RF-28 | **Informe técnico PDF:** plano a escala, método, error de cierre, MAE/RMSE frente a wincha, incertidumbre del área y coordenadas. | Alta | CU-10 |

## 3. Especificación de los casos de uso nuevos

### CU-07 — Metrado y presupuesto de un ambiente

- **Actor:** contratista o residente de obra.
- **Precondición:** el ambiente fue medido (CU-01) y el plano está cerrado.
- **Flujo principal:**
  1. El usuario abre el plano y elige "Metrado".
  2. Ingresa la altura del ambiente.
  3. Toca un muro y registra sus vanos (tipo, ancho y alto).
  4. Elige las partidas: piso, cielo raso, tarrajeo, pintura y contrazócalo.
  5. El sistema calcula el metrado de cada partida, con su desperdicio.
  6. El sistema propone el precio unitario de cada partida desde el catálogo (fuente y fecha visibles).
  7. El usuario ajusta precios, gastos generales y utilidad.
  8. El sistema calcula el presupuesto con IGV y lo exporta a PDF o Excel.
- **Excepciones:**
  - EX-08: un vano más ancho que su muro o más alto que el ambiente → se rechaza con un mensaje.
  - EX-09: el catálogo de precios no está disponible → se usa el último precio guardado y se indica su fecha.

### CU-08 — Plano de vivienda con varios ambientes

- **Actor:** arquitecto, tasador o propietario.
- **Precondición:** el proyecto tiene al menos dos ambientes medidos.
- **Flujo principal:**
  1. El usuario crea una "Planta de vivienda" en el proyecto y elige el ambiente base.
  2. Elige un muro del ambiente base y el muro del otro ambiente que comparten, y el espesor del muro.
  3. El sistema ubica el segundo ambiente pegado al primero (rotación y traslación).
  4. Repite con los demás ambientes.
  5. El sistema muestra advertencias de calidad y el cuadro de áreas.
  6. El usuario exporta el DXF de la planta completa.
- **Excepciones:**
  - EX-10: los muros unidos difieren en más de 10 cm → advertencia de esquina mal marcada.
  - EX-11: dos ambientes se superponen → advertencia y no se exporta hasta corregir.

### CU-09 — Cerco perimétrico de un terreno

- **Actor:** propietario rural, contratista o tasador.
- **Precondición:** el terreno se recorrió con GPS fijando las esquinas (RF-18, RF-19).
- **Flujo principal:**
  1. El usuario elige el tipo de cerco: postes con alambre o muro de ladrillo.
  2. Ingresa la separación entre postes, el número de hilos (o la altura del muro) y los portones.
  3. El sistema calcula el metrado por lado y el total.
  4. El sistema muestra el rango de compra según la incertidumbre del perímetro.
  5. El sistema genera el presupuesto (RF-24) y el DXF del terreno.
- **Excepciones:**
  - EX-12: la incertidumbre del perímetro supera el 5 % → se advierte que conviene volver a medir con más tiempo en cada esquina.

### CU-10 — Informe técnico de la medición

- **Actor:** perito, tasador o ingeniero verificador.
- **Precondición:** el recorrido existe; opcionalmente tiene validación con wincha o referencia.
- **Flujo principal:**
  1. El usuario elige "Informe técnico" en el plano.
  2. El sistema arma el PDF: datos del proyecto, plano a escala, método de medición, error de
     cierre, incertidumbre del área, MAE/RMSE frente a wincha (si existe) y coordenadas (si es GPS).
  3. El usuario descarga o comparte el informe.
- **Excepciones:**
  - EX-13: el recorrido no tiene validación → el informe lo indica explícitamente ("sin validación de campo").

## 4. Alcance de la precisión GPS

Con un celular de una sola frecuencia (por ejemplo, Samsung A25) el límite realista es de 1 a 2 m
por vértice fijado. La incertidumbre del área sigue la propagación de errores sobre la fórmula de
Shoelace:

σ_A² = ¼ Σ σᵢ² · dᵢ²

donde σᵢ es la desviación estándar por eje del vértice i y dᵢ la distancia entre sus vértices vecinos
(i − 1 e i + 1). Se informa U = 2σ_A (95 %).

| Uso | ¿Es suficiente el GPS del celular? |
|-----|-----------------------------------|
| Terrenos de más de ~3 000 m² (error de área < 5 %) | Sí |
| Ubicar y georreferenciar el predio | Sí |
| Cerco perimétrico de terrenos grandes | Sí |
| Lotes urbanos de menos de 500 m² | No: el resultado es solo referencial |
| Linderos, trámites registrales, metrados | No: requieren estación total o GNSS RTK |

Quedan como trabajo futuro: fusión GPS + IMU (filtro de Kalman extendido), mediciones GNSS crudas con
corrección diferencial (RTKLIB) y receptor RTK externo por Bluetooth.
