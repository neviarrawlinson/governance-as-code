import importlib
import json
import unittest
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[2]
REPO = ROOT.parents[1]
WORKFLOW = REPO / ".github" / "workflows" / "governance-assurance.yml"


def item(subject, outcome, integrity, action, transition):
    return {
        "control_id": "ACP-001-03", "subject_id": subject,
        "governance_outcome": outcome, "integrity_status": integrity,
        "assurance_action": action, "transition": transition,
        "evaluation_date": "2026-08-25", "reason": "Existing reason.",
    }


class LifecycleDiagnosticTests(unittest.TestCase):
    def setUp(self):
        module = importlib.import_module("automation.diagnostics")
        self.assertTrue(hasattr(module, "build_lifecycle_diagnostic"))
        self.assertTrue(hasattr(module, "render_lifecycle_summary"))
        self.assertTrue(hasattr(module, "write_diagnostic"))
        self.build = module.build_lifecycle_diagnostic
        self.render = module.render_lifecycle_summary
        self.write = module.write_diagnostic

    def diagnostic(self, **changes):
        values = {
            "run": {
                "repository": "neviarrawlinson/governance-as-code",
                "workflow": "Governance Assurance Demonstration",
                "run_id": "32805700165", "run_number": "15",
                "trigger": "push", "branch": "main", "commit_sha": "0d5000a",
            },
            "prior_state": {
                "status": "FOUND", "source_run_id": "32799613802",
                "artifact_id": "9546047131",
                "artifact_name": "trusted-assurance-state",
                "evaluation_date": "2026-08-22", "reason": "Newest eligible state.",
            },
            "trusted_history": {
                "lineage_id": "ACP-001-03-synthetic-assurance",
                "lineage_status": "ESTABLISHED",
                "status": "FOUND",
                "historical_comparison_allowed": True,
                "issue_operations_allowed": True,
                "publication_allowed": True,
                "recovery_required": False,
                "reason": "Authoritative trusted history was found and validated.",
                "source_run_id": "32799613802",
                "artifact_id": "9546047131",
                "artifact_name": "trusted-assurance-state",
                "prior_evaluation_date": "2026-08-22",
            },
            "assurance_observation": {
                "status": "COMPLETED", "evaluation_date": "2026-08-25",
                "candidate_state_evaluation_date": "2026-08-25",
                "candidate_state_generated": True,
                "decisions": [
                    item("USR-001", "PASS", "VERIFIED", "RECORD", "STABLE_PASS"),
                    item("USR-002", "PASS", "VERIFIED", "RECORD", "CONTROL_RECOVERY"),
                    item("SVC-001", "APPROVED_EXCEPTION", "VERIFIED", "REVIEW", "STABLE_APPROVED_EXCEPTION"),
                    item("USR-004", "FAIL", "VERIFIED", "ESCALATE", "PERSISTENT_CONTROL_FAILURE"),
                ],
                "integrity_results": [
                    {"subject_id": subject, "status": "VERIFIED", "mismatched_components": []}
                    for subject in ("USR-001", "USR-002", "SVC-001", "USR-004")
                ],
                "missing_prior_subject_ids": [], "assurance_status": "verified",
                "failure_stage": None, "failure_reason": None,
            },
            "events": [
                {"event_type": "CONTROL_RECOVERY_RECORDED"},
                {"event_type": "CONTROL_FAILURE_CONTINUES"},
            ],
            "proposed_operations": [
                {"operation": "COMMENT_ISSUE"}, {"operation": "CLOSE_ISSUE"}
            ],
            "executed_operations": [],
            "workflow_integration": {
                "mode": "DRY_RUN", "live_requested": False,
                "live_authorized": False, "live_job_status": "SKIPPED",
            },
            "publication": {
                "status": "WITHHELD", "decision": "DO_NOT_PROMOTE",
                "reason": "Dry-run governance events remain pending authorized live processing.",
                "candidate_state_available": True, "candidate_promoted": False,
                "upload_status": "SKIPPED", "authoritative_artifact_id": None,
            },
            "workflow_conclusion": "success",
            "generated_at": datetime(2026, 8, 25, 4, 0, tzinfo=timezone.utc),
        }
        values.update(changes)
        return self.build(**values)

    def test_prior_state_found_metadata(self):
        prior = self.diagnostic()["prior_state"]
        self.assertEqual(
            ("FOUND", "32799613802", "9546047131", "2026-08-22"),
            (prior["status"], prior["source_run_id"], prior["artifact_id"], prior["evaluation_date"]),
        )

    def test_absent_and_unavailable_are_distinct(self):
        first = self.diagnostic(prior_state={"status": "ABSENT", "reason": "No state."})
        failed = self.diagnostic(
            prior_state={"status": "UNAVAILABLE", "reason": "Download failed."},
            assurance_observation={"status": "NOT_REACHED", "failure_stage": "PRIOR_STATE_RETRIEVAL", "failure_reason": "Download failed."},
            events=[], proposed_operations=[],
            publication={"status": "NOT_REACHED", "decision": None, "reason": None},
            workflow_conclusion="failure",
        )
        self.assertEqual("ABSENT", first["prior_state"]["status"])
        self.assertEqual("UNAVAILABLE", failed["prior_state"]["status"])
        self.assertEqual("PRIOR_STATE_RETRIEVAL", failed["result"]["failed_stage"])
        self.assertEqual("NOT_REACHED", failed["evaluation"]["status"])

    def test_counts_keep_governance_integrity_action_and_transition_separate(self):
        evaluation = self.diagnostic()["evaluation"]
        self.assertEqual(4, evaluation["subject_count"])
        self.assertEqual({"PASS": 2, "FAIL": 1, "APPROVED_EXCEPTION": 1, "NOT_APPLICABLE": 0}, evaluation["governance_outcomes"])
        self.assertEqual({"VERIFIED": 4, "MISMATCH": 0}, evaluation["integrity_statuses"])
        self.assertEqual({"RECORD": 2, "REVIEW": 1, "ESCALATE": 1, "HALT_TRUST": 0}, evaluation["assurance_actions"])
        self.assertEqual({
            "CONTROL_RECOVERY": 1, "PERSISTENT_CONTROL_FAILURE": 1,
            "STABLE_APPROVED_EXCEPTION": 1, "STABLE_PASS": 1,
        }, evaluation["transitions"])

    def test_events_and_proposed_operations_are_aggregated(self):
        data = self.diagnostic()
        self.assertEqual({"CONTROL_FAILURE_CONTINUES": 1, "CONTROL_RECOVERY_RECORDED": 1}, data["events"]["types"])
        self.assertEqual(2, data["events"]["count"])
        self.assertEqual({"CLOSE_ISSUE": 1, "COMMENT_ISSUE": 1}, data["workflow_integration"]["proposed_operation_types"])
        self.assertEqual(0, data["workflow_integration"]["executed_operation_count"])

    def test_authorized_live_keeps_executed_operations_separate(self):
        data = self.diagnostic(
            executed_operations=[{"operation": "COMMENT_ISSUE"}, {"operation": "COMMENT_ISSUE"}, {"operation": "CLOSE_ISSUE"}],
            workflow_integration={"mode": "LIVE", "live_requested": True, "live_authorized": True, "live_job_status": "SUCCESS"},
            publication={
                "status": "PROMOTED", "decision": "PROMOTE",
                "reason": "Authorized live governance processing completed successfully.",
                "candidate_state_available": True, "candidate_promoted": True,
                "upload_status": "SUCCESS", "authoritative_artifact_id": "9546047131",
            },
        )
        self.assertTrue(data["workflow_integration"]["live_authorized"])
        self.assertEqual({"CLOSE_ISSUE": 1, "COMMENT_ISSUE": 2}, data["workflow_integration"]["executed_operation_types"])
        self.assertEqual("9546047131", data["publication"]["authoritative_artifact_id"])

    def test_run_14_equivalent_describes_recovery_persistence_and_promotion(self):
        data = self.diagnostic(
            executed_operations=[
                {"operation": "COMMENT_ISSUE"},
                {"operation": "CLOSE_ISSUE"},
                {"operation": "COMMENT_ISSUE"},
            ],
            workflow_integration={
                "mode": "LIVE",
                "live_requested": True,
                "live_authorized": True,
                "live_job_status": "SUCCESS",
            },
            publication={
                "status": "PROMOTED",
                "decision": "PROMOTE",
                "reason": "Authorized live governance processing completed successfully.",
                "candidate_state_available": True,
                "candidate_promoted": True,
                "upload_status": "SUCCESS",
                "authoritative_artifact_id": "9546047131",
            },
        )

        self.assertEqual(1, data["evaluation"]["transitions"]["CONTROL_RECOVERY"])
        self.assertEqual(
            1,
            data["evaluation"]["transitions"]["PERSISTENT_CONTROL_FAILURE"],
        )
        self.assertEqual(3, data["workflow_integration"]["executed_operation_count"])
        self.assertTrue(data["publication"]["candidate_promoted"])

    def test_run_15_equivalent_describes_stable_pass_pending_persistence(self):
        decisions = [
            item("USR-001", "PASS", "VERIFIED", "RECORD", "STABLE_PASS"),
            item("USR-002", "PASS", "VERIFIED", "RECORD", "STABLE_PASS"),
            item(
                "SVC-001",
                "APPROVED_EXCEPTION",
                "VERIFIED",
                "REVIEW",
                "STABLE_APPROVED_EXCEPTION",
            ),
            item(
                "USR-004",
                "FAIL",
                "VERIFIED",
                "ESCALATE",
                "PERSISTENT_CONTROL_FAILURE",
            ),
        ]
        assurance_observation = {
            "status": "COMPLETED",
            "evaluation_date": "2026-08-25",
            "candidate_state_evaluation_date": "2026-08-25",
            "candidate_state_generated": True,
            "decisions": decisions,
            "integrity_results": [
                {
                    "subject_id": decision["subject_id"],
                    "status": "VERIFIED",
                    "mismatched_components": [],
                }
                for decision in decisions
            ],
            "missing_prior_subject_ids": [],
            "assurance_status": "verified",
            "failure_stage": None,
            "failure_reason": None,
        }
        data = self.diagnostic(
            assurance_observation=assurance_observation,
            events=[{"event_type": "CONTROL_FAILURE_CONTINUES"}],
            proposed_operations=[{"operation": "COMMENT_ISSUE"}],
        )

        self.assertEqual(2, data["evaluation"]["transitions"]["STABLE_PASS"])
        self.assertEqual(1, data["events"]["count"])
        self.assertEqual(1, data["workflow_integration"]["proposed_operation_count"])
        self.assertEqual(0, data["workflow_integration"]["executed_operation_count"])
        self.assertEqual("DO_NOT_PROMOTE", data["publication"]["decision"])
        self.assertFalse(data["publication"]["candidate_promoted"])

    def test_failed_live_and_approved_but_failed_upload_are_described(self):
        data = self.diagnostic(
            workflow_integration={"mode": "LIVE", "live_requested": True, "live_authorized": True, "live_job_status": "FAILED"},
            publication={
                "status": "FAILED", "decision": "PROMOTE",
                "reason": "Existing publication reason.", "candidate_state_available": True,
                "candidate_promoted": False, "upload_status": "FAILED",
                "authoritative_artifact_id": None,
            },
            workflow_conclusion="failure",
        )
        self.assertEqual("FAILED", data["workflow_integration"]["live_job_status"])
        self.assertEqual("PROMOTE", data["publication"]["decision"])
        self.assertFalse(data["publication"]["candidate_promoted"])

    def test_integrity_halt_has_subject_component_metadata(self):
        observation = {
            "status": "COMPLETED", "evaluation_date": "2026-08-25",
            "candidate_state_generated": False,
            "decisions": [item("USR-002", "PASS", "MISMATCH", "HALT_TRUST", "STABLE_PASS")],
            "integrity_results": [{"subject_id": "USR-002", "status": "MISMATCH", "mismatched_components": ["evidence_artifact"]}],
            "missing_prior_subject_ids": [], "assurance_status": "integrity_halt",
            "failure_stage": "EVIDENCE_INTEGRITY", "failure_reason": "Evidence integrity returned MISMATCH.",
        }
        data = self.diagnostic(assurance_observation=observation, workflow_conclusion="failure")
        self.assertTrue(data["result"]["integrity_halt"])
        self.assertEqual([{
            "subject_id": "USR-002", "mismatched_components": ["evidence_artifact"],
            "assurance_action": "HALT_TRUST",
        }], data["result"]["integrity_halt_details"])

    def test_publication_reason_is_verbatim_and_markdown_escaped(self):
        reason = "Policy reason | unchanged\nsecond line"
        data = self.diagnostic(publication={
            "status": "WITHHELD", "decision": "DO_NOT_PROMOTE", "reason": reason,
            "candidate_state_available": True, "candidate_promoted": False,
            "upload_status": "SKIPPED", "authoritative_artifact_id": None,
        })
        self.assertEqual(reason, data["publication"]["reason"])
        self.assertIn("Policy reason \\| unchanged second line", self.render(data))

    def test_serialization_is_deterministic_and_excludes_sensitive_data(self):
        with TemporaryDirectory() as directory:
            one = self.write(self.diagnostic(), Path(directory) / "one.json").read_bytes()
            two = self.write(self.diagnostic(), Path(directory) / "two.json").read_bytes()
        self.assertEqual(one, two)
        self.assertEqual("1.0", json.loads(one)["schema_version"])
        text = one.decode().lower()
        for forbidden in ("github_token", "gh_token", "credential", "secret", "environment_dump", "evidence_payload", "file_contents", "sha256", "raw_api_response"):
            self.assertNotIn(forbidden, text)

    def test_summary_has_separate_lifecycle_sections(self):
        summary = self.render(self.diagnostic())
        for heading in (
            "## Trusted-State Baseline", "## Governance Outcomes",
            "## Integrity Status", "## Assurance Actions",
            "## Historical Transitions", "## Governance Events",
            "## Workflow Operations", "## Trusted-State Publication",
            "## Final Result",
        ):
            self.assertIn(heading, summary)

    def test_unresolved_history_is_separate_from_point_in_time_evaluation(self):
        data = self.diagnostic(
            trusted_history={
                "lineage_id": "ACP-001-03-synthetic-assurance",
                "lineage_status": "ESTABLISHED",
                "status": "ABSENT",
                "historical_comparison_allowed": False,
                "issue_operations_allowed": False,
                "publication_allowed": False,
                "recovery_required": True,
                "failure_stage": "ARTIFACT_DOWNLOAD",
                "reason": "Previously established authoritative history is absent.",
            },
            assurance_observation={
                "status": "COMPLETED",
                "evaluation_date": "2026-08-25",
                "candidate_state_generated": False,
                "decisions": [item("USR-002", "PASS", "VERIFIED", "RECORD", None)],
                "integrity_results": [
                    {"subject_id": "USR-002", "status": "VERIFIED", "mismatched_components": []}
                ],
                "missing_prior_subject_ids": [],
                "assurance_status": "history_unresolved",
                "failure_stage": "TRUSTED_HISTORY_RESOLUTION",
                "failure_reason": "Previously established authoritative history is absent.",
            },
            events=[],
            proposed_operations=[],
            publication={
                "status": "WITHHELD",
                "decision": "DO_NOT_PROMOTE",
                "reason": "Trusted history is unresolved for an established lineage; recovery is required before publication.",
                "candidate_state_available": False,
                "candidate_promoted": False,
                "upload_status": "SKIPPED",
                "authoritative_artifact_id": None,
            },
            workflow_conclusion="failure",
        )

        self.assertEqual("COMPLETED", data["evaluation"]["status"])
        self.assertEqual("ABSENT", data["trusted_history"]["status"])
        self.assertFalse(data["trusted_history"]["historical_comparison_allowed"])
        self.assertTrue(data["trusted_history"]["recovery_required"])
        self.assertEqual("ARTIFACT_DOWNLOAD", data["trusted_history"]["failure_stage"])
        summary = self.render(data)
        self.assertIn("## Trusted-History Resolution", summary)
        self.assertIn("Point-in-time evaluation only", summary)
        self.assertIn("ARTIFACT_DOWNLOAD", summary)


