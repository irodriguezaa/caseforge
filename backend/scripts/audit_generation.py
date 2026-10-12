"""Auditoría de generación de casos con Jira real (offline).

Uso (desde backend/):
    python scripts/audit_generation.py tests/fixtures/<fixture>.json [salida.json]
    (las EPCs se toman de los issues tipo Technical Epic del fixture)

- Replica la ruta de EPCs pegadas (pdf_bytes=None) sin llamar a Jira ni a OpenAI.
- Imprime métricas de calidad. Un motor sano debe dejar en 0 las métricas marcadas con (!).
"""
import collections, json, re, sys
sys.path.insert(0, ".")
from app.services import ai_case_engine as eng
from app.services import jira_generation as jg
from app.services.executability import is_user_action

GEN = "el usuario ingresa al flujo correspondiente"


def norm(s):
    return re.sub(r"\W+", " ", (s or "").lower()).strip()


def load(path):
    raw = json.load(open(path, encoding="utf-8"))["issues"]["nodes"]
    by = {i["key"]: i for i in raw}
    global EPCS
    EPCS = [i["key"] for i in raw if i["fields"]["issuetype"]["name"] == "Technical Epic"]
    arts = []
    for k in EPCS:
        a = jg._issue_payload(by[k])
        ch = sorted(
            (jg._issue_payload(i) for i in raw if (i["fields"].get("parent") or {}).get("key") == k),
            key=lambda c: c["key"],
        )
        a.update(children=ch, child_count=len(ch),
                 feature_child_count=sum(1 for c in ch if (c["summary"] or "").lower().startswith("feature")))
        arts.append(a)
    types = {i["key"]: i["fields"]["issuetype"]["name"] for i in raw}
    return arts, types, by


_FILLER = re.compile(r"^\s*(el usuario\s+)?(observar|confirmar|verificar|validar|revisar|comprobar)\b", re.I)
_IMPERATIVE = re.compile(r"^\s*(el usuario\s+)?\w+(ar|er|ir|a|e)\b", re.I)
_QUOTED = re.compile(r'["\u201c]([^"\u201d\n]{4,80})["\u201d]')


def jira_literals(arts):
    """Textos de UI entre comillas en las historias (excluye identificadores técnicos)."""
    lits = set()
    for a in arts:
        for c in a.get("children") or [a]:
            for m in _QUOTED.findall((c.get("description") or "") + "\n" + (c.get("acceptance_criteria") or "")):
                m = m.strip()
                if re.search(r"[/_{}#@\[\]]|^[a-z]+[A-Z]|^\w+$", m) and " " not in m:
                    continue
                if re.search(r"[/_{}\[\]]", m):
                    continue
                if re.match(r"id-\d+$", m, re.I):
                    continue
                if "." in m and " " not in m:
                    continue
                if re.fullmatch(r"<[^>]+>", m):
                    continue
                if " " not in m and len(m) >= 40:
                    continue
                lits.add(m)
    return lits


_NAV_VERB = re.compile(
    r"\b(abre|abrir|ingresa|ingresar|navega|navegar|selecciona|seleccionar)\b",
    re.I,
)
_WHEN_LINE = re.compile(r"(?im)^\s*(?:When|Cuando)\s+(.+)$")
_THEN_LINE = re.compile(r"(?im)^\s*(?:Then|Entonces)\s+(.+)$")
_GWT_LINE = re.compile(r"(?im)^\s*(?:Given|Dado que|Dado|When|Cuando)\s+(.+)$")
_SCENARIO_SPLIT = re.compile(r"(?im)^\s*(?:Scenario Outline|Scenario|Escenario)\s*:\s*(.+)$")
_QUOTE_MARK = re.compile(r'["“”]')
_NUMBERED_TITLE = re.compile(r"(?:—|-)\s*\d+\s*:|\b\d{1,2}\s*:")
_DANGLING_CONTEXT = re.compile(
    r"\b(de|del|para|por|con|en|a|al|el|la|los|las|un|una|y|o|que|su)\s*$",
    re.I,
)
_TECH_PRE = re.compile(
    r"\b(sdk|librer[ií]a|inicializ\w*|contexto\s+(?:t[eé]cnico|global)|"
    r"configuraci[oó]n\s+t[eé]cnica|feature\s*:)\b",
    re.I,
)
_VISIBLE_THEN = re.compile(r"\b(muestra|mostrar|pantalla|bot[oó]n|mensaje|men[uú]|modal|opci[oó]n)\b", re.I)
_EVENT_THEN = re.compile(r"\b(se emite|debe emitirse|evento)\b", re.I)
_STOP = {
    "el", "la", "los", "las", "un", "una", "que", "de", "del", "al", "a", "en", "y", "o",
    "con", "por", "para", "su", "sus", "usuario", "se", "es", "son",
}


