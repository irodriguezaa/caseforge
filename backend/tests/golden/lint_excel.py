"""Revisión de calidad de cualquier Excel generado (no necesita set dorado).

Uso:  python lint_excel.py generado.xlsx [--max-un-paso 0.4]
Sale con código 1 si encuentra errores. Las reglas son generales: no mencionan
tickets, dispositivos ni pantallas.
"""
import sys, re, collections, openpyxl

path = sys.argv[1]
MAX_ONE_STEP = float(sys.argv[sys.argv.index('--max-un-paso') + 1]) if '--max-un-paso' in sys.argv else 0.4
wb = openpyxl.load_workbook(path, read_only=True)
H = [c.value for c in next(wb['Test Cases'].iter_rows(max_row=1))]
ix = {h: i for i, h in enumerate(H)}
rows = [r for r in wb['Test Cases'].iter_rows(min_row=2, values_only=True) if r[0]]
epc = [r for r in rows if r[ix['Issue Type']] != 'qc_matrix']
matrix = [r for r in rows if r[ix['Issue Type']] == 'qc_matrix']

TECH = re.compile(r'\b(servicio|API|llamad[oa]|petici[oó]n|invoca|endpoint|request|metadata|valor recibido|'
                  r'llave de configuraci[oó]n|se recupera del|log|evento [a-z]+\.[a-z]+)\b', re.I)
PH = re.compile(r'<[^>]{0,40}>|@\w+|\[#\]|Valor <')
GEN = re.compile(r'Se muestra el resultado de|comportamiento definido|cambio en esa pantalla|Abrir y presenta', re.I)

def steps(r): return [s for s in (r[ix['Test Steps']] or '').split('\n') if s.strip()]
def strip_num(s): return re.sub(r'^\s*\d+\.\s*', '', s or '').strip().lower()

err = collections.defaultdict(list)
dup = collections.Counter((r[ix['Technical Story']], r[ix['Nombre']]) for r in epc)
sig = collections.Counter((r[ix['Technical Story']], r[ix['Test Steps']], r[ix['Resultado Esperado']]) for r in epc)
for r in epc:
    cid, name, exp = r[0], r[ix['Nombre']], r[ix['Resultado Esperado']] or ''
    txt = (r[ix['Test Steps']] or '') + '\n' + exp
    if dup[(r[ix['Technical Story']], name)] > 1: err['duplicado (mismo nombre e historia)'].append(cid)
    elif sig[(r[ix['Technical Story']], r[ix['Test Steps']], exp)] > 1: err['duplicado (mismos pasos y resultado)'].append(cid)
    if strip_num(exp.split('\n')[0])[:40] == (name or '').lower()[:40]: err['resultado esperado = título'].append(cid)
    if PH.search(txt): err['placeholder sin resolver'].append(cid)
    if TECH.search(txt): err['cláusula técnica en el caso'].append(cid)
    if GEN.search(txt): err['paso o resultado genérico'].append(cid)
    if len(steps(r)) != len([x for x in exp.split('\n') if x.strip()]): err['pasos y resultados no cuadran'].append(cid)

one = sum(len(steps(r)) == 1 for r in epc)
print(f'Casos de EPC: {len(epc)} · matriz regresiva: {len(matrix)} · un solo paso: {one} ({one/max(len(epc),1):.0%})')
fail = False
if not matrix: print('  ADVERTENCIA: no hay casos de matriz regresiva (¿se perdió el alcance regresivo?)')
if one / max(len(epc), 1) > MAX_ONE_STEP:
    print(f'  ERROR: más del {MAX_ONE_STEP:.0%} de los casos tiene un solo paso'); fail = True
for k, v in sorted(err.items(), key=lambda x: -len(x[1])):
    print(f'  ERROR {k}: {len(v)}  ej. {", ".join(v[:8])}'); fail = True
sc = [r for r in wb['Escenarios de Jira'].iter_rows(min_row=2, values_only=True) if r[0]]
llm = [r for r in sc if 'LLM' in str(r[4] or '') or '429' in str(r[4] or '')]
if llm: print(f'  ERROR errores de IA guardados como motivo: {len(llm)}'); fail = True
print('RESULTADO:', 'FALLA' if fail else 'OK')
sys.exit(1 if fail else 0)