class CliObservabilityHandoffTests(unittest.TestCase):
    def healthy_resolution(self):
        return SimpleNamespace(
            historical_comparison_allowed=True,
            publication_allowed=True,
        )

    def args(self):
        return Namespace(
            evaluation_date=None,
            output_directory=Path("runtime"),
            previous_state=Path("prior.json"),
            state_resolution=Path("resolution.json"),
        )

    def test_success_handoff_preserves_normal_exit_and_summary(self):
        from automation import cli

        result = SimpleNamespace(succeeded=True, summary="existing summary\n")
        with (
            patch.object(cli, "parse_args", return_value=self.args()),
            patch.object(cli, "run_pipeline", return_value=result),
            patch.object(cli, "load_state_resolution", return_value=self.healthy_resolution()),
            patch.object(cli, "classify_pipeline_status", return_value="verified"),
            patch.object(cli, "write_assurance_observation") as observe,
            patch.object(cli, "_write_pipeline_status"),
            patch.dict("os.environ", {}, clear=True),
            patch("builtins.print") as printed,
        ):
            cli.main()

        observe.assert_called_once_with(
            result, "verified", Path("runtime") / "assurance-observation.json"
        )
        printed.assert_called_once_with("existing summary\n", end="")

    def test_integrity_halt_handoff_preserves_exit_code(self):
        from automation import cli

        result = SimpleNamespace(succeeded=False, summary="halt summary\n")
        with (
            patch.object(cli, "parse_args", return_value=self.args()),
            patch.object(cli, "run_pipeline", return_value=result),
            patch.object(cli, "load_state_resolution", return_value=self.healthy_resolution()),
            patch.object(
                cli, "classify_pipeline_status", return_value="integrity_halt"
            ),
            patch.object(cli, "write_assurance_observation") as observe,
            patch.object(cli, "_write_pipeline_status"),
            patch.dict("os.environ", {}, clear=True),
            self.assertRaises(SystemExit) as raised,
        ):
            cli.main()

        self.assertEqual(1, raised.exception.code)
        observe.assert_called_once()

    def test_pipeline_failure_is_observed_and_propagates(self):
        from automation import cli

        with (
            patch.object(cli, "parse_args", return_value=self.args()),
            patch.object(cli, "run_pipeline", side_effect=ValueError("bounded")),
            patch.object(cli, "load_state_resolution", return_value=self.healthy_resolution()),
            patch.object(cli, "write_failure_observation") as observe,
            self.assertRaisesRegex(ValueError, "bounded"),
        ):
            cli.main()

        observe.assert_called_once_with(
            "ASSURANCE_EXECUTION",
            "ValueError: assurance pipeline execution failed.",
            Path("runtime") / "assurance-observation.json",
        )

    def test_observation_write_failure_does_not_fail_successful_pipeline(self):
        from automation import cli

        result = SimpleNamespace(succeeded=True, summary="existing summary\n")
        with (
            patch.object(cli, "parse_args", return_value=self.args()),
            patch.object(cli, "run_pipeline", return_value=result),
            patch.object(cli, "load_state_resolution", return_value=self.healthy_resolution()),
            patch.object(cli, "classify_pipeline_status", return_value="verified"),
            patch.object(
                cli,
                "write_assurance_observation",
                side_effect=OSError("diagnostics unavailable"),
            ),
            patch.object(cli, "_write_pipeline_status"),
            patch.dict("os.environ", {}, clear=True),
            patch("builtins.print"),
        ):
            cli.main()

    def test_observation_write_failure_does_not_mask_pipeline_failure(self):
        from automation import cli

        with (
            patch.object(cli, "parse_args", return_value=self.args()),
            patch.object(cli, "run_pipeline", side_effect=ValueError("original")),
            patch.object(cli, "load_state_resolution", return_value=self.healthy_resolution()),
            patch.object(
                cli,
                "write_failure_observation",
                side_effect=OSError("diagnostics unavailable"),
            ),
            self.assertRaisesRegex(ValueError, "original"),
        ):
            cli.main()