def _odd_quotes(text: str) -> bool:
    for line in (text or "").splitlines() or [""]:
        if len(_QUOTE_MARK.findall(line)) % 2 == 1:
            return True
    return False


def _echoes_action(action: str, expected: str) -> bool:
    act = norm(action)
    exp = norm(expected).strip(" .")
    obj = re.sub(r"^(?:el usuario\s+)?[a-záéíóúñ]+(?:ar|er|ir)\s+", "", act).strip()
    obj = re.sub(r"^(?:el|la|los|las|un|una)\s+", "", obj).strip()
    if len(obj) < 3:
        return False
    shown = re.sub(r"^se muestra\s+(?:la opci[oó]n|el|la|los|las|un|una)\s+", "", exp).strip()
    return shown == obj


def _bare_show(expected: str) -> bool:
    return bool(re.fullmatch(r"se muestra (?:un|una) \S+\.?", norm(expected)))


def _story_blobs(arts) -> list[dict]:
    rows = []
    for epic in arts or []:
        for child in epic.get("children") or [epic]:
            key = str(child.get("key") or "").strip()
            blob = f"{child.get('description') or ''}\n{child.get('acceptance_criteria') or ''}"
            parts = _SCENARIO_SPLIT.split(blob)
            head = parts[0] if parts else blob
            nav = [norm(clause) for clause in _GWT_LINE.findall(head) if _NAV_VERB.search(clause)]
            feature = ""
            feat = re.search(r"(?im)^\s*Feature\s*:\s*(.+)$", head)
            if feat:
                feature = feat.group(1).strip()
            titles = parts[1::2]
            bodies = parts[2::2]
            scenarios = []
            for title, body in zip(titles, bodies):
                whens = _WHEN_LINE.findall(body or "")
                thens = _THEN_LINE.findall(body or "")
                system = bool(whens) and not any(is_user_action(clause) for clause in whens)
                visible = any(_VISIBLE_THEN.search(clause) and not _EVENT_THEN.search(clause) for clause in thens)
                scenarios.append({"title": title.strip(), "system": system and not visible})
            rows.append({
                "key": key,
                "summary": child.get("summary") or "",
                "feature": feature,
                "nav": nav,
                "scenarios": scenarios,
            })
    return rows


def _matches_nav(action: str, clauses: list[str]) -> bool:
    folded = norm(action)
    if not _NAV_VERB.search(folded):
        return False
    tokens = set(folded.split()) - _STOP
    for clause in clauses:
        needed = set(clause.split()) - _STOP
        needed = {token for token in needed if not _NAV_VERB.fullmatch(token)}
        if needed and len(needed & tokens) >= min(2, len(needed)):
            return True
    return False


