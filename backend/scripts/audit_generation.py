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
                lits.add(m)
    return lits


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
    filler = 0
    for c in C:
        exps = [norm(s.expected_result) for s in c.steps]
        for i, s_ in enumerate(c.steps):
            if i and _FILLER.match(s_.action or "") and (exps[i] in exps[i - 1] or exps[i - 1] in exps[i] or len(set(exps[i].split()) - set(exps[i - 1].split())) <= 2):
                filler += 1
                break
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
    if arts is not None:
        lits = jira_literals(arts)
        blob = " ".join(" ".join([c.name or "", c.precondition or "", c.test_data or ""] + [s.action + " " + (s.expected_result or "") for s in c.steps]) for c in C).lower()
        kept = [l for l in lits if l.lower() in blob]
        print(f"  textos literales de UI de Jira conservados: {len(kept)}/{len(lits)} ({len(kept) * 100 // max(len(lits), 1)}%)")
    return m, missing


if __name__ == "__main__":
    r, types = run(sys.argv[1])
    arts, _, _ = load(sys.argv[1])
    metrics(r, types, arts)
    if len(sys.argv) > 2:
        json.dump([c.model_dump() if hasattr(c, "model_dump") else c.dict() for c in r.candidates],
                  open(sys.argv[2], "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
