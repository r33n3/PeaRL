"""Adapter registry — maps adapter_type → lazy-import class path."""

AVAILABLE_ADAPTERS: dict[str, str] = {
    # Sources
    "snyk": "pearl.integrations.adapters.snyk.SnykAdapter",
    "semgrep": "pearl.integrations.adapters.semgrep.SemgrepAdapter",
    "trivy": "pearl.integrations.adapters.trivy.TrivyAdapter",
    "sonarqube": "pearl.integrations.adapters.sonarqube.SonarQubeAdapter",
    "mass": "pearl.integrations.adapters.mass.MassAdapter",
    # CI/CD
    "azure_devops": None,  # CI/CD integration — no pull/push adapter; used for snippet generation
    # Sinks
    "jira": "pearl.integrations.adapters.jira.JiraAdapter",
    "slack": "pearl.integrations.adapters.slack.SlackAdapter",
    "github": "pearl.integrations.adapters.github_issues.GitHubIssuesAdapter",
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


from pearl.integrations.adapters.base_agent import BaseAgentPlatformAdapter


def get_agent_platform_adapter(platform: str, api_key: str) -> BaseAgentPlatformAdapter:
    """Factory: returns the adapter for the given platform string."""
    if platform == "claude":
        from pearl.integrations.adapters.claude_managed_agents import ClaudeManagedAgentsAdapter
        return ClaudeManagedAgentsAdapter(api_key=api_key)
    if platform == "openai":
        from pearl.integrations.adapters.openai_agents import OpenAIAgentsAdapter
        return OpenAIAgentsAdapter(api_key=api_key)
    raise ValueError(f"Unknown platform: {platform!r}")
