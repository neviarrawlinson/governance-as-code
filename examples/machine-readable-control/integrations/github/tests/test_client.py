import unittest

from integrations.github.client import ApiResponse, GitHubApiError, GitHubIssueGateway
from integrations.github.issues import Issue


class RecordingTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class GitHubIssueGatewayTests(unittest.TestCase):
    def test_finds_exact_marker_across_paginated_open_issues(self):
        marker = "<!-- governance-correlation-id: gac-v1:control-failure:C:S -->"
        transport = RecordingTransport(
            [
                ApiResponse(
                    [{"number": 1, "title": "Other", "body": "other"}],
                    "/repos/owner/repo/issues?state=open&page=2",
                ),
                ApiResponse(
                    [{"number": 2, "title": "Match", "body": marker}], None
                ),
            ]
        )
        gateway = GitHubIssueGateway("owner/repo", "token", transport=transport)

        issue = gateway.find_open_issue(marker)

        self.assertEqual(2, issue.number)
        self.assertEqual(2, len(transport.calls))
        self.assertIn("labels=governance-as-code", transport.calls[0][1])

    def test_create_comment_and_close_use_bounded_issue_endpoints(self):
        transport = RecordingTransport(
            [
                ApiResponse({"number": 5, "title": "Created", "body": "Body"}),
                ApiResponse({}),
                ApiResponse({}),
            ]
        )
        gateway = GitHubIssueGateway("owner/repo", "token", transport=transport)

        created = gateway.create_issue("Created", "Body", ("governance-as-code",))
        gateway.comment_issue(5, "Update")
        gateway.close_issue(5)

        self.assertEqual(5, created.number)
        self.assertEqual(
            [
                ("POST", "/repos/owner/repo/issues"),
                ("POST", "/repos/owner/repo/issues/5/comments"),
                ("PATCH", "/repos/owner/repo/issues/5"),
            ],
            [(method, path) for method, path, _ in transport.calls],
        )
        self.assertEqual({"state": "closed"}, transport.calls[2][2])

    def test_missing_labels_are_created_with_bounded_taxonomy(self):
        transport = RecordingTransport(
            [
                GitHubApiError(404, "missing"),
                ApiResponse({}),
                ApiResponse({"name": "control-failure"}),
            ]
        )
        gateway = GitHubIssueGateway("owner/repo", "token", transport=transport)

        gateway.ensure_labels(("governance-as-code", "control-failure"))

        self.assertEqual(
            ("POST", "/repos/owner/repo/labels"),
            transport.calls[1][:2],
        )
        self.assertEqual("governance-as-code", transport.calls[1][2]["name"])

    def test_event_marker_lookup_checks_issue_body_then_paginated_comments(self):
        marker = "<!-- governance-event-id: event-123 -->"
        transport = RecordingTransport(
            [
                ApiResponse([{"body": "other"}], "/next-comments"),
                ApiResponse([{"body": marker}], None),
            ]
        )
        gateway = GitHubIssueGateway("owner/repo", "token", transport=transport)

        found = gateway.has_event_marker(
            issue=Issue(number=7, title="Existing", body="issue body"),
            marker=marker,
        )

        self.assertTrue(found)
        self.assertEqual(2, len(transport.calls))
        self.assertIn("/issues/7/comments", transport.calls[0][1])


if __name__ == "__main__":
    unittest.main()
