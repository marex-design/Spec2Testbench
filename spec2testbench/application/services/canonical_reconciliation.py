from __future__ import annotations

from typing import Any, Iterable, Mapping


def normalize_case_compliance(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"PASS", "COMPLIANT"}:
        return "COMPLIANT"
    if text in {"FAIL", "NONCOMPLIANT"}:
        return "NONCOMPLIANT"
    return "NOT_EVALUATED"


def summarize_nominal_rows(
    rows: Iterable[Mapping[str, Any]],
    *,
    status_field: str = "reconciled_compliance",
) -> dict[str, Any]:
    materialized = list(rows)
    compliant = 0
    noncompliant = 0
    not_evaluated = 0
    changed_case_ids: list[str] = []

    for row in materialized:
        status = normalize_case_compliance(row.get(status_field))
        if status == "COMPLIANT":
            compliant += 1
        elif status == "NONCOMPLIANT":
            noncompliant += 1
        else:
            not_evaluated += 1

        historical = normalize_case_compliance(row.get("historical_compliance"))
        reconciled = normalize_case_compliance(row.get(status_field))
        case_id = str(row.get("case_id", "")).strip()
        if case_id and historical != reconciled:
            changed_case_ids.append(case_id)

    total = compliant + noncompliant + not_evaluated
    return {
        "compliant": compliant,
        "noncompliant": noncompliant,
        "not_evaluated": not_evaluated,
        "total": total,
        "changed_case_ids": changed_case_ids,
        "internally_consistent": total == len(materialized),
        "recomputed_from_rows": True,
    }


def legacy_effectiveness_reason(label: str) -> str:
    normalized = str(label or "").strip().upper()
    if normalized == "EFFECTIVE_NO_THRESHOLD_CROSSING":
        return "Legacy taxonomy treated a measurable metric shift as effective even when the mutated case stayed on the same side of the threshold."
    if normalized == "NO_MEASURABLE_EFFECT":
        return "Legacy taxonomy used a dedicated label when the mutated metric looked unchanged or numerically negligible."
    if normalized == "EFFECTIVE_THRESHOLD_CROSSED":
        return "Legacy taxonomy marked the mutation effective because the mutated case crossed the specification threshold."
    if normalized == "NOT_EVALUATED":
        return "Legacy taxonomy could not assign an effectiveness label because the target metric was not evaluated."
    if normalized == "SIMULATION_FAILURE":
        return "Legacy taxonomy could not assign an effectiveness label because the replay failed."
    return "Legacy taxonomy label carried no additional semantics beyond the recorded status."


def current_effectiveness_reason(
    label: str,
    *,
    reference_compliance: Any,
    mutated_compliance: Any,
) -> str:
    normalized = str(label or "").strip().upper()
    reference = normalize_case_compliance(reference_compliance)
    mutated = normalize_case_compliance(mutated_compliance)
    if normalized == "INEFFECTIVE_MUTATION":
        return (
            "Current taxonomy is compliance-based: the mutation is ineffective because the reference and mutated cases "
            f"remain {reference.lower()} and {mutated.lower()} with no violation introduced."
        )
    if normalized == "EFFECTIVE_VIOLATION":
        return "Current taxonomy marks the mutation effective because the mutated case violates the specification under corrected semantics."
    if normalized == "INVALID_REFERENCE_CASE":
        return "Current taxonomy rejects the mutation because the corrected nominal reference case is not compliant."
    if normalized == "NOT_EVALUATED":
        return "Current taxonomy leaves the mutation unevaluated because the corrected replay did not yield a usable metric."
    if normalized == "SIMULATION_FAILURE":
        return "Current taxonomy leaves the mutation unresolved because the corrected replay failed."
    return "Current taxonomy label carried no additional semantics beyond the recorded status."


