"""Per-frame CPT Bayes followed by explicit bidirectional compensation.

All hidden-state vectors use low/mid/high order. The observation grade maps
U/A/D to those states only for the declared compensation step; the CPT still
determines the preceding Bayesian posterior. Scores never enter inference.
"""

from __future__ import annotations

import copy
import math

from pilot_assessment.scene_assessment.configuration import SEQUENTIAL_INFERENCE_METHOD

METHOD = SEQUENTIAL_INFERENCE_METHOD
_TARGETS = {"D": [0.0, 0.0, 1.0], "A": [0.0, 1.0, 0.0], "U": [1.0, 0.0, 0.0]}
_AUDIT_FIELDS = (
    "prior",
    "bayes_posterior",
    "compensation_target",
    "compensation_alpha",
    "compensation_delta",
)
_MESSAGE = (
    "贝叶斯网络随每帧观测更新低／中／高状态概率；跨环节保留更新结果，分数由概率与状态分值换算。"
)


def bayes_compensation_update(prior, log_likelihood, grade, alpha, state_scores):
    """Return an auditable update with log-space likelihood multiplication.

    Zero prior components are valid and remain zero in the Bayes step. A
    positive compensation can restore the observed target state afterward.
    """
    logs = [
        math.log(p) + likelihood if p > 0 else -math.inf
        for p, likelihood in zip(prior, log_likelihood, strict=True)
    ]
    maximum = max(logs)
    if not math.isfinite(maximum):
        raise ValueError("No state has a positive finite evidence probability.")
    weights = [math.exp(value - maximum) for value in logs]
    total = math.fsum(weights)
    bayes = [weight / total for weight in weights]
    target = _TARGETS[grade]
    posterior = [(1 - alpha) * p + alpha * t for p, t in zip(bayes, target, strict=True)]
    return {
        "prior": list(prior),
        "bayes_posterior": bayes,
        "compensation_target": list(target),
        "compensation_alpha": alpha,
        "compensation_delta": [new - old for new, old in zip(posterior, bayes, strict=True)],
        "posterior": posterior,
        "score": math.fsum(p * value for p, value in zip(posterior, state_scores, strict=True)),
        "log_bayes_factor_high_low": log_likelihood[2] - log_likelihood[0],
    }


def _point(frame, grade, expected, observed, evidence=0):
    return {key: frame[key] for key in ("frame_index", "timestamp_s", "phase_id")} | {
        "grade": grade,
        "status": "no_evidence",
        "posterior": None,
        "score": None,
        "log_bayes_factor_high_low": None,
        "update_kind": "none",
        "evidence_count": evidence,
        "observed_checkpoint_count": observed,
        "expected_checkpoint_count": expected,
        **dict.fromkeys(_AUDIT_FIELDS),
    }


def _trace(checkpoint_id, timeline, observed, partial):
    return {
        "checkpoint_id": checkpoint_id,
        "method": METHOD,
        "status": "no_evidence" if not observed else "partial" if partial else "complete",
        "message": _MESSAGE,
        "timeline": timeline,
    }


def _calculate_traces(result, model, records):
    alpha = model["compensation"]["alpha"]
    scores = model["state_scores"]
    states = [
        {
            "id": point["checkpoint_id"],
            "lookup": {frame["frame_index"]: frame for frame in point["timeline"]},
            "prior": list(model["prior"]),
            "observed": False,
            "tainted": False,
            "incomplete": any(metric["status"] != "calculated" for metric in point["metrics"]),
            "timeline": [],
        }
        for point in result["checkpoints"]
    ]
    expected = len(states)
    item_prior = list(model["prior"])
    item_tainted = False
    item_updated = False
    item_timeline = []
    missing_counts = []
    missing_count = 0
    grades = {point["frame_index"]: point["grade"] for point in result["timeline"]}
    for frame in records:
        likelihoods = []
        evidence_count = 0
        frame_missing = False
        for state in states:
            observation = state["lookup"].get(frame["frame_index"])
            point = _point(
                frame, observation["grade"] if observation else None, 1, int(state["observed"])
            )
            state["timeline"].append(point)
            if observation is None:
                continue
            checkpoint = model["checkpoint_models"][state["id"]]
            if (
                observation["status"] != "calculated"
                or observation["grade"] not in checkpoint["states"]
            ):
                state["tainted"] = item_tainted = frame_missing = True
                point.update(status="insufficient_evidence", update_kind="missing")
                continue
            evidence_count += 1
            was_observed = state["observed"]
            state["observed"] = True
            point.update(evidence_count=1, observed_checkpoint_count=1)
            if state["tainted"]:
                point.update(status="insufficient_evidence", update_kind="missing")
                continue
            grade_index = checkpoint["states"].index(observation["grade"])
            likelihood = [math.log(row[grade_index]) for row in checkpoint["probabilities"]]
            update = bayes_compensation_update(
                state["prior"], likelihood, observation["grade"], alpha, scores
            )
            state["prior"] = update["posterior"]
            point.update(
                update,
                status="calculated",
                update_kind="bayes_compensation" if was_observed else "initial",
            )
            likelihoods.append(likelihood)
        observed = sum(state["observed"] for state in states)
        point = _point(frame, grades.get(frame["frame_index"]), expected, observed, evidence_count)
        if item_tainted:
            point.update(status="insufficient_evidence", update_kind="missing")
        elif likelihoods:
            # The item consumes observation likelihoods, not CP posteriors.
            # Apply the prior and compensation once regardless of CP count.
            likelihood = [math.fsum(row[index] for row in likelihoods) for index in range(3)]
            update = bayes_compensation_update(
                item_prior, likelihood, point["grade"], alpha, scores
            )
            item_prior = update["posterior"]
            point.update(
                update,
                status="calculated",
                update_kind="bayes_compensation" if item_updated else "initial",
            )
            item_updated = True
        missing_count += int(frame_missing)
        missing_counts.append(missing_count)
        item_timeline.append(point)
    phase_incomplete = any(phase["status"] != "calculated" for phase in result["phase_results"])
    observed = sum(state["observed"] for state in states)
    partial = phase_incomplete or item_tainted or observed != expected or not observed
    partial = partial or any(state["incomplete"] for state in states)
    traces = [
        _trace(
            state["id"],
            state["timeline"],
            state["observed"],
            state["tainted"] or state["incomplete"],
        )
        for state in states
    ]
    return traces, _trace(None, item_timeline, observed, partial), missing_counts, partial


