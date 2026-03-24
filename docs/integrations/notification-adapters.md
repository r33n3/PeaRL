# Notification Adapters

PeaRL supports three notification sink adapters for pushing promotion-gate alerts and security events to external messaging platforms.

## Adapter Types

| `adapter_type` | Platform | Auth Method |
|---|---|---|
| `teams` | Microsoft Teams | Incoming webhook URL (pre-authenticated) |
| `telegram` | Telegram | Bot token via env var |
| `webhook` | Generic / Discord | Optional Bearer or API key via env var |

---

## Microsoft Teams (`teams`)

Uses the [Incoming Webhook](https://learn.microsoft.com/en-us/microsoftteams/platform/webhooks-and-connectors/how-to/add-incoming-webhook) connector. Sends an Office 365 Connector MessageCard.

### Registration

```json
{
  "name": "My Teams Channel",
  "adapter_type": "teams",
  "integration_type": "sink",
  "category": "notification_channels",
  "base_url": "https://your-org.webhook.office.com/webhookb2/...",
  "enabled": true
}
```

No auth configuration is needed — the webhook URL is self-authenticating.

### Severity colours

| Severity | Colour |
|---|---|
| `critical`, `high` | Red (`FF0000`) |
| `moderate`, `medium` | Orange (`FFA500`) |
| `low`, `info` | Teams blue (`0078D4`) |
| `pass`, `success` | Green (`28A745`) |

---

## Telegram (`telegram`)

Uses the [Telegram Bot API](https://core.telegram.org/bots/api) `sendMessage` method. Formats messages with Markdown.

### Registration

```json
{
  "name": "My Telegram Channel",
  "adapter_type": "telegram",
  "integration_type": "sink",
  "category": "notification_channels",
  "base_url": "https://api.telegram.org",
  "auth": {
    "auth_type": "bearer",
    "bearer_token_env": "TG_BOT_TOKEN"
  },
  "labels": {
    "chat_id": "-1001234567890"
  },
  "enabled": true
}
```

Set the environment variable referenced by `bearer_token_env`:

```
TG_BOT_TOKEN=123456789:AAFabcdefghijklmnop
```

The `chat_id` label is mandatory. It can be a user ID, group ID (negative number), or public channel username (`@mychannel`).

---

## Generic Webhook (`webhook`)

HTTP POST to any URL. The payload includes a `content` field for Discord compatibility.

### Registration

```json
{
  "name": "Discord Alerts",
  "adapter_type": "webhook",
  "integration_type": "sink",
  "category": "notification_channels",
  "base_url": "https://discord.com/api/webhooks/123/abc",
  "enabled": true
}
```

For endpoints requiring authentication, use `auth_config`:

```json
{
  "auth": {
    "auth_type": "bearer",
    "bearer_token_env": "MY_WEBHOOK_TOKEN"
  }
}
```

### Payload shape

```json
{
  "title": "Promotion Gate: proj_myapp001 → preprod",
  "body": "2/3 gates passing (66%).\n1 blocker(s) require human review...",
  "severity": "high",
  "project_id": "proj_myapp001",
  "finding_ids": null,
  "content": "**Promotion Gate: proj_myapp001 → preprod**\n2/3 gates passing..."
}
```

The `content` field mirrors `title + body` so Discord renders it visibly in the channel without additional embed configuration.

---

## Promotion Gate Notifications

When `POST /api/v1/approvals/requests` is called with `request_type: "promotion_gate"`, PeaRL automatically dispatches a `NormalizedNotification` to all **enabled org-level sink adapters** after the record is committed.

The notification includes:

- **subject**: `Promotion Gate: {project_id} → {target_environment}`
- **body**: gate pass/fail counts and blocker summary
- **severity**: `high` if there are blockers, `low` if all gates pass

Only org-level sink integrations (those registered without a `project_id`) receive these notifications.

All notification failures are caught and logged — they never interrupt the approval request flow.
