"""Sampling methodology. All sample sizes are computed in code, never by the AI,
so they are repeatable and explainable. The table follows common ITGC practice;
firms should replace it with their own methodology."""
import csv
import io
import random

# frequency -> (lower-risk size, higher-risk size)
FREQUENCY_TABLE = {
    "Annual": (1, 1),
    "Quarterly": (2, 2),
    "Monthly": (2, 3),
    "Weekly": (5, 10),
    "Daily": (20, 30),
    "Multiple times per day": (25, 40),
    "Event-driven": (25, 40),
}


def determine_test_type(nature: str, frequency: str) -> dict:
    if nature == "Automated" or frequency == "Continuous (automated)":
        return {
            "test_type": "non_sampling",
            "method": "test_of_one",
            "reason": ("Automated / configuration-based control: test one instance (test of one) "
                       "and rely on program change and access ITGCs for consistency over the period."),
        }
    return {
        "test_type": "sampling",
        "method": "random",
        "reason": f"{nature} control performed {frequency.lower()}: select a random sample from the population.",
    }


def sample_size(frequency: str, risk_rating: str, population_size: int | None) -> tuple[int, str]:
    low, high = FREQUENCY_TABLE.get(frequency, (25, 40))
    size = high if risk_rating == "High" else low
    basis = f"{frequency} frequency, {risk_rating.lower()} risk -> {size} per methodology table"
    if population_size is not None:
        if population_size == 0:
            return 0, "Population is empty: no occurrences in period (confirm completeness)."
        if population_size <= size:
            return population_size, f"{basis}; population of {population_size} is not larger, so test all items"
    return size, basis


def parse_population(raw: bytes, filename: str) -> list[dict]:
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return []
        header = [str(h).strip() if h is not None else f"col{i+1}" for i, h in enumerate(rows[0])]
        return [{header[i]: ("" if v is None else str(v)) for i, v in enumerate(r)}
                for r in rows[1:] if any(v not in (None, "") for v in r)]
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader if any((v or "").strip() for v in r.values())]


def select(rows: list[dict], size: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    idx = sorted(rng.sample(range(len(rows)), size)) if size < len(rows) else list(range(len(rows)))
    return [{"index": i + 1, "row": rows[i]} for i in idx]