def _matched_scenario(case, stories: list[dict]) -> dict | None:
    keys = {item.strip() for item in (case.related_jira or "").split("|") if item.strip()}
    name = re.sub(r"\s+—\s+.*$", "", norm(case.name))
    best = None
    best_len = 0
    for story in stories:
        if keys and story["key"] not in keys:
            continue
        for scenario in story["scenarios"]:
            title = norm(scenario["title"])
            if title and title in name and len(title) > best_len:
                best = {**scenario, "story": story}
                best_len = len(title)
    return best


def _r7_metrics(cases, arts) -> dict[str, int]:
    stories = _story_blobs(arts or [])
    by_key = {story["key"]: story for story in stories}
    counts = {
        "(R7) comillas sin cerrar": 0,
        "(R7) acción repetida en el mismo caso": 0,
        "(R7) navegación del Background después de una acción del escenario": 0,
        "(R7) resultado de relleno o Se muestra el resultado de": 0,
        "(R7) título con numeración o cortado": 0,
        "(R7) precondición técnica": 0,
        "(R7) caso ejecutable cuyo When es del sistema": 0,
    }
    for case in cases:
        visible = [case.name or "", case.precondition or ""]
        visible.extend(step.action or "" for step in case.steps)
        visible.extend(step.expected_result or "" for step in case.steps)
        if any(_odd_quotes(text) for text in visible):
            counts["(R7) comillas sin cerrar"] += 1
        actions = [norm(step.action) for step in case.steps if norm(step.action)]
        if len(actions) != len(set(actions)):
            counts["(R7) acción repetida en el mismo caso"] += 1
        keys = [item.strip() for item in (case.related_jira or "").split("|") if item.strip()]
        nav = []
        for key in keys:
            nav.extend((by_key.get(key) or {}).get("nav") or [])
        if nav and case.steps:
            flags = [_matches_nav(step.action or "", nav) for step in case.steps]
            if any(flags[index] and any(not earlier for earlier in flags[:index]) for index in range(len(flags))):
                counts["(R7) navegación del Background después de una acción del escenario"] += 1
        if any(
            re.search(r"se muestra el resultado de", step.expected_result or "", re.I)
            or _echoes_action(step.action or "", step.expected_result or "")
            or _bare_show(step.expected_result or "")
            for step in case.steps
        ):
            counts["(R7) resultado de relleno o Se muestra el resultado de"] += 1
        name = case.name or ""
        context = name.split(" — ", 1)[1] if " — " in name else ""
        if _NUMBERED_TITLE.search(name) or (context and _DANGLING_CONTEXT.search(context.strip())):
            counts["(R7) título con numeración o cortado"] += 1
        pre = case.precondition or ""
        technical_pre = bool(_TECH_PRE.search(pre))
        folded_pre = norm(pre)
        for key in keys:
            story = by_key.get(key) or {}
            for label in (story.get("summary") or "", story.get("feature") or ""):
                folded = norm(label)
                if len(folded.split()) >= 3 and folded in folded_pre:
                    technical_pre = True
        if technical_pre:
            counts["(R7) precondición técnica"] += 1
        if case.steps:
            matched = _matched_scenario(case, stories)
            if matched and matched["system"]:
                counts["(R7) caso ejecutable cuyo When es del sistema"] += 1
    return counts


def _stories_with_navigation(arts) -> set[str]:
    keys: set[str] = set()
    for epic in arts or []:
        children = epic.get("children") or [epic]
        for child in children:
            blob = f"{child.get('description') or ''}\n{child.get('acceptance_criteria') or ''}"
            head = re.split(r"(?im)^\s*(?:Scenario|Escenario)\b", blob, maxsplit=1)[0]
            if re.search(
                r"(?im)^\s*(?:Given|Dado que|Dado)\b.*\b(abre|abrir|ingresa|ingresar|navega|navegar|selecciona|seleccionar)\b",
                head,
            ):
                key = str(child.get("key") or "").strip()
                if key:
                    keys.add(key)
    return keys


