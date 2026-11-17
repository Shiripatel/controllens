"""Design & Implementation agent.

Steps: 1 Set context -> 2 Map risk to attributes -> 3 Map attributes to procedures
-> 4 Map procedures to evidence & evaluate -> 5 Check citations (guardrail)
-> 6 Roll up proposed conclusion (deterministic)."""
from . import prompts
from .common import (control_block, evidence_block, validate_citations, keywords, find_line,
                     CITATION_SCHEMA)
from .llm import call_structured
from .runner import RunContext, StepFailed

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "attributes": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "attribute_id": {"type": "string"},
                "addresses_risk": {"type": "string"},
                "procedures": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["attribute_id", "addresses_risk", "procedures"]}},
        "suggested_additional_attributes": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["attributes"],
}

EVAL_SCHEMA = {
    "type": "object",
    "properties": {
        "attribute_results": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "attribute_id": {"type": "string"},
                "design_assessment": {"type": "string", "enum": ["adequate", "inadequate", "unable_to_assess"]},
                "implemented": {"type": "string", "enum": ["yes", "no", "unable_to_assess"]},
                "procedure_evidence_map": {"type": "array", "items": {
                    "type": "object",
                    "properties": {"procedure": {"type": "string"},
                                   "evidence_ids": {"type": "array", "items": {"type": "string"}}},
                    "required": ["procedure", "evidence_ids"]}},
                "citations": CITATION_SCHEMA,
                "reasoning": {"type": "string"},
            },
            "required": ["attribute_id", "design_assessment", "implemented", "citations", "reasoning"]}},
        "gaps": {"type": "array", "items": {"type": "string"}},
        "evidence_requests": {"type": "array", "items": {"type": "string"}},
        "summary": {"type": "string"},
    },
    "required": ["attribute_results", "summary"],
}


def run(ctx: RunContext) -> dict:
    c = ctx.control

    def set_context():
        if not c.attributes:
            raise StepFailed("Control has no attributes. Add attributes before running D&I.")
        return {
            "control": f"{c.ref} {c.title}",
            "system": c.system.name if c.system else None,
            "attributes": len(c.attributes),
            "evidence_files": [{"id": f"E{e.id}", "file": e.filename, "purpose": e.purpose,
                                "readable": bool(e.extracted_text)} for e in ctx.evidence],
            "warnings": ([] if ctx.evidence else ["No evidence uploaded - results will be 'unable to assess'"]),
        }

    ctx.step("context", "Set context", set_context)

    # --- Steps 2+3: plan
    def mock_plan():
        return {"attributes": [
            {"attribute_id": a["id"],
             "addresses_risk": f"Helps prevent: {c.risk[:120]}",
             "procedures": c.dni_procedures[:2] or ["Inspect supporting documentation"]}
            for a in c.attributes], "suggested_additional_attributes": []}

    plan = ctx.step("plan", "Map risk to attributes and procedures", lambda: call_structured(
        tool_name="record_dni_plan", tool_description="Record the D&I plan",
        schema=PLAN_SCHEMA, system=prompts.DNI_PLAN,
        user=control_block(c) + "\n\nStandard D&I procedures:\n- " + "\n- ".join(c.dni_procedures),
        mock=mock_plan))

    # --- Step 4: evaluate against evidence
    def mock_eval():
        results = []
        for a in c.attributes:
            ev, line = find_line(ctx.evidence, keywords(a["text"]), prefer=("design", "general"))
            if ev:
                results.append({"attribute_id": a["id"], "design_assessment": "adequate",
                                "implemented": "yes",
                                "procedure_evidence_map": [{"procedure": p, "evidence_ids": [f"E{ev.id}"]}
                                                           for p in c.dni_procedures[:1]],
                                "citations": [{"evidence_id": f"E{ev.id}", "locator": "", "excerpt": line}],
                                "reasoning": f"[offline mock] {ev.filename} contains text matching this attribute."})
            else:
                results.append({"attribute_id": a["id"], "design_assessment": "unable_to_assess",
                                "implemented": "unable_to_assess", "procedure_evidence_map": [],
                                "citations": [], "reasoning": "[offline mock] No matching evidence found."})
        gaps = [f"{r['attribute_id']}: no supporting evidence" for r in results if not r["citations"]]
        return {"attribute_results": results, "gaps": gaps,
                "evidence_requests": [f"Provide: {x}" for x in c.expected_evidence] if gaps else [],
                "summary": "[offline mock] Keyword-based evaluation. Set CL_ANTHROPIC_API_KEY for AI evaluation."}

    plan_txt = "\n".join(f"{p['attribute_id']}: {'; '.join(p['procedures'])}" for p in plan["attributes"])
    evaluation = ctx.step("evaluate", "Map procedures to evidence and evaluate", lambda: call_structured(
        tool_name="record_dni_evaluation", tool_description="Record D&I evaluation per attribute",
        schema=EVAL_SCHEMA, system=prompts.DNI_EVALUATE,
        user=f"{control_block(c)}\n\nPLAN:\n{plan_txt}\n\n{evidence_block(ctx.evidence)}",
        mock=mock_eval))

    # --- Step 5: guardrail - verify citations, downgrade unsupported claims
    def check():
        known = {a["id"] for a in c.attributes}
        seen = set()
        for r in evaluation["attribute_results"]:
            seen.add(r["attribute_id"])
            r["citations"], flags = validate_citations(r.get("citations", []), ctx.evidence,
                                                       r["attribute_id"])
            ctx.flags.extend(flags)
            supported = any(cit.get("verified") is not False for cit in r["citations"])
            if r["design_assessment"] == "adequate" and not supported:
                r["design_assessment"] = "unable_to_assess"
                r["downgraded"] = True
                ctx.flags.append({"type": "unsupported_conclusion", "where": r["attribute_id"],
                                  "detail": "Marked adequate without verified evidence; changed to unable_to_assess"})
            if r["implemented"] == "yes" and not supported:
                r["implemented"] = "unable_to_assess"
                r["downgraded"] = True
        for missing in known - seen:
            ctx.flags.append({"type": "attribute_not_evaluated", "where": missing,
                              "detail": "Agent did not return a result for this attribute"})
            evaluation["attribute_results"].append({
                "attribute_id": missing, "design_assessment": "unable_to_assess",
                "implemented": "unable_to_assess", "citations": [], "reasoning": "Not evaluated by agent"})
        return {"flags": ctx.flags, "attributes_checked": len(seen)}

    ctx.step("guardrails", "Verify evidence citations", check)

    # --- Step 6: deterministic roll-up
    def conclude():
        rs = evaluation["attribute_results"]
        design = [r["design_assessment"] for r in rs]
        impl = [r["implemented"] for r in rs]
        if "inadequate" in design:
            d = "not_effective"
        elif "unable_to_assess" in design:
            d = "insufficient_evidence"
        else:
            d = "effective"
        if "no" in impl:
            i = "not_implemented"
        elif "unable_to_assess" in impl:
            i = "insufficient_evidence"
        else:
            i = "implemented"
        return {"design": d, "implementation": i,
                "basis": "All attributes must be adequate and implemented; any inadequate attribute "
                         "fails design; any unassessed attribute means more evidence is needed."}

    proposed = ctx.step("conclude", "Propose conclusion", conclude)
    return {"plan": plan, "evaluation": evaluation, "proposed_conclusion": proposed}
