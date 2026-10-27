# Set dorado de generación QC

`aaf_legacy_release47.json` = resultado esperado para AAFCL-1919, 1940, 1971, 1987 (AAF Legacy, Release 47).

- `casos`: 15 casos esperados. Cada uno lista los escenarios de Jira (`historia` + `escenario`) que debe cubrir.
  `tipo: impacto` = EPC técnica que afecta lo que el usuario ve (un caso por superficie, no por escenario).
- `no_generan_caso`: 78 escenarios que NO deben ser caso, con el criterio del filtro positivo que fallan
  (`actor`, `superficie`, `verificacion_en_dispositivo`). Se acepta `verificación técnica` o `pendiente de revisión QC`.

## Cómo se compara (no por conteo)
- faltante: caso dorado sin ningún caso generado que cubra alguno de sus escenarios.
- de más: caso generado que solo cubre escenarios de `no_generan_caso`.
- fragmentado: un caso dorado repartido en 2+ casos generados (viola la regla del bug).
- mal clasificado: escenario de `no_generan_caso` que salió como caso ejecutable.
- fusionado: un caso generado que cubre 2+ casos dorados (solo advertencia).

Coincidir en número (2/6/7/0) NO basta: hay que cubrir los escenarios correctos.

## Uso
    python compare_golden.py aaf_legacy_release47.json <excel_generado.xlsx>
Sale con código 1 si hay faltantes, de más, fragmentados o mal clasificados. Envolverlo en un test de pytest
que genere las 4 EPC con el motor y llame al comparador.

## Regla
Un cambio que mejora un fixture y empeora otro no se acepta. Agregar fixtures de otros dispositivos
(tvOS, WEB, ADR) para que las reglas no queden cargadas a AAF.
