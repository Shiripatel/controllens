"""Test of Operating Effectiveness agent.

Steps: 1 Set context -> 2 Map attributes to test procedures -> 3 Decide test type
(code) -> 4 Build test plan from the locked sample (code) -> 5 Test each sample
item (AI, in batches) -> 6 Verify citations -> 7 Propose conclusion (code)."""
from ..models import Sample, Exception_
from ..sampling import determine_test_type
from . import prompts
from .common import control_block, evidence_block, validate_citations, find_line, CITATION_SCHEMA
from .llm import call_structured
from .runner import RunContext, StepFailed

BATCH = 8
NEGATIVE = ("not approved", "no approval", "missing", "rejected", "late", "after deploy",
            "exception", "fail", "not removed", "still active")

PROC_SCHEMA = {
    "type": "object",
    "properties": {"procedures": {"type": "array", "items": {
        "type": "object",
        "properties": {"attribute_id": {"type": "string"},
                       "test_steps": {"type": "array", "items": {"type": "string"}},
                       "pass_criteria": {"type": "string"}},
        "required": ["attribute_id", "test_steps", "pass_criteria"]}}},
    "required": ["procedures"],
}

TEST_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "sample_index": {"type": "integer"},
            "results": {"type": "array", "items": {
                "type": "object",
                "properties": {
                    "attribute_id": {"type": "string"},
                    "result": {"type": "string", "enum": ["pass", "fail", "unable_to_assess"]},
                    "citations": CITATION_SCHEMA,
                    "note": {"type": "string"}},
                "required": ["attribute_id", "result", "citations", "note"]}}},
        "required": ["sample_index", "results"]}}},
    "required": ["items"],
}


def _item_label(row: dict) -> str:
    vals = [str(v) for v in row.values() if str(v).strip()]
    return " / ".join(vals[:3])