def explain_mutation_label_transition(
    *,
    old_label: Any,
    new_label: Any,
    reference_compliance: Any,
    mutated_compliance: Any,
    reference_value: Any,
    mutated_value: Any,
) -> str:
    old_text = str(old_label or "").strip().upper()
    new_text = str(new_label or "").strip().upper()
    reference = normalize_case_compliance(reference_compliance)
    mutated = normalize_case_compliance(mutated_compliance)

    try:
        difference = abs(float(reference_value) - float(mutated_value))
    except (TypeError, ValueError):
        difference = None

    if old_text == new_text:
        return "The legacy and corrected taxonomies agree on this mutation label."
    if new_text == "INEFFECTIVE_MUTATION" and reference == "COMPLIANT" and mutated == "COMPLIANT":
        if old_text == "EFFECTIVE_NO_THRESHOLD_CROSSING":
            if difference is not None and difference > 0.0:
                return (
                    "The label changed because legacy effectiveness meant measurable metric movement, whereas the corrected "
                    "taxonomy only counts threshold-crossing violations as effective."
                )
            return (
                "The label changed because the corrected taxonomy collapses non-violating legacy gain mutations into "
                "INEFFECTIVE_MUTATION."
            )
        if old_text == "NO_MEASURABLE_EFFECT":
            return (
                "The label changed because the corrected taxonomy merges legacy non-violating categories such as "
                "NO_MEASURABLE_EFFECT into INEFFECTIVE_MUTATION."
            )
    if new_text == "EFFECTIVE_VIOLATION" and mutated == "NONCOMPLIANT":
        return "The label changed because the corrected replay now crosses the specification threshold and therefore becomes an effective violation."
    if new_text == "NOT_EVALUATED":
        return "The label changed because the corrected replay no longer yields a scientifically valid target metric."
    return "The label changed because the corrected taxonomy applies different effectiveness semantics than the legacy report."


def build_mutation_label_reconciliation_rows(
    *,
    inventory_rows: Iterable[Mapping[str, Any]],
    old_vs_new_rows: Iterable[Mapping[str, Any]],
    revalidation_rows: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    inventory_map = {
        str(row.get("mutation_id") or row.get("case_id") or "").strip(): row
        for row in inventory_rows
    }
    transition_map = {
        str(row.get("mutation_id") or row.get("case_id") or "").strip(): row
        for row in old_vs_new_rows
    }
    revalidation_map = {
        str(row.get("mutation_id") or row.get("case_id") or "").strip(): row
        for row in revalidation_rows
    }

    rows: list[dict[str, Any]] = []
    for mutation_id in sorted(inventory_map):
        inventory = inventory_map[mutation_id]
        transition = transition_map.get(mutation_id, {})
        revalidation = revalidation_map.get(mutation_id, {})
        old_label = transition.get("old_effectiveness_status") or inventory.get("old_effectiveness_status", "")
        new_label = transition.get("new_effectiveness_status") or revalidation.get("status", "")
        row = {
            "mutation_id": mutation_id,
            "old_effectiveness_label": old_label,
            "new_effectiveness_label": new_label,
            "reason_for_old_label": legacy_effectiveness_reason(str(old_label)),
            "reason_for_new_label": current_effectiveness_reason(
                str(new_label),
                reference_compliance=revalidation.get("reference_compliance"),
                mutated_compliance=revalidation.get("mutated_compliance"),
            ),
            "transition_reason": explain_mutation_label_transition(
                old_label=old_label,
                new_label=new_label,
                reference_compliance=revalidation.get("reference_compliance"),
                mutated_compliance=revalidation.get("mutated_compliance"),
                reference_value=revalidation.get("reference_corrected_gain_db"),
                mutated_value=revalidation.get("mutated_corrected_gain_db"),
            ),
            "reference_corrected_gain": revalidation.get("reference_corrected_gain_db"),
            "mutated_corrected_gain": revalidation.get("mutated_corrected_gain_db"),
            "threshold": revalidation.get("threshold"),
            "operator": revalidation.get("operator"),
            "reference_compliance": revalidation.get("reference_compliance"),
            "mutated_compliance": revalidation.get("mutated_compliance"),
            "final_effectiveness_label": new_label,
            "transition_documented": True,
        }
        rows.append(row)
    return rows
