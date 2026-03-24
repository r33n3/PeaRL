"""Adapter registry — maps adapter_type → lazy-import class path."""

AVAILABLE_ADAPTERS: dict[str, str] = {
    # Sources
    "snyk": "pearl.integrations.adapters.snyk.SnykAdapter",
    "semgrep": "pearl.integrations.adapters.semgrep.SemgrepAdapter",
    "trivy": "pearl.integrations.adapters.trivy.TrivyAdapter",
    "sonarqube": "pearl.integrations.adapters.sonarqube.SonarQubeAdapter",
    # Sinks
    "jira": "pearl.integrations.adapters.jira.JiraAdapter",
    "slack": "pearl.integrations.adapters.slack.SlackAdapter",
    "github_issues": "pearl.integrations.adapters.github_issues.GitHubIssuesAdapter",
    "teams": "pearl.integrations.adapters.teams.TeamsAdapter",
    "telegram": "pearl.integrations.adapters.telegram.TelegramAdapter",
    "webhook": "pearl.integrations.adapters.webhook.WebhookAdapter",
}


def import_adapter(dotted_path: str):
    """Import an adapter class from its dotted module path."""
    import importlib

    module_path, class_name = dotted_path.rsplit(".", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)
