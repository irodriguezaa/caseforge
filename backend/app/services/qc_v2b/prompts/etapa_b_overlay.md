REGLAS EXTRA DEL PAQUETE QC (v2-B). Se suman a las anteriores; si chocan, ganan estas.

PAQUETE: solo casos que QC ejecuta en el dispositivo, con cuentas reales, sin tocar configuración.
- HPP y ERG: sí.
- TTF: solo si el resultado es visible para el usuario (no se muestra, mensaje de error en pantalla). TTF de llaves: no.
- HPA (Atrás, cancelar, reintento, recargar, persistencia): no. No los diseñes.
- E2E de "la Home/pantalla no se rompe": no. Eso es regresión por componente.
- Si el caso describe el flujo esperado de un tipo de usuario (login → estado X, incluso replegado u oculto), es HPP, no TTF ni HPA.

GRANULARIDAD: un caso por comportamiento (tipo de usuario × estado/resultado visible).
- Fusiona en un solo caso lo que solo cambia la vía de entrada o un paso previo ("ya lo tiene" vs "lo acaba de adquirir") y deja esa diferencia como variante opcional.
- Conformidad visual: un solo ERG por pantalla/componente; los tipos de usuario van como variantes.
- No generes casos por volumen. El techo es el número de comportamientos distintos de las Technical Stories.

VARIANTES: máximo 3. Solo la operación principal (México), salvo que la historia pida explícitamente otras operaciones.
- Si la historia no es de pagos, no armes matriz de métodos de pago: una cuenta por tipo de usuario.
- Marca como opcional (prefijo "opcional: " en la condición) las variantes que exigen compra real o configuración especial.

PASOS: 3 a 6. No pongas en cada caso "recargar" ni "ir a otra sección y volver".

REDACCIÓN (misma regla que Legacy / scenario_cases):
- Perspectiva de usuario final. El tester actúa en el dispositivo y observa la pantalla.
- Resultado esperado: solo lo visible (qué aparece, desaparece, a dónde lleva, qué texto se ve).
- PROHIBIDO en el resultado esperado: llaves, APA/metadata, nombres de campo, payload, JSON, status code, API, endpoint, servicio, "se recupera del", logs, Figma, URLs técnicas.
- Si un Then mezcla algo visible con algo técnico, escribe solo lo visible; lo técnico va en referencia técnica o precondición de negocio.
- Sin rellenos: nada de "Se muestra el resultado de", "comportamiento definido", "funciona correctamente", "cambio en esa pantalla", "Abrir y presenta".
- Sin fragmentos técnicos sueltos (identificadores con punto, paths, `backticks`, enlaces de Figma).
- El primer paso lleva a la pantalla; el resultado de "Abrir X" es "Se muestra X", no un eco del título.

PRIORIDAD (no todo Critical):
- Blocker: flujo principal de la funcionalidad.
- Critical: reglas de negocio visibles (estados por tipo de usuario, ocultar/mostrar).
- Major: conformidad visual y complementos. Si el JSON no admite Major, usa Critical y pon "Major" al inicio del riesgo.

TÍTULO: "<Tipo de usuario> + <acción> + <resultado>". Completo, sin truncar, sin texto duplicado ni frases rotas.
Ejemplo: "Usuario externo registra y ve el Centro de Notificaciones desplegado".
