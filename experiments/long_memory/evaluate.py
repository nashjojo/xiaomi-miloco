"""CPU-only synthetic memory experiment; NOT a video perception benchmark."""
from __future__ import annotations

import argparse
import ast
import copy
import json
import time
import uuid
from collections import Counter, defaultdict
from pathlib import Path

BASE = 1792022400000  # fixed Unix milliseconds; comparisons use event time
UNKNOWN = None


def scenario(seconds):
    """Same local script repeated every minute: duration changes load, not difficulty."""
    truth, queries = [], []
    for minute in range(seconds // 60):
        obj = f"cup-{minute}"
        # Two real people; track 1 deliberately collides between cameras.
        script = [
            (2, "a", "1", "alice", "place", "table", True),
            (8, "a", "2", "bob", "touch", "table", False),
            (14, "a", "1", "alice", "move", "shelf", False),
            (20, "a", "1", "alice", "leave", "door", False),
            (26, "a", "9", "alice", "return", "door", False),
            (32, "a", "9", "alice", "move", "bag", False),
            (38, "b", "1", "alice", "carry", "hall", True),
            (44, "b", "1", "alice", "place", "cabinet", False),
            (50, "b", "1", "alice", "occluded", None, False),
            (56, "b", "1", "alice", "reveal", "cabinet", False),
        ]
        for offset, cam, track, person, action, location, meaningful in script:
            eid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"miloco-synthetic:{minute}:{offset}"))
            truth.append(dict(id=eid, timestamp=BASE+(minute*60+offset)*1000,
                              camera=cam, track=track, person=person, object=obj,
                              action=action, location=location, meaningful=meaningful))
        ids = {e[0]: truth[-10+i]["id"] for i, e in enumerate(script)}
        def q(kind, offsets, expected):
            queries.append(dict(id=f"{minute}:{kind}", kind=kind,
                                evidence=[ids[o] for o in offsets], expected=expected,
                                selectors=[dict(timestamp=BASE+(minute*60+o)*1000,
                                                camera=script[[s[0] for s in script].index(o)][1]) for o in offsets],
                                asked_at=BASE+seconds*1000))
        q("historical_location", [14], "shelf")
        q("mover", [32], "alice")
        q("return_identity", [2, 26], True)
        q("cross_camera", [32, 38], True)
        q("location_change", [2, 14], ["table", "shelf"])
        q("last_seen_location", [56], "cabinet")
        # Current position while occluded is not knowable from last visible position.
        q("occluded_current", [50], None)
    return truth, queries


