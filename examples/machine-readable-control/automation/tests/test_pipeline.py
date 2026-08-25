import json
import re
import subprocess
import unittest
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from assurance.decision import ESCALATE, HALT_TRUST, RECORD, REVIEW
from evidence.integrity import IntegrityVerification, MISMATCH, VERIFIED
from automation.pipeline import (
    build_assurance_decision,
    complete_pipeline,
    prepare_pipeline,
    run_pipeline,
)


EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = EXAMPLE_ROOT.parents[1]
WORKFLOW_PATH = REPOSITORY_ROOT / ".github" / "workflows" / "governance-assurance.yml"
EVALUATION_DATE = date(2026, 8, 22)
GENERATED_AT = datetime(2026, 8, 22, 15, 0, tzinfo=timezone.utc)
APPROVED_ACTIONS = {
    "actions/checkout": (
        "de0fac2e4500dabe0009e67214ff5f5447ce83dd",
        "v6.0.2",
    ),
    "actions/setup-python": (
        "a309ff8b426b58ec0e2a45f0f869d46889d02405",
        "v6.2.0",
    ),
    "actions/upload-artifact": (
        "b7c566a772e6b6bfb58ed0dc250532a479d7789f",
        "v6.0.0",
    ),
    "actions/download-artifact": (
        "37930b1c2abaa49bbe596cd826c3c89aef350131",
        "v7.0.0",
    ),
}


class PipelineIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.output_directory = Path(self.temporary_directory.name) / "run"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def run_example(self):
        return run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory,
            generated_at=GENERATED_AT,
        )

    def test_full_synthetic_pipeline_executes_successfully(self):
        result = self.run_example()

        self.assertTrue(result.succeeded)
        self.assertEqual(5, len(result.decisions))

    def test_all_subjects_receive_existing_validator_outcomes(self):
        result = self.run_example()

        self.assertEqual(
            ["PASS", "PASS", "PASS", "APPROVED_EXCEPTION", "FAIL"],
            [decision.governance_outcome for decision in result.decisions],
        )

    def test_evidence_is_generated_from_validator_outcomes(self):
        prepared = prepare_pipeline(
            EVALUATION_DATE, self.output_directory, GENERATED_AT
        )

        self.assertEqual(
            [item.outcome for item in prepared.validation_results],
            [record["result"]["outcome"] for record in prepared.evidence_records],
        )
        self.assertTrue(all(path.exists() for path in prepared.evidence_paths))

    def test_generated_evidence_verifies_successfully(self):
        result = self.run_example()

        self.assertEqual(
            [VERIFIED] * 5,
            [verification.status for verification in result.integrity_results],
        )

    def test_assurance_actions_come_from_existing_decision_engine(self):
        result = self.run_example()

        self.assertEqual(
            [RECORD, RECORD, RECORD, REVIEW, ESCALATE],
            [decision.assurance_action for decision in result.decisions],
        )

    def test_not_applicable_verified_is_delegated_to_record_action(self):
        record = {
            "subject": {"account_id": "USR-OUT-OF-SCOPE"},
            "result": {"outcome": "NOT_APPLICABLE"},
        }
        verification = IntegrityVerification(VERIFIED, {}, [])

        decision = build_assurance_decision(
            "ACP-001-03", record, verification, EVALUATION_DATE
        )

        self.assertEqual("NOT_APPLICABLE", decision.governance_outcome)
        self.assertEqual(RECORD, decision.assurance_action)

    def test_verified_fail_does_not_fail_pipeline(self):
        result = self.run_example()

        failures = [
            decision
            for decision in result.decisions
            if decision.governance_outcome == "FAIL"
        ]
        self.assertEqual([ESCALATE], [item.assurance_action for item in failures])
        self.assertTrue(result.succeeded)

    def test_explicit_evaluation_date_is_honored(self):
        result = self.run_example()

        self.assertEqual(
            ["2026-08-22"] * 5,
            [decision.evaluation_date for decision in result.decisions],
        )

    def test_default_evaluation_date_uses_current_utc_date(self):
        local_time = datetime(
            2026, 8, 22, 18, 30, tzinfo=timezone(timedelta(hours=-7))
        )
        result = run_pipeline(
            output_directory=self.output_directory,
            generated_at=local_time,
        )

        self.assertEqual("2026-08-23", result.evaluation_date)

    def test_runtime_outputs_are_ignored_by_git(self):
        paths = [
            EXAMPLE_ROOT / "generated-assurance" / "evidence" / "record.json",
            EXAMPLE_ROOT / "generated-assurance" / "evidence" / "record.json.sha256",
            EXAMPLE_ROOT / "generated-assurance" / "assurance-decisions.json",
            EXAMPLE_ROOT / "generated-assurance" / "run-summary.md",
        ]

        for path in paths:
            completed = subprocess.run(
                [
                    "git",
                    "-c",
                    f"safe.directory={REPOSITORY_ROOT.as_posix()}",
                    "-C",
                    str(REPOSITORY_ROOT),
                    "check-ignore",
                    "--quiet",
                    str(path),
                ],
                check=False,
            )
            self.assertEqual(0, completed.returncode)

    def test_human_readable_summary_contains_subjects_and_aggregate_counts(self):
        result = self.run_example()

        self.assertIn("# Governance Assurance Run Summary", result.summary)
        self.assertIn("USR-002", result.summary)
        self.assertIn("| None |", result.summary)
        self.assertIn("| FAIL | 1 |", result.summary)
        self.assertIn("| ESCALATE | 1 |", result.summary)
        self.assertIn("| HALT_TRUST | 0 |", result.summary)

    def test_structured_decisions_serialize_and_parse(self):
        result = self.run_example()

        parsed = json.loads(result.decisions_path.read_text(encoding="utf-8"))
        self.assertEqual(5, len(parsed))
        self.assertEqual("USR-001", parsed[0]["subject_id"])
        self.assertEqual("RECORD", parsed[0]["assurance_action"])

    def test_existing_exception_traceability_remains_in_evidence(self):
        prepared = prepare_pipeline(
            EVALUATION_DATE, self.output_directory, GENERATED_AT
        )

        self.assertEqual("EXC-001", prepared.evidence_records[3]["exception"]["exception_id"])
        self.assertTrue(
            prepared.evidence_records[3]["exception"]["valid_at_evaluation_time"]
        )


class IntegrityFailureTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.output_directory = Path(self.temporary_directory.name) / "run"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_integrity_mismatch_halts_trust_and_fails_pipeline(self):
        prepared = prepare_pipeline(
            EVALUATION_DATE, self.output_directory, GENERATED_AT
        )
        prepared.evidence_paths[0].write_text(
            prepared.evidence_paths[0].read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )

        result = complete_pipeline(prepared)

        self.assertEqual(MISMATCH, result.integrity_results[0].status)
        self.assertEqual(HALT_TRUST, result.decisions[0].assurance_action)
        self.assertFalse(result.succeeded)


class WorkflowConfigurationTests(unittest.TestCase):
    def workflow(self):
        return yaml.load(
            WORKFLOW_PATH.read_text(encoding="utf-8"),
            Loader=yaml.BaseLoader,
        )

    def action_references(self):
        references = []
        pattern = re.compile(
            r"^\s*-?\s*uses:\s*([^@\s]+)@([^\s#]+)(?:\s+#\s*(\S+))?\s*$"
        )
        for line in WORKFLOW_PATH.read_text(encoding="utf-8").splitlines():
            match = pattern.match(line)
            if match:
                references.append(match.groups())
        return references

    def test_external_actions_use_only_approved_immutable_release_pins(self):
        references = self.action_references()

        self.assertEqual(
            Counter(
                {
                    "actions/checkout": 4,
                    "actions/setup-python": 4,
                    "actions/upload-artifact": 3,
                    "actions/download-artifact": 3,
                }
            ),
            Counter(action for action, _, _ in references),
        )
        for action, reference, release_comment in references:
            self.assertIn(action, APPROVED_ACTIONS)
            approved_sha, approved_release = APPROVED_ACTIONS[action]
            self.assertRegex(reference, r"^[0-9a-f]{40}$")
            self.assertEqual(approved_sha, reference)
            self.assertEqual(approved_release, release_comment)

    def test_each_action_uses_one_consistent_approved_sha(self):
        references = self.action_references()

        for action, (approved_sha, _) in APPROVED_ACTIONS.items():
            action_references = {
                reference
                for referenced_action, reference, _ in references
                if referenced_action == action
            }
            self.assertEqual({approved_sha}, action_references)

    def test_artifact_producer_and_consumer_configuration_is_preserved(self):
        workflow = self.workflow()
        assurance_steps = workflow["jobs"]["assurance"]["steps"]
        live_steps = workflow["jobs"]["live-governance-workflow"]["steps"]
        publication_steps = workflow["jobs"]["trusted-state-publication"]["steps"]
        runtime_upload = next(
            step
            for step in assurance_steps
            if step["name"] == "Upload synthetic demonstration artifacts"
        )
        live_download = next(
            step
            for step in live_steps
            if step["name"] == "Download generated governance events"
        )
        publication_download = next(
            step
            for step in publication_steps
            if step["name"] == "Download candidate trusted state"
        )
        state_upload = next(
            step
            for step in publication_steps
            if step["name"] == "Upload trusted assurance state"
        )

        runtime_name = "synthetic-governance-assurance-${{ github.run_id }}"
        runtime_path = "examples/machine-readable-control/generated-assurance/"
        download_path = "examples/machine-readable-control/generated-assurance"
        self.assertEqual(runtime_name, runtime_upload["with"]["name"])
        self.assertEqual(runtime_path, runtime_upload["with"]["path"])
        self.assertEqual("warn", runtime_upload["with"]["if-no-files-found"])
        self.assertEqual("7", runtime_upload["with"]["retention-days"])
        for download in (live_download, publication_download):
            self.assertEqual(runtime_name, download["with"]["name"])
            self.assertEqual(download_path, download["with"]["path"])
        self.assertEqual("trusted-assurance-state", state_upload["with"]["name"])
        self.assertEqual(
            "${{ runner.temp }}/trusted-state-publication/trusted-assurance-state.json",
            state_upload["with"]["path"],
        )
        self.assertEqual("error", state_upload["with"]["if-no-files-found"])
        self.assertEqual("30", state_upload["with"]["retention-days"])
        self.assertEqual("true", state_upload["with"]["overwrite"])

    def test_workflow_has_required_triggers_and_path_filters(self):
        workflow = self.workflow()
        triggers = workflow["on"]

        self.assertIn("workflow_dispatch", triggers)
        self.assertEqual("0 6 * * 1", triggers["schedule"][0]["cron"])
        self.assertEqual(
            [
                "examples/machine-readable-control/controls/**",
                "examples/machine-readable-control/validation/**",
                "examples/machine-readable-control/evidence/**",
                "examples/machine-readable-control/assurance/**",
                "examples/machine-readable-control/automation/**",
                "examples/machine-readable-control/events/**",
                "examples/machine-readable-control/integrations/**",
                "examples/machine-readable-control/sample-data/**",
                ".github/workflows/governance-assurance.yml",
            ],
            triggers["push"]["paths"],
        )

    def test_manual_live_input_is_boolean_and_defaults_to_false(self):
        workflow = self.workflow()
        live_input = workflow["on"]["workflow_dispatch"]["inputs"][
            "live_issue_workflow"
        ]

        self.assertEqual("boolean", live_input["type"])
        self.assertEqual("true", live_input["required"])
        self.assertEqual("false", live_input["default"])

    def test_workflow_uses_bounded_read_permissions_and_artifact_retention(self):
        workflow = self.workflow()

        self.assertEqual(
            {"actions": "read", "contents": "read", "issues": "read"},
            workflow["permissions"],
        )
        self.assertNotIn("write", workflow["permissions"].values())
        assurance_steps = workflow["jobs"]["assurance"]["steps"]
        assurance_uploads = [
            step
            for step in assurance_steps
            if step.get("uses", "").startswith("actions/upload-artifact@")
        ]
        self.assertEqual(1, len(assurance_uploads))
        runtime_upload = assurance_uploads[0]
        self.assertEqual("7", runtime_upload["with"]["retention-days"])
        self.assertIn("generated-assurance", runtime_upload["with"]["path"])
        self.assertNotIn("!", runtime_upload["with"]["path"])

        publication_job = workflow["jobs"]["trusted-state-publication"]
        self.assertEqual(
            {"actions": "read", "contents": "read"},
            publication_job["permissions"],
        )
        self.assertNotIn("issues", publication_job["permissions"])
        state_upload = next(
            step
            for step in publication_job["steps"]
            if step.get("uses", "").startswith("actions/upload-artifact@")
        )
        self.assertEqual("trusted-assurance-state", state_upload["with"]["name"])
        self.assertEqual("30", state_upload["with"]["retention-days"])
        self.assertIn("state_ready == 'true'", state_upload["if"])

    def test_workflow_retrieves_state_before_pipeline_execution(self):
        workflow = self.workflow()
        steps = workflow["jobs"]["assurance"]["steps"]
        names = [step["name"] for step in steps]

        self.assertLess(
            names.index("Retrieve prior trusted assurance state"),
            names.index("Run synthetic assurance pipeline"),
        )

    def test_trusted_state_retrieval_uses_paginated_file_backed_api_data(self):
        workflow = self.workflow()
        retrieval = next(
            step
            for step in workflow["jobs"]["assurance"]["steps"]
            if step["name"] == "Retrieve prior trusted assurance state"
        )
        script = retrieval["run"]

        self.assertEqual(2, script.count("gh api --paginate --slurp"))
        self.assertIn('> "$workflow_runs_file"', script)
        self.assertIn('> "$artifacts_file"', script)
        self.assertIn('--slurpfile runs "$workflow_runs_file"', script)
        self.assertIn('--slurpfile artifacts "$artifacts_file"', script)
        self.assertNotIn('workflow_runs="$(', script)
        self.assertNotIn('artifacts="$(', script)
        self.assertNotIn("--argjson runs", script)
        self.assertNotIn("--argjson artifacts", script)

    def test_retrieval_classifies_raw_state_without_inferring_first_run(self):
        workflow = self.workflow()
        steps = workflow["jobs"]["assurance"]["steps"]
        retrieval = next(
            step for step in steps
            if step["name"] == "Retrieve prior trusted assurance state"
        )
        resolution = next(
            step for step in steps
            if step["name"] == "Resolve trusted assurance history"
        )

        for status in ("FOUND", "ABSENT", "EXPIRED", "UNAVAILABLE", "INELIGIBLE"):
            self.assertIn(status, retrieval["run"])
        self.assertNotIn("NOT_FOUND", retrieval["run"])
        self.assertIn("automation.state_resolution", resolution["run"])
        self.assertIn("trusted-state-lineage.json", resolution["run"])
        self.assertLess(
            [step["name"] for step in steps].index("Resolve trusted assurance history"),
            [step["name"] for step in steps].index("Run synthetic assurance pipeline"),
        )

    def test_newest_artifact_selection_has_deterministic_id_tie_breaker(self):
        retrieval = next(
            step
            for step in self.workflow()["jobs"]["assurance"]["steps"]
            if step["name"] == "Retrieve prior trusted assurance state"
        )

        self.assertIn("sort_by([.created_at, .id])", retrieval["run"])

    def test_unresolved_history_cannot_reach_issue_writes_or_publication(self):
        workflow = self.workflow()
        assurance = workflow["jobs"]["assurance"]
        live = workflow["jobs"]["live-governance-workflow"]
        publication = workflow["jobs"]["trusted-state-publication"]
        publication_step = next(
            step for step in publication["steps"]
            if step["name"] == "Evaluate trusted state publication"
        )

        self.assertEqual(
            "${{ steps.trusted-history.outputs.issue_operations_allowed }}",
            assurance["outputs"]["issue_operations_allowed"],
        )
        self.assertIn(
            "needs.assurance.outputs.issue_operations_allowed == 'true'",
            live["if"],
        )
        self.assertIn(
            "--trusted-history-publication-allowed",
            publication_step["run"],
        )
        self.assertIn(
            "needs.assurance.outputs.publication_allowed",
            publication_step["run"],
        )

    def test_workflow_serializes_state_advancement_and_handles_reruns(self):
        workflow = self.workflow()

        self.assertEqual(
            {
                "group": "governance-assurance-${{ github.workflow }}-${{ github.ref }}",
                "cancel-in-progress": "false",
            },
            workflow["concurrency"],
        )
        steps = workflow["jobs"]["assurance"]["steps"]
        state_upload = next(
            step
            for step in workflow["jobs"]["trusted-state-publication"]["steps"]
            if step.get("with", {}).get("retention-days") == "30"
        )
        self.assertEqual("true", state_upload["with"]["overwrite"])
        retrieval = next(
            step
            for step in steps
            if step["name"] == "Retrieve prior trusted assurance state"
        )
        self.assertIn("GITHUB_RUN_ID", retrieval["run"])
        self.assertIn("workflow_run.id != $run_id", retrieval["run"])
        self.assertIn(
            "actions/workflows/governance-assurance.yml/runs", retrieval["run"]
        )

    def test_state_publication_waits_for_dry_run_or_authorized_live_boundary(self):
        workflow = self.workflow()
        publication_job = workflow["jobs"]["trusted-state-publication"]
        publication_step = next(
            step
            for step in publication_job["steps"]
            if step["name"] == "Evaluate trusted state publication"
        )

        self.assertEqual(
            ["assurance", "live-governance-workflow"], publication_job["needs"]
        )
        self.assertIn("always()", publication_job["if"])
        self.assertIn(
            "automation.state_publication", publication_step["run"]
        )
        self.assertIn("github.event_name", publication_step["run"])
        self.assertIn("inputs.live_issue_workflow", publication_step["run"])
        self.assertIn(
            "needs.live-governance-workflow.result", publication_step["run"]
        )
        self.assertIn(
            "needs.assurance.outputs.assurance_status", publication_step["run"]
        )

    def test_workflow_runs_event_tests(self):
        workflow = self.workflow()
        steps = workflow["jobs"]["assurance"]["steps"]
        tests = next(step for step in steps if step["name"] == "Run complete test suite")

        self.assertIn("events/tests", tests["run"])

    def test_workflow_runs_github_integration_tests_and_dry_run(self):
        workflow = self.workflow()
        steps = workflow["jobs"]["assurance"]["steps"]
        tests = next(step for step in steps if step["name"] == "Run complete test suite")
        integration = next(
            step
            for step in steps
            if step["name"] == "Plan GitHub governance workflow operations"
        )

        self.assertIn("integrations/github/tests", tests["run"])
        self.assertIn("integrations.github.cli --dry-run", integration["run"])
        self.assertEqual("${{ github.token }}", integration["env"]["GH_TOKEN"])
        self.assertEqual(
            "${{ always() && steps.trusted-history.outputs.issue_operations_allowed == 'true' && (steps.assurance-pipeline.outputs.assurance_status == 'verified' || steps.assurance-pipeline.outputs.assurance_status == 'integrity_halt') }}",
            integration["if"],
        )
        self.assertEqual("read", workflow["permissions"]["issues"])
        self.assertNotIn(
            "--live", "\n".join(step.get("run", "") for step in steps)
        )

    def test_push_and_schedule_paths_cannot_run_write_capable_job(self):
        workflow = self.workflow()
        live_job = workflow["jobs"]["live-governance-workflow"]

        self.assertIn(
            "github.event_name == 'workflow_dispatch'", live_job["if"]
        )
        self.assertIn("inputs.live_issue_workflow == true", live_job["if"])
        self.assertNotIn("push", live_job["if"])
        self.assertNotIn("schedule", live_job["if"])

    def test_manual_false_cannot_run_write_capable_job(self):
        workflow = self.workflow()
        live_job = workflow["jobs"]["live-governance-workflow"]

        self.assertIn("inputs.live_issue_workflow == true", live_job["if"])
        self.assertNotIn("inputs.live_issue_workflow", live_job.get("env", {}))

    def test_authorized_manual_job_has_bounded_write_permission_and_uses_live_cli(self):
        workflow = self.workflow()
        live_job = workflow["jobs"]["live-governance-workflow"]
        live_step = next(
            step
            for step in live_job["steps"]
            if step["name"] == "Execute authorized GitHub governance workflow"
        )

        self.assertEqual("assurance", live_job["needs"])
        self.assertEqual(
            {"actions": "read", "contents": "read", "issues": "write"},
            live_job["permissions"],
        )
        self.assertIn("integrations.github.cli --live", live_step["run"])
        self.assertEqual("${{ inputs.live_issue_workflow }}", live_step["env"]["LIVE_ISSUE_WORKFLOW"])
        write_jobs = [
            name
            for name, job in workflow["jobs"].items()
            if job.get("permissions", {}).get("issues") == "write"
        ]
        self.assertEqual(["live-governance-workflow"], write_jobs)

    def test_live_job_consumes_assurance_artifact_only_after_plan_is_ready(self):
        workflow = self.workflow()
        assurance = workflow["jobs"]["assurance"]
        live_job = workflow["jobs"]["live-governance-workflow"]
        download = next(
            step
            for step in live_job["steps"]
            if step.get("uses", "").startswith("actions/download-artifact@")
        )

        self.assertEqual(
            "${{ steps.github-dry-run.outcome == 'success' }}",
            assurance["outputs"]["workflow_plan_ready"],
        )
        self.assertEqual(
            "${{ steps.assurance-pipeline.outputs.assurance_status }}",
            assurance["outputs"]["assurance_status"],
        )
        self.assertIn(
            "needs.assurance.outputs.workflow_plan_ready == 'true'",
            live_job["if"],
        )
        self.assertIn(
            "needs.assurance.outputs.assurance_status == 'verified'",
            live_job["if"],
        )
        self.assertIn(
            "needs.assurance.outputs.assurance_status == 'integrity_halt'",
            live_job["if"],
        )
        self.assertEqual(
            "synthetic-governance-assurance-${{ github.run_id }}",
            download["with"]["name"],
        )
        self.assertEqual(
            "examples/machine-readable-control/generated-assurance",
            download["with"]["path"],
        )


class PipelineEventIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.output_directory = self.directory / "run"
        self.previous_state_path = self.directory / "previous-state.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_first_run_without_transitions_produces_no_events(self):
        result = run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory,
            generated_at=GENERATED_AT,
        )

        self.assertEqual([], result.events)
        self.assertEqual([], result.event_paths)

    def test_usr_002_recovery_uses_prior_fail_state_and_records_recovery_event(self):
        self.previous_state_path.write_text(
            json.dumps(
                {
                    "control_id": "ACP-001-03",
                    "evaluation_date": "2026-08-21",
                    "subjects": [
                        {"subject_id": "USR-002", "governance_outcome": "FAIL"},
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory,
            generated_at=GENERATED_AT,
            previous_state_path=self.previous_state_path,
        )

        decision = next(
            item for item in result.decisions if item.subject_id == "USR-002"
        )
        self.assertEqual("PASS", decision.governance_outcome)
        self.assertEqual("FAIL", decision.previous_governance_outcome)
        self.assertEqual("CONTROL_RECOVERY", decision.transition)
        self.assertEqual(
            ["CONTROL_RECOVERY_RECORDED"],
            [item.event_type for item in result.events],
        )

    def test_dry_run_candidate_does_not_consume_recovery_from_prior_state(self):
        prior_state = {
            "control_id": "ACP-001-03",
            "evaluation_date": "2026-08-21",
            "subjects": [
                {"subject_id": "USR-002", "governance_outcome": "FAIL"},
            ],
        }
        self.previous_state_path.write_text(
            json.dumps(prior_state), encoding="utf-8"
        )

        dry_run = run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory / "dry-run",
            generated_at=GENERATED_AT,
            previous_state_path=self.previous_state_path,
        )
        authorized_run = run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory / "authorized-run",
            generated_at=GENERATED_AT,
            previous_state_path=self.previous_state_path,
        )

        self.assertEqual(prior_state, json.loads(self.previous_state_path.read_text()))
        self.assertEqual(
            ["CONTROL_RECOVERY_RECORDED"],
            [item.event_type for item in dry_run.events],
        )
        self.assertEqual(
            ["CONTROL_RECOVERY_RECORDED"],
            [item.event_type for item in authorized_run.events],
        )

    def test_transition_decisions_produce_runtime_event_files(self):
        self.previous_state_path.write_text(
            json.dumps(
                {
                    "control_id": "ACP-001-03",
                    "evaluation_date": "2026-08-21",
                    "subjects": [
                        {"subject_id": "USR-001", "governance_outcome": "FAIL"},
                        {"subject_id": "USR-002", "governance_outcome": "PASS"},
                        {"subject_id": "SVC-001", "governance_outcome": "PASS"},
                        {
                            "subject_id": "USR-004",
                            "governance_outcome": "APPROVED_EXCEPTION",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        result = run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory,
            generated_at=GENERATED_AT,
            previous_state_path=self.previous_state_path,
        )

        self.assertEqual(
            [
                "CONTROL_RECOVERY_RECORDED",
                "EXCEPTION_REVIEW_OPENED",
                "EXCEPTION_LAPSE_ESCALATION",
            ],
            [item.event_type for item in result.events],
        )
        self.assertEqual(3, len(result.event_paths))
        self.assertTrue(all(path.exists() for path in result.event_paths))

    def test_unresolved_history_retains_observations_without_historical_claims(self):
        result = run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory,
            generated_at=GENERATED_AT,
            historical_comparison_allowed=False,
            candidate_state_allowed=False,
        )

        self.assertEqual(
            ["PASS", "PASS", "PASS", "APPROVED_EXCEPTION", "FAIL"],
            [item.governance_outcome for item in result.decisions],
        )
        self.assertTrue(all(item.transition is None for item in result.decisions))
        self.assertEqual([], result.events)
        self.assertIsNone(result.trusted_state_path)
        self.assertFalse(result.historical_comparison_allowed)


class HistoricalComparisonTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = TemporaryDirectory()
        self.directory = Path(self.temporary_directory.name)
        self.output_directory = self.directory / "run"
        self.previous_state_path = self.directory / "previous-state.json"

    def tearDown(self):
        self.temporary_directory.cleanup()

    def write_previous(self, outcomes):
        self.previous_state_path.write_text(
            json.dumps(
                {
                    "control_id": "ACP-001-03",
                    "evaluation_date": "2026-08-21",
                    "subjects": [
                        {"subject_id": subject_id, "governance_outcome": outcome}
                        for subject_id, outcome in outcomes.items()
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def run_with_previous(self, outcomes):
        self.write_previous(outcomes)
        return run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory,
            generated_at=GENERATED_AT,
            previous_state_path=self.previous_state_path,
        )

    def transition_for(self, subject_id, previous_outcome):
        result = self.run_with_previous({subject_id: previous_outcome})
        return next(
            item.transition for item in result.decisions if item.subject_id == subject_id
        )

    def test_first_run_has_no_transitions_and_writes_trusted_state(self):
        result = run_pipeline(
            evaluation_date=EVALUATION_DATE,
            output_directory=self.output_directory,
            generated_at=GENERATED_AT,
        )

        self.assertTrue(all(item.transition is None for item in result.decisions))
        self.assertIsNotNone(result.trusted_state_path)
        self.assertTrue(result.trusted_state_path.exists())

    def test_healthy_authoritative_history_preserves_stable_production_behavior(self):
        result = self.run_with_previous(
            {
                "USR-001": "PASS",
                "USR-002": "PASS",
                "USR-003": "PASS",
                "SVC-001": "APPROVED_EXCEPTION",
                "USR-004": "FAIL",
            }
        )

        self.assertEqual(
            [
                "STABLE_PASS",
                "STABLE_PASS",
                "STABLE_PASS",
                "STABLE_APPROVED_EXCEPTION",
                "PERSISTENT_CONTROL_FAILURE",
            ],
            [item.transition for item in result.decisions],
        )
        self.assertEqual(
            ["CONTROL_FAILURE_CONTINUES"],
            [item.event_type for item in result.events],
        )

    def test_pass_to_fail_is_new_control_failure(self):
        self.assertEqual(
            "NEW_CONTROL_FAILURE", self.transition_for("USR-004", "PASS")
        )

    def test_fail_to_fail_is_persistent_control_failure(self):
        self.assertEqual(
            "PERSISTENT_CONTROL_FAILURE", self.transition_for("USR-004", "FAIL")
        )

    def test_fail_to_pass_is_control_recovery(self):
        self.assertEqual("CONTROL_RECOVERY", self.transition_for("USR-001", "FAIL"))

    def test_approved_exception_to_fail_is_exception_to_failure(self):
        self.assertEqual(
            "EXCEPTION_TO_FAILURE",
            self.transition_for("USR-004", "APPROVED_EXCEPTION"),
        )

    def test_approved_exception_to_pass_is_exception_to_pass(self):
        self.assertEqual(
            "EXCEPTION_TO_PASS",
            self.transition_for("USR-001", "APPROVED_EXCEPTION"),
        )

    def test_pass_to_approved_exception_is_new_approved_exception(self):
        self.assertEqual(
            "NEW_APPROVED_EXCEPTION", self.transition_for("SVC-001", "PASS")
        )

    def test_stable_pass_is_classified(self):
        self.assertEqual("STABLE_PASS", self.transition_for("USR-001", "PASS"))

    def test_stable_approved_exception_is_classified(self):
        self.assertEqual(
            "STABLE_APPROVED_EXCEPTION",
            self.transition_for("SVC-001", "APPROVED_EXCEPTION"),
        )

    def test_stable_not_applicable_is_delegated_to_decision_engine(self):
        record = {
            "subject": {"account_id": "USR-OUT-OF-SCOPE"},
            "result": {"outcome": "NOT_APPLICABLE"},
        }
        verification = IntegrityVerification(VERIFIED, {}, [])

        decision = build_assurance_decision(
            "ACP-001-03",
            record,
            verification,
            EVALUATION_DATE,
            previous_governance_outcome="NOT_APPLICABLE",
        )

        self.assertEqual("STABLE_NOT_APPLICABLE", decision.transition)

    def test_new_subject_has_no_transition(self):
        result = self.run_with_previous({"USR-002": "FAIL"})
        decision = next(item for item in result.decisions if item.subject_id == "USR-001")

        self.assertIsNone(decision.previous_governance_outcome)
        self.assertIsNone(decision.transition)

    def test_missing_prior_subject_is_reported_without_outcome(self):
        result = self.run_with_previous({"REMOVED-001": "FAIL"})

        self.assertEqual(["REMOVED-001"], result.missing_subject_ids)
        self.assertIn("REMOVED-001", result.summary)
        self.assertNotIn("REMOVED-001 | FAIL", result.summary)

    def test_mismatch_prevents_state_update_and_preserves_previous_state(self):
        self.write_previous({"USR-001": "PASS"})
        previous_bytes = self.previous_state_path.read_bytes()
        prepared = prepare_pipeline(
            EVALUATION_DATE, self.output_directory, GENERATED_AT
        )
        prepared.evidence_paths[0].write_text(
            prepared.evidence_paths[0].read_text(encoding="utf-8") + " ",
            encoding="utf-8",
        )

        result = complete_pipeline(prepared, self.previous_state_path)

        self.assertFalse(result.succeeded)
        self.assertIsNone(result.trusted_state_path)
        self.assertFalse(
            (self.output_directory / "trusted-assurance-state.json").exists()
        )
        self.assertEqual(previous_bytes, self.previous_state_path.read_bytes())

    def test_runtime_trusted_state_is_ignored_by_git(self):
        path = EXAMPLE_ROOT / "generated-assurance" / "trusted-assurance-state.json"
        completed = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={REPOSITORY_ROOT.as_posix()}",
                "-C",
                str(REPOSITORY_ROOT),
                "check-ignore",
                "--quiet",
                str(path),
            ],
            check=False,
        )

        self.assertEqual(0, completed.returncode)


if __name__ == "__main__":
    unittest.main()
