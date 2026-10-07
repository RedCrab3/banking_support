import json
from pathlib import Path

import streamlit as st


REPORT_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "evaluation"
    / "reports"
)


METRICS = {
    "classification_ok": "Classification",
    "routing_ok": "Routing",
    "database_ok": "Database correctness",
    "response_facts_ok": "Response fact checks",
    "end_to_end_ok": "End-to-end",
    "memory_flag_ok": "Memory usage",
}


def render_evaluation():
    st.subheader("Saved evaluation results")
    st.caption(
        "Results from fixed functional test sets. "
        "Viewing reports makes no model calls."
    )

    reports = sorted(
        REPORT_DIRECTORY.glob("*.json"),
        reverse=True,
    )

    if not reports:
        st.info("No saved evaluation reports found.")
        return

    selected = st.selectbox(
        "Evaluation report",
        options=reports,
        format_func=lambda path: path.name,
        key="evaluation_report",
    )

    try:
        raw = selected.read_text(encoding="utf-8")
        report = json.loads(raw)
        cases = report["cases"]

        if not isinstance(cases, list) or not cases:
            raise ValueError("Report has no evaluation cases.")

        summary = report["summary"]

        if not isinstance(summary, dict):
            raise ValueError("Invalid report summary.")

    except (OSError, ValueError, KeyError, TypeError) as exc:
        st.error(
            f"Could not read this evaluation report: "
            f"{type(exc).__name__}"
        )
        return

    if not report.get("completed", False):
        st.warning(
            "This report is incomplete. "
            "Metrics cover only the recorded submissions."
        )

    st.write("Scope:", report.get("scope", "Not recorded"))
    st.write("Run started:", report.get("started_at", "Not recorded"))
    st.write(
        "Configured model:",
        report.get("configured_model", "Not recorded"),
    )

    total = len(cases)
    passed = sum(
        bool(case.get("checks", {}).get("end_to_end_ok"))
        for case in cases
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Passed submissions", f"{passed}/{total}")

    latency = summary.get("mean_latency_seconds")
    col2.metric(
        "Mean latency",
        f"{latency:.2f}s" if isinstance(latency, (int, float)) else "N/A",
    )
    col3.metric("Errors", summary.get("error_count", "N/A"))
    col4.metric("Fallbacks", summary.get("fallback_count", "N/A"))

    metric_rows = []

    for key, label in METRICS.items():
        metric = summary.get(key)

        if isinstance(metric, dict):
            metric_rows.append({
                "Metric": label,
                "Passed": metric.get("passed"),
                "Total": metric.get("total"),
                "Percentage": metric.get("percentage"),
            })

    if metric_rows:
        st.dataframe(
            metric_rows,
            hide_index=True,
            use_container_width=True,
        )

    st.info(
        "These percentages describe the saved test set. "
        "They do not establish accuracy on all customer requests. "
        "Response fact checks do not score empathy or writing quality."
    )

    st.markdown("**Submission results**")

    failures_only = st.checkbox(
        "Show failed submissions only",
        key="evaluation_failures_only",
    )

    visible_cases = [
        case for case in cases
        if (
            not failures_only
            or not case.get("checks", {}).get("end_to_end_ok")
        )
    ]

    rows = []

    for case in visible_cases:
        result = case.get("result", {})
        checks = case.get("checks", {})

        rows.append({
            "Case": case["id"],
            "Message": case.get("message", ""),
            "Expected category": case.get("expected_category", ""),
            "Actual category": result.get("category", ""),
            "Expected outcome": case.get("expected_outcome", ""),
            "Actual outcome": result.get("outcome", ""),
            "Result": "PASS" if checks.get("end_to_end_ok") else "FAIL",
            "Seconds": case.get("elapsed_seconds"),
        })

    if rows:
        st.dataframe(
            rows,
            hide_index=True,
            use_container_width=True,
        )
    else:
        st.success("No failed submissions in this report.")

    st.markdown("**Inspect a response**")

    index = st.selectbox(
        "Case",
        options=list(range(len(cases))),
        format_func=lambda value: (
            f"{cases[value]['id']} · "
            f"{cases[value].get('message', '')[:80]}"
        ),
        key=f"evaluation_case_{selected.name}",
    )

    case = cases[index]
    result = case.get("result", {})

    st.write("Customer message:", case.get("message", ""))
    st.write("Assistant response:", result.get("response", ""))

    with st.expander("Checks and execution trace"):
        st.json(case.get("checks", {}))
        st.json(result.get("trace", []))

    with st.expander("Reproducibility details"):
        st.json({
            "versions": report.get("versions", {}),
            "dataset_sha256": report.get("dataset_sha256"),
            "prompt_sha256": report.get("prompt_sha256", {}),
        })

    st.download_button(
        "Download selected report",
        data=raw,
        file_name=selected.name,
        mime="application/json",
        key="download_evaluation_report",
    )