class WorkflowDiagnosticTests(unittest.TestCase):
    def workflow(self):
        return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)

    def test_diagnostics_is_always_downstream_and_non_authoritative(self):
        workflow = self.workflow()
        diagnostics = workflow["jobs"]["lifecycle-diagnostics"]
        self.assertEqual(["assurance", "live-governance-workflow", "trusted-state-publication"], diagnostics["needs"])
        self.assertIn("always()", diagnostics["if"])
        self.assertEqual("true", diagnostics["continue-on-error"])
        self.assertNotIn("needs", workflow["jobs"]["assurance"])
        self.assertEqual("assurance", workflow["jobs"]["live-governance-workflow"]["needs"])
        self.assertEqual(["assurance", "live-governance-workflow"], workflow["jobs"]["trusted-state-publication"]["needs"])

    def test_diagnostics_permissions_and_seven_day_artifact(self):
        diagnostics = self.workflow()["jobs"]["lifecycle-diagnostics"]
        self.assertEqual({"actions": "read", "contents": "read"}, diagnostics["permissions"])
        upload = next(step for step in diagnostics["steps"] if step.get("with", {}).get("name") == "synthetic-governance-lifecycle-diagnostics-${{ github.run_id }}")
        self.assertEqual("7", upload["with"]["retention-days"])
        self.assertEqual("warn", upload["with"]["if-no-files-found"])

    def test_live_execution_metadata_is_separate_from_dry_run_plan(self):
        live = self.workflow()["jobs"]["live-governance-workflow"]
        execution = next(
            step
            for step in live["steps"]
            if step["name"] == "Execute authorized GitHub governance workflow"
        )
        metadata = next(
            step
            for step in live["steps"]
            if step["name"] == "Surface executed operation metadata"
        )
        output_path = "generated-assurance/executed-github-issue-operations.json"
        self.assertIn(f"--output {output_path}", execution["run"])
        self.assertIn(output_path, metadata["run"])

    def test_existing_permissions_gates_pins_and_artifacts_remain(self):
        workflow = self.workflow()
        live = workflow["jobs"]["live-governance-workflow"]
        publication = workflow["jobs"]["trusted-state-publication"]
        self.assertEqual({"actions": "read", "contents": "read", "issues": "read"}, workflow["permissions"])
        self.assertEqual({"actions": "read", "contents": "read", "issues": "write"}, live["permissions"])
        self.assertIn("github.event_name == 'workflow_dispatch'", live["if"])
        self.assertIn("inputs.live_issue_workflow == true", live["if"])
        self.assertEqual({"actions": "read", "contents": "read"}, publication["permissions"])
        self.assertIn("needs.assurance.outputs.assurance_status", publication["if"])
        approved = {
            "actions/checkout": "de0fac2e4500dabe0009e67214ff5f5447ce83dd",
            "actions/setup-python": "a309ff8b426b58ec0e2a45f0f869d46889d02405",
            "actions/upload-artifact": "b7c566a772e6b6bfb58ed0dc250532a479d7789f",
            "actions/download-artifact": "37930b1c2abaa49bbe596cd826c3c89aef350131",
        }
        for line in WORKFLOW.read_text(encoding="utf-8").splitlines():
            if "uses: actions/" in line:
                action, reference = line.split("uses: ", 1)[1].split(" #", 1)[0].split("@", 1)
                self.assertEqual(approved[action], reference)
        runtime = next(step for step in workflow["jobs"]["assurance"]["steps"] if step.get("with", {}).get("name") == "synthetic-governance-assurance-${{ github.run_id }}")
        state = next(step for step in publication["steps"] if step.get("with", {}).get("name") == "trusted-assurance-state")
        self.assertEqual(("7", "examples/machine-readable-control/generated-assurance/"), (runtime["with"]["retention-days"], runtime["with"]["path"]))
        self.assertEqual(("30", "true"), (state["with"]["retention-days"], state["with"]["overwrite"]))
        self.assertEqual("${{ steps.state-publication.outputs.state_ready == 'true' }}", state["if"])
        self.assertEqual("trusted-state-upload", state["id"])


if __name__ == "__main__":
    unittest.main()
