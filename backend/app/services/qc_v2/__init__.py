"""QcPulse v2 — generación de casos QC en dos etapas.

Etapa A: modela los escenarios de prueba de una Technical Epic cruzando User Stories (CRN)
con Technical Stories (COV). Etapa B: diseña los casos de cada escenario aplicando la
"regla del bug". Etapa C (código): validación estructural y complejidad.

Se activa con QC_ENGINE=v2. El motor legacy sigue siendo el default.
"""

ENGINE_TAG = "qc-v2"
