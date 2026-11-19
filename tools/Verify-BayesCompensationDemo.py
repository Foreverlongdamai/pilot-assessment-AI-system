"""Independent Decimal oracle for the CPT-then-compensation demo reports.

Uses no pilot_assessment implementation imports. The captured source input hashes
are the bytes observed before the September 23 compensation demo was generated.
The old supervisor SHA256SUMS.txt is stale and is deliberately not the baseline.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from decimal import Decimal, localcontext
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METHOD = "sequential_bayes_compensation_v1"
GRADE_INDEX = {"U": 0, "A": 1, "D": 2}
SOURCE_HASHES = {
    "SCN-001/01-proficient.input.json": (
        "b6471ecaaa006f613240a41ae7bc44f4953941cbceb2e8f67479a67de4930b41"
    ),
    "SCN-001/02-marginal.input.json": (
        "4397c531d522614fc2ac9aa4c311138208659b8dc92d96de13bf014e7abb6da9"
    ),
    "SCN-001/03-unqualified.input.json": (
        "fe34faa88878fdcb31b9314fad2579548c1ab280227651362f20a9fa6149f2f7"
    ),
    "SCN-002/01-proficient.input.json": (
        "0794cecb7632caa24bca9f8f1895ff0f92493df0461858cde0d904107df6e4c8"
    ),
    "SCN-002/02-marginal.input.json": (
        "eda083da51ac9fadf572f315d3c0d72465c8befebe21dc02326c69a325317d88"
    ),
    "SCN-002/03-unqualified.input.json": (
        "d616b4bf18cec0d01827712a87c4d12a517c374de2b093d6ac5d0994fdde2ee6"
    ),
}


def dec(value):
    return value if isinstance(value, Decimal) else Decimal(str(value))


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def oracle_step(prior, likelihoods, grade, alpha, scores=(0, 50, 100)):
    """Multiply all same-frame CP likelihoods once, then one compensation."""
    prior = [dec(value) for value in prior]
    weights = prior.copy()
    for likelihood in likelihoods:
        weights = [old * dec(value) for old, value in zip(weights, likelihood, strict=True)]
    total = sum(weights)
    if total <= 0:
        raise ValueError("The prior and evidence have zero joint probability.")
    bayes = [value / total for value in weights]
    target = [Decimal(int(index == GRADE_INDEX[grade])) for index in range(3)]
    alpha = dec(alpha)
    posterior = [
        (1 - alpha) * value + alpha * goal for value, goal in zip(bayes, target, strict=True)
    ]
    delta = [new - old for new, old in zip(posterior, bayes, strict=True)]
    score = sum(p * dec(s) for p, s in zip(posterior, scores, strict=True))
    bayes_score = sum(p * dec(s) for p, s in zip(bayes, scores, strict=True))
    return {
        "prior": prior,
        "bayes_posterior": bayes,
        "compensation_target": target,
        "compensation_alpha": alpha,
        "compensation_delta": delta,
        "posterior": posterior,
        "score": score,
        "bayes_score": bayes_score,
        "compensation_score_delta": score - bayes_score,
    }


def serial(value):
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {key: serial(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serial(item) for item in value]
    if isinstance(value, set):
        return [serial(item) for item in sorted(value)]
    return value


class Audit:
    def __init__(self):
        self.failures = []
        self.assertions = 0
        self.numeric_values = 0
        self.max_absolute_error = 0.0
        self.valid_checkpoint_points = 0
        self.valid_item_points = 0
        self.compensation_delta_types = set()

    def check(self, condition, path, actual=None, expected=None):
        self.assertions += 1
        if not condition:
            self.failures.append(
                {"path": path, "actual": serial(actual), "expected": serial(expected)}
            )

    def same(self, actual, expected, path):
        self.check(actual == expected, path, actual, expected)

    def number(self, actual, expected, path):
        if isinstance(expected, (list, tuple)):
            if not isinstance(actual, list) or len(actual) != len(expected):
                self.check(False, path, actual, serial(list(expected)))
                return
            for index, (got, want) in enumerate(zip(actual, expected, strict=True)):
                self.number(got, want, f"{path}[{index}]")
            return
        if (
            not isinstance(actual, (int, float))
            or isinstance(actual, bool)
            or not math.isfinite(actual)
        ):
            self.check(False, path, actual, expected)
            return
        expected = float(expected)
        error = abs(actual - expected)
        self.max_absolute_error = max(self.max_absolute_error, error)
        self.numeric_values += 1
        self.check(
            math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9), path, actual, expected
        )

    def step(self, point, expected, path):
        for key in (
            "prior",
            "bayes_posterior",
            "compensation_target",
            "compensation_alpha",
            "posterior",
            "score",
        ):
            self.number(point.get(key), expected[key], f"{path}.{key}")
        delta = point.get("compensation_delta")
        self.compensation_delta_types.add(
            "probability_vector" if isinstance(delta, list) else "invalid"
        )
        self.number(delta, expected["compensation_delta"], f"{path}.compensation_delta")
        for key in ("bayes_score", "compensation_score_delta"):
            if key in point:
                self.number(point[key], expected[key], f"{path}.{key}")
        posterior = point.get("posterior")
        if isinstance(posterior, list):
            self.check(
                all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in posterior),
                f"{path}.simplex_bounds",
            )
            self.number(sum(posterior), 1, f"{path}.simplex_sum")


def observation_likelihood(model, grade):
    column = model["states"].index(grade)
    return [row[column] for row in model["probabilities"]]


def math_examples():
    table = [[0.10, 0.25, 0.65], [0.35, 0.63, 0.02], [0.90, 0.099, 0.001]]
    priors = {
        "D_dominant": [0.05, 0.05, 0.90],
        "A_dominant": [0.05, 0.90, 0.05],
        "U_dominant": [0.90, 0.05, 0.05],
    }
    result = {"alpha": 0.2, "state_order": ["Low", "Mid", "High"], "cases": []}
    for name, prior in priors.items():
        for column, grade in enumerate(("D", "A", "U")):
            step = oracle_step(prior, [[row[column] for row in table]], grade, 0.2)
            result["cases"].append(
                {
                    "prior_name": name,
                    "grade": grade,
                    "score_before": sum(p * s for p, s in zip(prior, (0, 50, 100), strict=True)),
                    **serial(step),
                }
            )
    recovery = []
    for name, prior, grade, col in (
        ("pure_D_then_U", [0, 0, 1], "U", 2),
        ("pure_U_then_D", [1, 0, 0], "D", 0),
    ):
        points = []
        for _ in range(5):
            step = oracle_step(prior, [[row[col] for row in table]], grade, 0.2)
            points.append(serial(step))
            prior = step["posterior"]
        recovery.append({"case": name, "steps": points})
    result["pure_state_recovery"] = recovery
    counter = oracle_step([0.54, 0.01, 0.45], [[row[1] for row in table]], "A", 0.2)
    result["known_A_counterexample"] = {"score_before": 45.5, **serial(counter)}
    result["limits"] = [
        "Compensation is an engineering adjustment after CPT Bayes, "
        "not a pure posterior under the original BN.",
        "Fixed alpha is applied per valid frame; "
        "this model does not claim sampling-rate invariance.",
        "An A observation increases the middle-state mass "
        "but need not move the score toward 50 for every prior.",
        "Repeated grades can still saturate; compensation permits recovery "
        "when an opposing grade subsequently arrives.",
        "The final value is the same sequential process endpoint, "
        "not a separate order-invariant whole-flight estimator.",
    ]
    # Independent exact reference: uniform prior + D, alpha=.2.
    test = oracle_step([Decimal(1) / 3] * 3, [[0.1, 0.35, 0.9]], "D", 0.2)
    assert abs(test["score"] - Decimal(2260) / 27) < Decimal("1e-60")
    assert recovery[0]["steps"][0]["posterior"] == [0.2, 0.0, 0.8]
    assert recovery[1]["steps"][0]["posterior"] == [0.8, 0.0, 0.2]
    good = serial(test)
    sanity = Audit()
    sanity.step(good, test, "valid_oracle_point")
    assert not sanity.failures
    mutations = []
    for key in (
        "prior",
        "bayes_posterior",
        "compensation_target",
        "compensation_delta",
        "posterior",
        "score",
        "compensation_alpha",
    ):
        broken = copy.deepcopy(good)
        if isinstance(broken[key], list):
            broken[key][0] += 0.01
        else:
            broken[key] += 0.01
        sanity = Audit()
        sanity.step(broken, test, key)
        assert sanity.failures, key
        mutations.append({"field": key, "corruption_detected": True})
    result["verifier_mutation_checks"] = mutations
    return result


def audit_report(report_path, source_root, demo_root, audit):
    relative = report_path.relative_to(demo_root)
    name = relative.as_posix()
    report, original = load(report_path), load(source_root / relative)
    scene = relative.parts[0]
    config = load(demo_root / scene / "configuration.json")
    source_config = load(source_root / scene / "configuration.json")
    audit.same(report["configuration"], config, f"{name}.configuration_snapshot")
    audit.same(config["parameters"], source_config["parameters"], f"{name}.thresholds")
    audit.same(
        set(config["skill_models"]), set(source_config["skill_models"]), f"{name}.model_item_ids"
    )
    input_relative = relative.with_name(relative.name.replace(".report.json", ".input.json"))
    key = input_relative.as_posix()
    source_hash, demo_hash = (
        digest(source_root / input_relative),
        digest(demo_root / input_relative),
    )
    audit.same(source_hash, SOURCE_HASHES[key], f"{name}.original_input_unchanged")
    audit.same(demo_hash, source_hash, f"{name}.copied_input_sha256")
    input_data = load(demo_root / input_relative)
    audit.same(report["input"], input_data, f"{name}.input_snapshot")
    audit.same(input_data, original["input"], f"{name}.source_report_input")
    for field in ("scene_id", "grade", "passed", "calculation_status"):
        audit.same(report[field], original[field], f"{name}.{field}")
    old_items = {item["item_id"]: item for item in original["items"]}
    audit.same([item["item_id"] for item in report["items"]], list(old_items), f"{name}.item_ids")
    summaries = []
    for item in report["items"]:
        item_id = item["item_id"]
        path = f"{name}/{item_id}"
        # Preserve all rule-layer outputs, including every original frame grade.
        for field, value in old_items[item_id].items():
            if field != "skill_quantification":
                audit.same(item.get(field), value, f"{path}.rule_layer.{field}")
        skill = item["skill_quantification"]
        if item_id not in config["skill_models"]:
            audit.same(skill["status"], "not_applicable", f"{path}.checklist_status")
            audit.same(skill["posterior"], None, f"{path}.checklist_posterior")
            audit.same(skill["score"], None, f"{path}.checklist_score")
            continue
        model, old_model = config["skill_models"][item_id], source_config["skill_models"][item_id]
        for field in ("prior", "state_scores", "checkpoint_models"):
            audit.same(model[field], old_model[field], f"{path}.source_parameter.{field}")
        audit.same(model["inference_method"], METHOD, f"{path}.model_method")
        audit.number(model["compensation"]["alpha"], 0.2, f"{path}.configured_alpha")
        alpha, scores = model["compensation"]["alpha"], model["state_scores"]
        audit.same(skill["status"], "complete", f"{path}.result_status")
        audit.same(skill["method"], METHOD, f"{path}.result_method")
        temporal = skill["temporal_analysis"]
        audit.same(temporal["method"], METHOD, f"{path}.temporal_method")
        audit.same(temporal["item_trace"]["method"], METHOD, f"{path}.item_trace_method")
        audit.same(skill["cumulative_trace"]["method"], METHOD, f"{path}.cumulative_method")
        frames = input_data["items"][item_id]["frames"]
        cp_rules = {
            cp["checkpoint_id"]: {p["frame_index"]: p for p in cp["timeline"]}
            for cp in item["checkpoints"]
        }
        cp_traces = {trace["checkpoint_id"]: trace for trace in temporal["checkpoint_traces"]}
        audit.same(set(cp_traces), set(model["checkpoint_models"]), f"{path}.checkpoint_trace_ids")
        for cp_id, cp_model in model["checkpoint_models"].items():
            prior = model["prior"]
            trace = cp_traces[cp_id]
            audit.same(trace["method"], METHOD, f"{path}/{cp_id}.method")
            audit.same(
                [p["frame_index"] for p in trace["timeline"]],
                list(range(len(frames))),
                f"{path}/{cp_id}.full_item_time_axis",
            )
            valid_indices = []
            for point in trace["timeline"]:
                index = point["frame_index"]
                observation = cp_rules[cp_id].get(index)
                ppath = f"{path}/{cp_id}/frame[{index}]"
                for field in ("timestamp_s", "phase_id"):
                    audit.same(point[field], frames[index][field], f"{ppath}.{field}")
                if observation is None:
                    audit.same(point.get("posterior"), None, f"{ppath}.not_applicable_posterior")
                    audit.same(point.get("score"), None, f"{ppath}.not_applicable_score")
                    continue
                audit.same(observation["status"], "calculated", f"{ppath}.valid_demo_observation")
                grade = observation["grade"]
                audit.same(point.get("grade"), grade, f"{ppath}.grade")
                expected = oracle_step(
                    prior, [observation_likelihood(cp_model, grade)], grade, alpha, scores
                )
                audit.step(point, expected, ppath)
                valid_indices.append(index)
                prior = expected["posterior"]
                audit.valid_checkpoint_points += 1
            audit.same(
                valid_indices,
                list(cp_rules[cp_id]),
                f"{path}/{cp_id}.complete_observation_coverage",
            )
        item_rules = {p["frame_index"]: p for p in item["timeline"]}
        cumulative = skill["cumulative_trace"]["timeline"]
        trace_points = temporal["item_trace"]["timeline"]
        audit.same(
            [p["frame_index"] for p in trace_points],
            list(item_rules),
            f"{path}.complete_item_coverage",
        )
        audit.same(
            [p["frame_index"] for p in cumulative],
            list(item_rules),
            f"{path}.complete_cumulative_coverage",
        )
        prior = model["prior"]
        for point, prefix in zip(trace_points, cumulative, strict=True):
            index = point["frame_index"]
            ppath = f"{path}/frame[{index}]"
            for field in ("timestamp_s", "phase_id"):
                audit.same(point[field], frames[index][field], f"{ppath}.{field}")
                audit.same(prefix[field], frames[index][field], f"{ppath}.cumulative.{field}")
            grade = item_rules[index]["grade"]
            likelihoods, grades = [], []
            for cp_id, cp_model in model["checkpoint_models"].items():
                observation = cp_rules[cp_id].get(index)
                if observation is not None:
                    audit.same(
                        observation["status"],
                        "calculated",
                        f"{ppath}/{cp_id}.valid_demo_observation",
                    )
                    grades.append(observation["grade"])
                    likelihoods.append(observation_likelihood(cp_model, observation["grade"]))
            audit.same(grade, min(grades, key=GRADE_INDEX.get), f"{ppath}.worst_grade_target")
            audit.same(point.get("grade"), grade, f"{ppath}.grade")
            expected = oracle_step(prior, likelihoods, grade, alpha, scores)
            audit.step(point, expected, ppath)
            for field in ("posterior", "score"):
                audit.number(prefix.get(field), expected[field], f"{ppath}.cumulative.{field}")
            for field in ("prior", "bayes_posterior", "compensation_target", "compensation_alpha"):
                if field in prefix:
                    audit.number(prefix[field], expected[field], f"{ppath}.cumulative.{field}")
            prior = expected["posterior"]
            audit.valid_item_points += 1
        audit.number(skill["posterior"], expected["posterior"], f"{path}.final_posterior")
        audit.number(skill["score"], expected["score"], f"{path}.final_score")
        summaries.append(
            {
                "item_id": item_id,
                "grade": item["grade"],
                "passed": item["passed"],
                "score": skill["score"],
                "posterior": skill["posterior"],
                "item_points": len(trace_points),
            }
        )
    return {"report": name, "input_sha256": demo_hash, "items": summaries}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--demo-dir", type=Path, default=ROOT / "examples/bayes-compensation-2026-09-23"
    )
    parser.add_argument(
        "--source-dir", type=Path, default=ROOT / "examples/supervisor-demo-2026-09-15"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "tmp/compensation_qa/independent-verification.json"
    )
    parser.add_argument(
        "--math-only",
        action="store_true",
        help="Only compute the independent nine-case and recovery oracles.",
    )
    args = parser.parse_args()
    audit = Audit()
    result = {
        "method": METHOD,
        "oracle": "stdlib Decimal with 80-digit precision; no production imports",
        "source_dir": str(args.source_dir.resolve()),
        "demo_dir": str(args.demo_dir.resolve()),
        "source_input_baseline": SOURCE_HASHES,
        "reports": [],
    }
    with localcontext() as ctx:
        ctx.prec = 80
        result["mathematical_examples"] = math_examples()
        if not args.math_only:
            for relative in SOURCE_HASHES:
                report_relative = relative.replace(".input.json", ".report.json")
                path = args.demo_dir / report_relative
                try:
                    result["reports"].append(
                        audit_report(path, args.source_dir, args.demo_dir, audit)
                    )
                except (OSError, KeyError, ValueError, TypeError, IndexError) as exc:
                    audit.check(
                        False,
                        report_relative,
                        f"{type(exc).__name__}: {exc}",
                        "readable complete compensation report",
                    )
    result.update(
        passed=not audit.failures,
        scope="math_only" if args.math_only else "six_demo_reports",
        assertions=audit.assertions,
        numeric_values=audit.numeric_values,
        max_absolute_error=audit.max_absolute_error,
        valid_checkpoint_points=audit.valid_checkpoint_points,
        valid_item_points=audit.valid_item_points,
        compensation_delta_types=sorted(audit.compensation_delta_types),
        failures=audit.failures,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(serial(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                key: result[key]
                for key in (
                    "passed",
                    "scope",
                    "assertions",
                    "numeric_values",
                    "max_absolute_error",
                    "valid_checkpoint_points",
                    "valid_item_points",
                )
            },
            ensure_ascii=False,
        )
    )
    print(f"Report: {args.output.resolve()}")
    if audit.failures:
        print(json.dumps(audit.failures[:8], ensure_ascii=False, indent=2))
    return int(bool(audit.failures))


if __name__ == "__main__":
    raise SystemExit(main())