def quantify_sequential(
    configuration,
    item,
    result,
    fallback,
    issues,
    *,
    blocked=False,
    process_blocked=False,
    records=None,
):
    """Calculate one trace for both the final assessment and all item curves."""
    model = configuration["skill_models"][item["item_id"]]
    quantification = copy.deepcopy(fallback)
    warnings = [
        "CPT、先验、更新系数和状态分值均未标定，是项目研究参数，不是航空官方评分标准。",
        "每个有效帧更新一次贝叶斯网络；固定每帧更新系数的响应受采样频率影响。",
        "item 给定能力时假设检查点观察条件独立；同帧观测目标取适用检查点最差等级。",
        "最终概率是这一序贯模型在任务末尾的状态；不是与时间顺序无关的整段平均能力。",
        "规则 U 与 Fail 独立保留，不会被概率回升或分数抵消。",
    ]
    quantification.update(
        method=METHOD,
        **{
            key: model.get(key) if isinstance(model.get(key), str) else None
            for key in ("model_version", "calibration", "parameter_source")
        },
        posterior=None,
        score=None,
        local_traces=[],
        cumulative_trace=None,
        warnings=warnings,
        evidence=[
            {
                "checkpoint_id": point["checkpoint_id"],
                "grade": point["grade"],
                "used": False,
                "weight": None,
                "frame_distribution": copy.deepcopy(point["frame_distribution"]),
            }
            for point in result["checkpoints"]
        ],
    )
    analysis = {
        "status": "not_configured",
        "method": METHOD,
        "model_version": quantification["model_version"],
        "message": _MESSAGE,
        "warnings": list(warnings),
        "checkpoint_traces": [],
        "item_trace": None,
    }
    quantification["temporal_analysis"] = analysis
    path = "/skill_models/" + item["item_id"]
    model_issues = [
        entry
        for entry in issues
        if entry["path"] in ("/skill_models", path) or entry["path"].startswith(path + "/")
    ]
    if model_issues:
        message = "贝叶斯网络参数不完整或不合法；未计算概率。"
        quantification.update(
            status="invalid_model",
            message=message,
            warnings=[entry["message"] for entry in model_issues],
        )
        analysis.update(
            status="invalid_model", message=message, warnings=list(quantification["warnings"])
        )
        return quantification
    if process_blocked:
        message = "输入结构、时间或规则参数无效；保留规则结果，不生成概率曲线。"
        quantification.update(status="insufficient_evidence", message=message)
        analysis.update(status="blocked", message=message)
        return quantification
    try:
        traces, item_trace, missing_counts, partial = _calculate_traces(
            result,
            model,
            result["timeline"] if records is None else records,
        )
    except ValueError:
        message = "本帧总似然不可归一化；未补零概率或切换算法。"
        quantification.update(status="invalid_model", message=message)
        analysis.update(status="invalid_model", message=message)
        return quantification
    complete = not blocked and not partial
    analysis.update(
        status="complete" if complete else "partial",
        checkpoint_traces=traces,
        item_trace=item_trace,
    )
    if not complete and item_trace["timeline"]:
        # Required phase coverage cannot leave a displayed final result. Earlier
        # valid prefixes and independent CP observations remain available.
        item_trace["status"] = "partial"
        item_trace["timeline"][-1].update(
            status="insufficient_evidence",
            posterior=None,
            score=None,
            log_bayes_factor_high_low=None,
            **dict.fromkeys(_AUDIT_FIELDS),
        )
    cumulative = []
    for point, missing in zip(item_trace["timeline"], missing_counts, strict=True):
        status = point["status"]
        if status == "calculated":
            status = (
                "complete"
                if point["observed_checkpoint_count"] == point["expected_checkpoint_count"]
                else "partial"
            )
        else:
            status = "insufficient_evidence"
        cumulative.append(
            {
                **{
                    key: copy.deepcopy(point[key])
                    for key in (
                        "frame_index",
                        "timestamp_s",
                        "phase_id",
                        "observed_checkpoint_count",
                        "expected_checkpoint_count",
                        "posterior",
                        "score",
                    )
                },
                "status": status,
                "missing_frame_count": missing,
            }
        )
    quantification["cumulative_trace"] = {
        "item_id": result["item_id"],
        "method": METHOD,
        "message": _MESSAGE,
        "timeline": cumulative,
    }
    if not complete:
        quantification.update(
            status="insufficient_evidence",
            message="本项数据或必需环节不完整；保留有效前缀与已知 U，不提供最终概率或分数。",
        )
        return quantification
    endpoint = item_trace["timeline"][-1]
    if endpoint["posterior"] is None:
        quantification.update(
            status="insufficient_evidence", message="末帧没有完整适用证据；不提供最终概率或分数。"
        )
        analysis["status"] = "partial"
        return quantification
    for evidence in quantification["evidence"]:
        evidence["used"] = True
    quantification.update(
        status="complete",
        posterior=copy.deepcopy(endpoint["posterior"]),
        score=endpoint["score"],
        evidence_count=len(result["checkpoints"]),
        message=_MESSAGE,
    )
    return quantification