def observe(truth, fault):
    """Explicit fault injection, NOT simulation of actual Gate/DeepSORT accuracy."""
    observed, losses = [], Counter()
    for original in truth:
        e = copy.deepcopy(original)
        offset = ((e["timestamp"]-BASE)//1000) % 60
        if fault in ("gate", "combined") and offset == 14:
            losses["injected_gate_skip"] += 1
            continue
        if fault in ("occlusion", "combined") and offset == 32:
            losses["injected_hidden_action"] += 1
            continue
        if fault in ("identity", "combined") and offset in (26, 32):
            e["person"] = "unknown_7"
        if fault in ("cross_camera", "combined") and e["camera"] == "b":
            e["person"] = "unknown_8"
            e["object"] = "unlinked-" + e["object"]
        # Deliberately strip truth-only meaningful label from memory input.
        meaningful = e.pop("meaningful")
        observed.append({
            "event": {"event_id": e.pop("id"), "timestamp": e.pop("timestamp"),
                      "text": f"{e['person']} {e['action']} {e['object']}",
                      "has_rule_hit": meaningful, "has_suggestion": False,
                      "has_asr": False, "snapshot_count": 0,
                      "device_ids": [e["camera"]]},
            # Evaluation sidecar: these fields are NOT Miloco Omni output fields.
            "facts": e,
        })
    return observed, losses


def memory(records, mode, period=60, budget=0):
    if mode == "raw":
        kept = records
    elif mode == "periodic":
        # Deterministic lossy baseline, not the production LLM digest.
        # Last state per entity per period. No access to truth or queries.
        buckets = {}
        for r in records:
            f = r["facts"]
            key = ((r["event"]["timestamp"]-BASE)//(period*1000), f["object"])
            buckets[key] = r
        kept = list(buckets.values())
    elif mode == "profile":
        # Profile-only baseline rejects transient states. No fabricated habits
        # from the five-hour repetitive synthetic fixture; no Dreaming is run.
        kept = []
    else:
        raise ValueError(mode)
    return kept[-budget:] if budget else kept


def answer(records, query):
    # Exact temporal/camera retrieval, without gold IDs or answer access.
    # This deliberately does not claim free-form language retrieval capability.
    index = {(r["event"]["timestamp"], r["facts"]["camera"]): r for r in records
             if r["event"]["timestamp"] <= query["asked_at"]}
    evidence = [index.get((s["timestamp"], s["camera"])) for s in query["selectors"]]
    if any(r is None for r in evidence):
        return {"value": None, "citations": [], "reason": "missing_evidence"}
    facts = [r["facts"] for r in evidence]
    kind = query["kind"]
    value = None
    if kind in ("historical_location", "last_seen_location"):
        value = facts[0]["location"]
    elif kind == "mover":
        value = facts[0]["person"] if not facts[0]["person"].startswith("unknown") else None
    elif kind in ("return_identity", "cross_camera"):
        # Never infer stable identity from same local track number or proximity.
        if all(not f["person"].startswith("unknown") for f in facts):
            value = len({f["person"] for f in facts}) == 1
            if kind == "cross_camera":
                value = value and len({f["object"] for f in facts}) == 1
    elif kind == "location_change":
        value = [f["location"] for f in facts]
    elif kind != "occluded_current":
        raise ValueError(kind)
    return {"value": value, "citations": [r["event"]["event_id"] for r in evidence],
            "reason": "occluded" if kind == "occluded_current" else "observed"}


def score(records, queries):
    details, grouped = [], defaultdict(Counter)
    for q in queries:
        a = answer(records, {k: v for k, v in q.items() if k not in ("expected", "evidence")})
        correct = a["value"] == q["expected"]
        known = q["expected"] is not None
        c = grouped[q["kind"]]
        c.update(total=1, correct=int(correct), answerable=int(known),
                 answered=int(a["value"] is not None),
                 evidence_correct=int(set(a["citations"]) == set(q["evidence"])),
                 false_claim=int(not known and a["value"] is not None))
        details.append(dict(query=q, answer=a, correct=correct,
                            lag_seconds=(q["asked_at"]-max(s["timestamp"] for s in q["selectors"]))/1000))
    counts = sum(grouped.values(), Counter())
    def metrics(c):
        return {**c, "accuracy": c["correct"]/c["total"] if c["total"] else None,
                "coverage": c["answered"]/c["answerable"] if c["answerable"] else None}
    return dict(overall=metrics(counts), by_kind={k: metrics(v) for k,v in grouped.items()},
                details=details)


def schema_contract(root):
    """Extract actual model with AST to avoid importing camera/ONNX dependencies."""
    path = root / "backend/miloco/src/miloco/perception/schema.py"
    tree = ast.parse(path.read_text())
    node = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "MeaningfulEvent")
    return {n.target.id for n in node.body if isinstance(n, ast.AnnAssign)}


def run(out, period=60, budget=0):
    out.mkdir(parents=True, exist_ok=True)
    fields = schema_contract(Path(__file__).resolve().parents[2])
    report = {"warning": "SYNTHETIC MECHANISM TEST; NOT VIDEO/VLM SCORES",
              "config": dict(period_seconds=period, record_budget=budget), "runs": []}
    for duration in (60, 18000):
        truth, queries = scenario(duration)
        (out/f"truth-{duration}.json").write_text(json.dumps(dict(events=truth, queries=queries), indent=2))
        for fault in ("clean", "gate", "identity", "occlusion", "cross_camera", "combined"):
            observed, losses = observe(truth, fault)
            assert all(set(r["event"]) <= fields for r in observed)
            for stream in ("all_observed", "meaningful_only"):
                inputs = [r for r in observed if stream == "all_observed" or r["event"]["has_rule_hit"]]
                (out/f"observed-{duration}-{fault}-{stream}.jsonl").write_text(
                    "".join(json.dumps(r)+"\n" for r in inputs))
                for mode in ("raw", "periodic", "profile"):
                    start = time.perf_counter()
                    kept = memory(inputs, mode, period, budget)
                    result = score(kept, queries)
                    details = result.pop("details")
                    name = f"{duration}-{fault}-{stream}-{mode}"
                    (out/f"answers-{name}.json").write_text(json.dumps(details, indent=2))
                    report["runs"].append(dict(duration_seconds=duration, fault=fault,
                        stream=stream, mode=mode, truth_events=len(truth),
                        observed_events=len(observed), persisted_events=len(inputs),
                        retained_events=len(kept), injected_losses=dict(losses),
                        observation_recall=len(observed)/len(truth),
                        persistence_recall=len(inputs)/len(truth),
                        memory_bytes=len(json.dumps(kept).encode()),
                        cpu_wall_seconds=time.perf_counter()-start, **result))
    (out/"report.json").write_text(json.dumps(report, indent=2))
    lines = ["# Synthetic mechanism results", "", report["warning"], "",
             "|Seconds|Fault|Stream|Memory|Observation recall|Retained|QA accuracy|", "|---|---|---|---|---|---|---|"]
    for r in report["runs"]:
        lines.append(f"|{r['duration_seconds']}|{r['fault']}|{r['stream']}|{r['mode']}|{r['observation_recall']:.3f}|{r['retained_events']}|{r['overall']['accuracy']:.3f}|")
    (out/"RESULTS.md").write_text("\n".join(lines)+"\n")
    print(f"Wrote {len(report['runs'])} runs to {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("/tmp/miloco-long-memory"))
    parser.add_argument("--period", type=int, default=60)
    parser.add_argument("--budget", type=int, default=0, help="retained records, 0=unlimited")
    args = parser.parse_args()
    if args.period < 1 or args.budget < 0:
        parser.error("period must be positive and budget nonnegative")
    run(args.out, args.period, args.budget)
