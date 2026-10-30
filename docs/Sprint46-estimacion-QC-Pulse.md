# Sprint 46 · cómo estima QC Pulse

**Filtro Jira:** 117859
**Jornada QC:** 6 h/día (capacidad neta de ejecución, no el turno completo)

La cifra de horas sale de los casos persistidos en cada **Release**, no del tablero de Sprint Testing.

---

## No confundir dos cosas

| Qué | Estado hoy en el portal |
|---|---|
| **Cómo se arman los casos** | Motor **legacy**. `QC_ENGINE` no está en `v2`. |
| **Cómo se calculan las horas** | Fórmula **nueva** (minutos por prioridad × complejidad). La de conteo `(casos ÷ 46) × 3 días` está retirada. |
| **QcPulse v2** (etapas A/B/C, tipos HPP/HPA/TTF/ERG/E2E) | Código listo. **No corre** al generar desde el portal hasta `QC_ENGINE=v2` + rebuild. |

Para el Sprint 46, los casos que genere el portal son **legacy**. Las horas que lea en la Release usan la tabla de minutos.

---

## 1. Cómo se arman los casos (hoy)

Default: `CASE_COMPOSITION_MODE=scenario` → **un caso QC por cada Scenario de Jira**.

1. **RN + Jira** — Analiza el Release Note, ata Technical Epics y baja stories / Gherkin. Sale un inventario de cobertura.
2. **Composición** — Materializa 1 caso por Scenario (Given/When/Then → acción / resultado esperado). Determinista; no hay etapas A/B/C.
3. **Complejidad** — La pone el código según la forma del caso, no según la prioridad:
   - **BAJA:** validación básica de 1 paso, o 1 paso con confianza alta.
   - **MEDIA:** condición especial, 2–3 pasos, o confianza media.
   - **ALTA:** 4+ pasos o confianza baja.
4. **Matriz** — Según alcance (Smoke, Acotadas, Regresión…). Casos de catálogo; **no** entran a la suma de minutos del RN.

BLOCKER vs CRITICAL **no** define complejidad: solo elige la fila de minutos.

---

## 2. Cómo se calcula el esfuerzo (vigente)

Vale para cualquier caso ya guardado.

### Release Apps

| Prioridad | BAJA | MEDIA | ALTA |
|---|---|---|---|
| CRITICAL | 10 min | 15 min | 20 min |
| BLOCKER | 15 min | 25 min | 35 min |

- Horas de casos = suma de minutos ÷ 60.
- Se **suma el alcance** de validación (si hay rango, entra el **tope**):
  - Pruebas Acotadas: 2 h
  - Smoke Test: 3 h
  - Regresivo / No afectación: 4 h
  - Regresión completa: 8 h
  - N/A: 0 h
- Días-persona = horas totales ÷ **6**.
- Duración = días-persona ÷ recursos QC.
- La ventana inicio/fin es **calendario**; no entra en esta cuenta.

### Operativa

- 1 tester por dispositivo, 6 casos/día.
- Horas = N casos × 1 h.
- Días = casos del dispositivo más cargado ÷ 6 (trabajo en paralelo).

### Release BE

- No depende del número de casos.
- Smoke 3 h · Acotadas 2 h · Regresión completa 8 h · N/A 0.
- Días QC = esas horas ÷ 6.

---

## 3. Cómo armar la cifra del Sprint 46

1. Sprint Testing → Sprint 46 (filtro 117859): ver EPCs y programas en alcance.
2. Crear o abrir cada Release Apps / BE / OPE del Sprint. Un estimado por frente; **no mezclar fórmulas**.
3. Analizar RN y generar casos (motor legacy) o adjuntar matriz. Sin casos, Apps no tiene horas de RN.
4. Leer **Esfuerzo estimado QC** y **Duración estimada**. Sumar las **horas** de todos los frentes.
5. Filtros y recursos: el filtro de la tabla cambia el número; más testers acortan **duración**, no las horas.

**Jornada:** no subir la fórmula a 8 h. Reportar horas QC Pulse y traducir a días con 6 h. Operativa, ambiente y juntas van fuera de esas 6 h.
