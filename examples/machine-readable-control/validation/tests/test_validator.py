import unittest
from datetime import date
from pathlib import Path

from validation.validator import (
    APPROVED_EXCEPTION,
    FAIL,
    NOT_APPLICABLE,
    PASS,
    evaluate_account,
    evaluate_environment,
    load_control,
    load_environment,
)


EXAMPLE_ROOT = Path(__file__).resolve().parents[2]
CONTROL_PATH = EXAMPLE_ROOT / "controls" / "ACP-001-03.yaml"
ENVIRONMENT_PATH = EXAMPLE_ROOT / "sample-data" / "identity-environment.json"
EVALUATION_DATE = date(2026, 8, 22)

CONTROL = {
    "control": {
        "requirement": {
            "scope": [
                "privileged_accounts",
                "remote_access",
                "sensitive_or_regulated_systems",
            ]
        }
    }
}


def account(**overrides):
    values = {
        "account_id": "TEST-001",
        "username": "test.user@example.test",
        "privileged": False,
        "remote_access": False,
        "sensitive_or_regulated_system_access": False,
        "mfa_enabled": False,
        "exception": None,
    }
    values.update(overrides)
    return values


def valid_exception(**overrides):
    values = {
        "exception_id": "EXC-TEST",
        "status": "approved",
        "risk_review_completed": True,
        "security_approval": True,
        "governance_approval": True,
        "expiration_date": "2026-12-31",
    }
    values.update(overrides)
    return values


class AccountEvaluationTests(unittest.TestCase):
    def test_privileged_account_with_mfa_passes(self):
        result = evaluate_account(
            account(privileged=True, mfa_enabled=True), CONTROL, EVALUATION_DATE
        )

        self.assertEqual(PASS, result.outcome)
        self.assertTrue(result.reason)

    def test_remote_access_account_without_mfa_fails(self):
        result = evaluate_account(
            account(remote_access=True), CONTROL, EVALUATION_DATE
        )

        self.assertEqual(FAIL, result.outcome)

    def test_sensitive_system_account_with_mfa_passes(self):
        result = evaluate_account(
            account(
                sensitive_or_regulated_system_access=True,
                mfa_enabled=True,
            ),
            CONTROL,
            EVALUATION_DATE,
        )

        self.assertEqual(PASS, result.outcome)

    def test_disabled_mfa_with_valid_exception_is_approved_exception(self):
        result = evaluate_account(
            account(privileged=True, exception=valid_exception()),
            CONTROL,
            EVALUATION_DATE,
        )

        self.assertEqual(APPROVED_EXCEPTION, result.outcome)

    def test_disabled_mfa_with_expired_exception_fails(self):
        result = evaluate_account(
            account(
                privileged=True,
                exception=valid_exception(expiration_date="2026-06-30"),
            ),
            CONTROL,
            EVALUATION_DATE,
        )

        self.assertEqual(FAIL, result.outcome)

    def test_exception_expiring_on_evaluation_date_is_approved_exception(self):
        result = evaluate_account(
            account(
                privileged=True,
                exception=valid_exception(expiration_date="2026-08-22"),
            ),
            CONTROL,
            EVALUATION_DATE,
        )

        self.assertEqual(APPROVED_EXCEPTION, result.outcome)

    def test_out_of_scope_account_is_not_applicable(self):
        result = evaluate_account(account(), CONTROL, EVALUATION_DATE)

        self.assertEqual(NOT_APPLICABLE, result.outcome)

    def test_exception_missing_risk_review_fails(self):
        result = evaluate_account(
            account(
                privileged=True,
                exception=valid_exception(risk_review_completed=False),
            ),
            CONTROL,
            EVALUATION_DATE,
        )

        self.assertEqual(FAIL, result.outcome)

    def test_exception_missing_security_approval_fails(self):
        result = evaluate_account(
            account(
                privileged=True,
                exception=valid_exception(security_approval=False),
            ),
            CONTROL,
            EVALUATION_DATE,
        )

        self.assertEqual(FAIL, result.outcome)

    def test_exception_missing_governance_approval_fails(self):
        result = evaluate_account(
            account(
                privileged=True,
                exception=valid_exception(governance_approval=False),
            ),
            CONTROL,
            EVALUATION_DATE,
        )

        self.assertEqual(FAIL, result.outcome)

    def test_exception_without_approved_status_fails(self):
        result = evaluate_account(
            account(
                privileged=True,
                exception=valid_exception(status="pending"),
            ),
            CONTROL,
            EVALUATION_DATE,
        )

        self.assertEqual(FAIL, result.outcome)


class SyntheticEnvironmentIntegrationTests(unittest.TestCase):
    def test_existing_dataset_produces_expected_outcomes(self):
        control = load_control(CONTROL_PATH)
        environment = load_environment(ENVIRONMENT_PATH)

        results = evaluate_environment(control, environment, EVALUATION_DATE)

        self.assertEqual(
            [
                ("admin@example.test", PASS),
                ("remote.user@example.test", PASS),
                ("finance.user@example.test", PASS),
                ("service.account@example.test", APPROVED_EXCEPTION),
                ("legacy.admin@example.test", FAIL),
            ],
            [(result.username, result.outcome) for result in results],
        )
        self.assertTrue(all(result.reason for result in results))


if __name__ == "__main__":
    unittest.main()