def run(ctx: RunContext) -> dict:
    c = ctx.control
    db = ctx.db

    def set_context():
        if c.status not in ("design_reviewed", "operating_in_progress", "operating_prepared"):
            ctx.flags.append({"type": "design_not_reviewed", "where": "context",
                              "detail": "DE is not yet reviewed; OE results may need rework"})
        return {"control": f"{c.ref} {c.title}", "status": c.status,
                "evidence_files": [{"id": f"E{e.id}", "file": e.filename, "purpose": e.purpose}
                                   for e in ctx.evidence]}

    ctx.step("context", "Set context", set_context)

    def mock_proc():
        return {"procedures": [{"attribute_id": a["id"],
                                "test_steps": c.operating_procedures[-2:] or ["Inspect evidence for the sample item"],
                                "pass_criteria": f"Evidence shows: {a['text']}"} for a in c.attributes]}

    procs = ctx.step("procedures", "Map attributes to test procedures", lambda: call_structured(
        tool_name="record_operating_procedures", tool_description="Record OE test steps per attribute",
        schema=PROC_SCHEMA, system=prompts.OE_PROCEDURES,
        user=control_block(c) + "\n\nStandard Operating procedures:\n- " + "\n- ".join(c.operating_procedures),
        mock=mock_proc))

    test_type = ctx.step("test_type", "Decide test type", lambda: determine_test_type(c.nature, c.frequency))

    def plan():
        sample = (db.query(Sample).filter_by(control_id=c.id, active=True)
                  .order_by(Sample.id.desc()).first())
        if test_type["method"] == "test_of_one":
            items = sample.items if sample else [{"index": 1, "row": {"instance": "Current configuration"}}]
            return {"method": "test_of_one", "sample_id": sample.id if sample else None,
                    "items": items[:1], "note": "Test of one for automated control"}
        if not sample:
            raise StepFailed("No sample selected. Upload a population and generate a sample on the "
                             "Sampling tab, then run OE again.")
        return {"method": sample.method, "sample_id": sample.id, "seed": sample.seed,
                "population_size": sample.population_size, "sample_size": sample.sample_size,
                "rationale": sample.rationale, "items": sample.items}

    test_plan = ctx.step("test_plan", "Build test plan", plan)
    items = test_plan["items"]
    proc_txt = "\n".join(f"{p['attribute_id']}: {' | '.join(p['test_steps'])} (pass if: {p['pass_criteria']})"
                         for p in procs["procedures"])
    operating_evidence = [e for e in ctx.evidence if e.purpose != "population"] or ctx.evidence

    def mock_test(batch):
        out = []
        for it in batch:
            terms = [str(v).lower() for v in it["row"].values() if len(str(v).strip()) >= 3][:2]
            ev, line = find_line(operating_evidence, terms, prefer=("operating",)) if terms else (None, None)
            res = []
            for a in c.attributes:
                if not ev:
                    res.append({"attribute_id": a["id"], "result": "unable_to_assess", "citations": [],
                                "note": "[offline mock] No evidence found for this item"})
                else:
                    bad = any(n in line.lower() for n in NEGATIVE)
                    res.append({"attribute_id": a["id"], "result": "fail" if bad else "pass",
                                "citations": [{"evidence_id": f"E{ev.id}", "locator": "", "excerpt": line}],
                                "note": f"[offline mock] {'Exception indicated' if bad else 'Matched'} in {ev.filename}"})
            out.append({"sample_index": it["index"], "results": res})
        return {"items": out}

    def test_all():
        all_items = []
        for i in range(0, len(items), BATCH):
            batch = items[i:i + BATCH]
            sample_txt = "\n".join(f"Sample #{it['index']}: {it['row']}" for it in batch)
            r = call_structured(
                tool_name="record_operating_results", tool_description="Record OE results per sample item",
                schema=TEST_SCHEMA, system=prompts.OE_TEST,
                user=(f"{control_block(c)}\n\nTEST PROCEDURES:\n{proc_txt}\n\nSAMPLE ITEMS TO TEST:\n"
                      f"{sample_txt}\n\n{evidence_block(operating_evidence)}"),
                mock=lambda b=batch: mock_test(b))
            ctx.run.input_tokens += r.input_tokens
            ctx.run.output_tokens += r.output_tokens
            ctx.run.provider, ctx.run.model = r.provider, r.model
            all_items.extend(r.data["items"])
        return {"items": all_items}

    tested = ctx.step("test", f"Test {len(items)} sample item(s)", test_all)

    def check():
        labels = {it["index"]: _item_label(it["row"]) for it in items}
        returned = {t["sample_index"] for t in tested["items"]}
        for t in tested["items"]:
            t["label"] = labels.get(t["sample_index"], "")
            for r in t["results"]:
                where = f"#{t['sample_index']}/{r['attribute_id']}"
                r["citations"], flags = validate_citations(r.get("citations", []), ctx.evidence, where)
                ctx.flags.extend(flags)
                if r["result"] == "pass" and not any(x.get("verified") is not False for x in r["citations"]):
                    r["result"], r["downgraded"] = "unable_to_assess", True
                    ctx.flags.append({"type": "unsupported_conclusion", "where": where,
                                      "detail": "Pass without verified evidence; changed to unable_to_assess"})
        for missing in set(labels) - returned:
            ctx.flags.append({"type": "item_not_tested", "where": f"#{missing}",
                              "detail": "Agent did not return results for this sample item"})
        return {"flags": len(ctx.flags)}

    ctx.step("guardrails", "Verify evidence citations", check)

    def conclude():
        fails, unable = [], 0
        for t in tested["items"]:
            for r in t["results"]:
                if r["result"] == "fail":
                    fails.append((t, r))
                elif r["result"] == "unable_to_assess":
                    unable += 1
        # replace previous agent-raised open exceptions for this control
        db.query(Exception_).filter_by(control_id=c.id, source="operating_agent", status="open").delete()
        for t, r in fails:
            db.add(Exception_(control_id=c.id, sample_item=f"#{t['sample_index']} {t.get('label','')}"[:255],
                              attribute_id=r["attribute_id"], description=r["note"], source="operating_agent"))
        db.commit()
        failed_items = len({t["sample_index"] for t, _ in fails})
        if failed_items:
            concl = "not_operating_effectively"
        elif unable or ctx.flags and any(f["type"] == "item_not_tested" for f in ctx.flags):
            concl = "insufficient_evidence"
        else:
            concl = "operating_effectively"
        return {"operating": concl, "items_tested": len(items), "items_with_exceptions": failed_items,
                "attribute_checks_unable": unable,
                "basis": "Any exception means the control did not operate effectively for the period "
                         "unless the engagement team documents an acceptable explanation; "
                         "unassessed checks need more evidence."}

    proposed = ctx.step("conclude", "Propose conclusion", conclude)
    return {"procedures": procs, "test_type": test_type, "test_plan": test_plan,
            "results": tested, "proposed_conclusion": proposed}
