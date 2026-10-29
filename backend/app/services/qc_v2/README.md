# QcPulse v2 — generación de casos QC en dos etapas

Rama: `feat/qc-v2`. El motor actual (legacy) sigue siendo el default; la v2 se activa por configuración.

## Cómo funciona

| Etapa | Qué hace | Quién |
|---|---|---|
| 0. Recolección | Technical Stories de la épica (cada `Scenario` = COV, el Background es contexto). User Stories por la ruta Technical Epic → Technical Brief → Product Brief → Product Epic (mismo título que el Technical Brief) → User Story; cada criterio numerado de `customfield_19114` = CRN | Código |
| A. Modelado | Una llamada por épica: escenarios de prueba, cruce CRN/COV, brechas (solo negocio / solo técnico / implícito), exclusiones con motivo | IA |
| B. Diseño | Una llamada por escenario, en paralelo: casos con la **regla del bug** (dos verificaciones van juntas si al fallar serían un solo bug) | IA |
| C. Validación | Estructural (3–6 pasos, sin campos ni comillas vacías) y complejidad determinista. **Ningún caso se descarta**: se marca "requiere revisión" | Código |

Prompts versionados: `prompts/etapa_a.md`, `prompts/etapa_b.md`.

## Configuración (`.env`)

```
QC_ENGINE=v2                    # legacy | v2 | v2b (solo afecta la generación desde el portal)
OPENAI_QC_MODEL=gpt-5.6-sol     # o OPENAI_QC_MODEL_A / OPENAI_QC_MODEL_B por etapa
OPENAI_QC_TEMPERATURE=0.25      # vacío = sin temperature (algunos modelos no la aceptan; se reintenta solo)
QC_V2_CONCURRENCY=5
QC_V2_TIMEOUT=240
```

## Uso

```bash
./scripts/qcv2.sh build                                  # una vez, tras cada cambio de código
./scripts/qcv2.sh run WEB WEBCL-2060 WEBCL-1586          # → exports/qcv2/qcv2_WEB_<fecha>.xlsx y .json
./scripts/qcv2.sh bench exports/benchmark/Luminia_WEB_5EPCs.xlsx exports/qcv2/qcv2_WEB_<fecha>.xlsx --judge
./scripts/qcv2.sh test
```

El `run` no toca la base de datos. El Excel trae: **Resumen** (CRN, COV, escenarios, casos, llamadas, tokens, tiempo, avisos), **Escenarios**, **Casos** y **Cruce** (brechas en amarillo, errores en rojo).

Desde el portal: `QC_ENGINE=v2` en `.env` y `docker compose up -d --build`. Los casos se guardan como siempre; el Excel de la Release agrega las columnas Escenario, Tipo de prueba, Brecha y Requiere revisión (solo si hay casos v2). La hoja Zephyr no cambia.

## Criterio de liberación (benchmark)

| Métrica | Meta |
|---|---|
| Cobertura de las verificaciones de Luminia (juez IA) | ≥ 90 % |
| Granularidad (casos QcPulse ÷ Luminia) | 40 % – 60 % |
| Casos con 3 a 6 pasos | ≥ 90 % |
| Pasos de Desarrollo | 0 |
| Duplicados (mismo bug) | 0 |

Si una meta falla en una sola épica, primero revisar si es el contenido de Jira antes de tocar los prompts.

## Regresar al motor actual

`QC_ENGINE=legacy` (o quitar la línea) y `docker compose up -d --build`. No hace falta revert.