def run(path):
    arts, types, by = load(path)
    eng.fetch_artifacts_for_keys = lambda keys: [a for a in arts if a["key"] in keys]
    r = eng.generate_release_app_candidates(
        release_id=1, release_name="audit", validation_type=None, analysis_present=True,
        rn_filename="", pdf_bytes=None, release_context={}, existing_cases=[],
        tickets={"functionality": [(k, by[k]["fields"]["summary"]) for k in EPCS]},
    )
    return r, types


def metrics(r, types, arts=None):
    C = r.candidates
    m = collections.Counter()
    per_epc = collections.Counter()
    stories = set()
    for c in C:
        epics = [e.strip() for e in (c.related_functionality or "").split("|") if e.strip()]
        per_epc[epics[0] if len(epics) == 1 else "MULTI"] += 1
        sts = [s.strip() for s in (c.related_jira or "").split("|") if s.strip()]
        stories.update(sts)
        acts = [norm(s.action) for s in c.steps]
        exps = [s.expected_result or "" for s in c.steps]
        blob = " ".join([c.name or "", c.precondition or "", c.test_data or ""] + [s.action + " " + (s.expected_result or "") for s in c.steps])
        pre = [norm(p) for p in (c.precondition or "").split(";") if p.strip()]
        m["(!) caso cruza EPCs"] += len(epics) > 1
        m["(!) caso generado desde Bug/Epic/otro"] += any(types.get(s) != "Technical Story" for s in sts)
        m["(!) todos los pasos genéricos"] += bool(acts) and all(a == GEN for a in acts)
        m["(!) acción repetida en pasos consecutivos"] += any(acts[i] == acts[i + 1] for i in range(len(acts) - 1))
        m["(!) esperado = acción del usuario"] += any(re.match(r"\s*(el )?usuario\b", e, re.I) for e in exps)
        m["(!) esperado = título"] += any(norm(e) == norm(c.name) for e in exps)
        m["(!) placeholder <x> sin sustituir"] += bool(re.search(r"<[A-Za-zÁ-ú_]+>", blob))
        m["(!) tabla vacía | a | b |"] += any(re.search(r"\|[^|]+\|[^|]+\|\s*$", e) for e in exps)
        m["(!) residuos markdown (``` / \"\"\" / __)"] += bool(re.search(r"```|\"\"\"|__", blob))
        m["(!) precondición con cláusula duplicada"] += len(pre) != len(set(pre))
        m["casos de 1 solo paso"] += len(c.steps) == 1
    nav_stories = _stories_with_navigation(arts or [])
    one_step_nav = 0
    for c in C:
        if len(c.steps) != 1:
            continue
        story_keys = [s.strip() for s in (c.related_jira or "").split("|") if s.strip()]
        if any(key in nav_stories for key in story_keys):
            one_step_nav += 1
    m["casos de 1 paso con navegación en la Feature"] = one_step_nav
    filler = 0
    for c in C:
        exps = [norm(s.expected_result) for s in c.steps]
        for i, s_ in enumerate(c.steps):
            if i and _FILLER.match(s_.action or "") and (exps[i] in exps[i - 1] or exps[i - 1] in exps[i] or len(set(exps[i].split()) - set(exps[i - 1].split())) <= 2):
                filler += 1
                break
    for c in C:
        m["(!) caso sin pasos"] += len(c.steps) == 0
        m["(!) resultado genérico (Se observa el comportamiento…)"] += any(re.search(r"se observa el comportamiento|comportamiento (definido|esperado)", s_.expected_result or "", re.I) for s_ in c.steps)
        m["(!) paso que es fila de tabla o medida (a: b: c / NNN x NNNpx)"] += any(re.search(r"\d+\s*x\s*\d+\s*px|:.*:.*:", s_.action or "", re.I) for s_ in c.steps)
        m["(!) precondición con 'Feature' o API"] += bool(re.search(r"Feature\b|API|servicio \"|response\.", c.precondition or ""))
    for c in C:
        m["(!) paso que no es acción del usuario (Given, título de escenario, regla)"] += any(
            not re.match(r"^\s*(el usuario\s+)?[a-záéíóúñ]+(ar|er|ir)\b", (s_.action or ""), re.I)
            or re.match(r"^\s*(el usuario\s+)?(est[aá]|se encuentra|tiene|cuenta con|desbloque[oó])\b", (s_.action or ""), re.I)
            for s_ in c.steps)
        m["(!) resultado con endpoint, status o llave técnica"] += any(
            re.search(r'"/[a-z]|/v\d/|status code|"\d{3}"|[A-Z][a-z]+_[A-Z][A-Za-z]+_', s_.expected_result or "") for s_ in c.steps)
        m["(!) datos de prueba con ruido del formato (id-n, smartlink, mention)"] += bool(re.search(r'"(id-\d+|smartlink|mention)"', c.test_data or ""))
        m["(!) título de más de 150 caracteres"] += len(c.name or "") > 150
    m["(!) caso con paso de relleno (Observar/Confirmar que repite el anterior)"] = filler
    names = collections.Counter(norm(c.name) for c in C)
    m["(!) casos con nombre duplicado"] = sum(v for v in names.values() if v > 1)
    missing = sorted(k for k, v in types.items() if v == "Technical Story" and k not in stories)
    print(f"engine={r.engine} coverage_units={r.coverage_unit_count} casos={len(C)} "
          f"pasos/caso={sum(len(c.steps) for c in C) / max(len(C), 1):.2f}")
    print("por EPC:", dict(per_epc))
    print("historias técnicas sin casos:", missing or "ninguna")
    for k, v in m.items():
        print(f"  {k}: {v} ({v * 100 // max(len(C), 1)}%)")
    for key, value in _r7_metrics(C, arts).items():
        print(f"  {key}: {value} ({value * 100 // max(len(C), 1)}%)")
    if arts is not None:
        lits = jira_literals(arts)
        # Solo título, acciones y resultados: los Datos de prueba NO cuentan (evita volcar textos ahí)
        blob = " ".join(" ".join([c.name or ""] + [s.action + " " + (s.expected_result or "") for s in c.steps]) for c in C).lower()
        kept = [l for l in lits if l.lower() in blob]
        print(f"  textos literales de UI de Jira conservados: {len(kept)}/{len(lits)} ({len(kept) * 100 // max(len(lits), 1)}%)")
    ledger = list((getattr(r, "generation_stats", None) and r.generation_stats.scenario_ledger) or [])
    if ledger:
        by_state = collections.Counter(row.get("estado") or "" for row in ledger)
        print("Escenarios de Jira:", dict(by_state), "total", len(ledger))
        covered = by_state.get("caso ejecutable", 0) + by_state.get("verificación técnica", 0)
        print(f"ejecutable + verificación técnica: {covered}")
        pending = [row for row in ledger if row.get("estado") == "pendiente de revisión QC"]
        print("pendientes QC:", len(pending), f"({len(pending) * 100 // max(len(ledger), 1)}%)")
        excluded = [row for row in ledger if row.get("estado") == "excluido"]
        print("excluido:", len(excluded), f"({len(excluded) * 100 // max(len(ledger), 1)}%)")
    details = list(getattr(r, "analysis_details", None) or [])
    for line in details:
        if "LLM" in line:
            print(line)
    batches = list((getattr(r, "generation_stats", None) and r.generation_stats.llm_batches) or [])
    if batches:
        sent = len(batches)
        ok = sum(1 for row in batches if row.get("ok"))
        print(f"LLM enviados={sent} aceptados={ok} tasa={ok * 100 // max(sent, 1)}%")
    return m, missing


if __name__ == "__main__":
    r, types = run(sys.argv[1])
    arts, _, _ = load(sys.argv[1])
    metrics(r, types, arts)
    if len(sys.argv) > 2:
        json.dump([c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in r.candidates],
                  open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
