import json
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from integrations.github.issues import Issue


API_ROOT = "https://api.github.com"
LABEL_DEFINITIONS = {
    "governance-as-code": (
        "1d76db",
        "Created by the synthetic Governance as Code demonstration",
    ),
    "control-failure": ("b60205", "Governance control failure workflow"),
    "exception-review": ("d4c5f9", "Governance exception review workflow"),
    "integrity-incident": ("b60205", "Governance evidence integrity incident"),
}


class GitHubApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(f"GitHub API returned {status}: {message}")
        self.status = status


@dataclass(frozen=True)
class ApiResponse:
    data: Any
    next_path: str | None = None


class ApiTransport(Protocol):
    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> ApiResponse: ...


class UrllibTransport:
    def __init__(self, token: str):
        self.token = token

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> ApiResponse:
        url = path if path.startswith("https://") else f"{API_ROOT}{path}"
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            url,
            data=data,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request) as response:
                body = response.read()
                parsed = json.loads(body) if body else {}
                return ApiResponse(parsed, _next_link(response.headers.get("Link")))
        except HTTPError as error:
            message = error.read().decode("utf-8", errors="replace")
            raise GitHubApiError(error.code, message) from error


def _next_link(link_header: str | None) -> str | None:
    if not link_header:
        return None
    for part in link_header.split(","):
        url_part, *parameters = part.strip().split(";")
        if any('rel="next"' in parameter for parameter in parameters):
            return url_part.strip()[1:-1]
    return None


class GitHubIssueGateway:
    def __init__(
        self,
        repository: str,
        token: str,
        *,
        transport: ApiTransport | None = None,
    ):
        self.repository = repository
        self.transport = transport or UrllibTransport(token)

    def find_open_issue(self, marker: str) -> Issue | None:
        path = (
            f"/repos/{self.repository}/issues?state=open&"
            "labels=governance-as-code&per_page=100"
        )
        while path:
            response = self.transport.request("GET", path)
            for item in response.data:
                body = item.get("body") or ""
                if marker in body:
                    return Issue(
                        number=item["number"],
                        title=item["title"],
                        body=body,
                    )
            path = response.next_path
        return None

    def ensure_labels(self, labels: tuple[str, ...]) -> None:
        for label in labels:
            if label not in LABEL_DEFINITIONS:
                raise ValueError(f"Unsupported governance issue label: {label}")
            try:
                self.transport.request(
                    "GET", f"/repos/{self.repository}/labels/{quote(label, safe='')}"
                )
            except GitHubApiError as error:
                if error.status != 404:
                    raise
                color, description = LABEL_DEFINITIONS[label]
                self.transport.request(
                    "POST",
                    f"/repos/{self.repository}/labels",
                    {"name": label, "color": color, "description": description},
                )

    def has_event_marker(self, issue: Issue, marker: str) -> bool:
        if marker in issue.body:
            return True
        if issue.number is None:
            return False
        path = (
            f"/repos/{self.repository}/issues/{issue.number}/comments?per_page=100"
        )
        while path:
            response = self.transport.request("GET", path)
            if any(marker in (item.get("body") or "") for item in response.data):
                return True
            path = response.next_path
        return False

    def create_issue(
        self, title: str, body: str, labels: tuple[str, ...]
    ) -> Issue:
        response = self.transport.request(
            "POST",
            f"/repos/{self.repository}/issues",
            {"title": title, "body": body, "labels": list(labels)},
        )
        return Issue(
            number=response.data["number"],
            title=response.data["title"],
            body=response.data.get("body") or "",
        )

    def comment_issue(self, issue_number: int, body: str) -> None:
        self.transport.request(
            "POST",
            f"/repos/{self.repository}/issues/{issue_number}/comments",
            {"body": body},
        )

    def close_issue(self, issue_number: int) -> None:
        self.transport.request(
            "PATCH",
            f"/repos/{self.repository}/issues/{issue_number}",
            {"state": "closed"},
        )
