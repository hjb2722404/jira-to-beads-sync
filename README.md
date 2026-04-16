# JIRA to Beads Sync

A Python script that syncs tasks from JIRA to [Beads](https://github.com/beads/beads) with support for images, attachments, and comments.

## Features

- **Task Sync**: Sync JIRA issues to Beads with priority and type mapping
- **Image Embedding**: JIRA ADF images embedded as Markdown in descriptions
- **Attachment Links**: JIRA attachments displayed as downloadable links
- **Comment Sync**: JIRA comments synced to Beads' native comment system (incremental sync)
- **Auto-Close**: Automatically mark Beads tasks as done when removed from JIRA
- **Multiple Auth**: Supports Basic Auth, API Token, and Bearer Token

## Prerequisites

- Python 3.7+
- [Beads CLI](https://github.com/beads/beads) (`bd`) installed and initialized
- JIRA account with API access

## Installation

```bash
# Clone the repository
git clone https://github.com/hjb2722404/jira-to-beads-sync.git
cd jira-to-beads-sync

# Install Python dependencies (if any)
pip install -r requirements.txt  # Not required for basic usage
```

## Configuration

Create a configuration file at `.claude/jira-config.json` in your project directory:

```json
{
  "jira_url": "https://your-jira-server.com",
  "auth_type": "basic",
  "auth": {
    "username": "your-username",
    "password": "your-password"
  },
  "jql": "statusCategory != Done AND assignee = currentUser() ORDER BY priority DESC, created ASC",
  "validate_ssl": false,
  "project_dir": "/path/to/beads/project"
}
```

### Configuration Fields

| Field | Required | Description |
|-------|----------|-------------|
| `jira_url` | Yes | JIRA server URL |
| `auth_type` | Yes | Auth method: `basic`, `api_token`, or `bearer` |
| `auth` | Yes | Auth credentials (format depends on auth_type) |
| `jql` | No | JQL query (defaults to active tasks assigned to current user) |
| `validate_ssl` | No | Enable SSL verification (default: true) |
| `project_dir` | No | Beads project directory (default: current directory) |

### Auth Types

```json
// Basic Auth
{"username": "...", "password": "..."}

// API Token (for JIRA Cloud)
{"email": "...", "token": "..."}

// Bearer Token
{"token": "..."}
```

## Usage

```bash
# Default usage (reads from .claude/jira-config.json)
python scripts/jira_to_beads.py

# Specify config file
python scripts/jira_to_beads.py --config /path/to/config.json

# Override JQL
python scripts/jira_to_beads.py --jql "project = PROJ AND statusCategory != Done"

# Sync all tasks without selection
python scripts/jira_to_beads.py --all

# Dry run (preview only)
python scripts/jira_to_beads.py --dry-run
```

### Interactive Selection

```
# Select individual tasks
1 3 5

# Select range
1-3

# Select all
all

# Cancel
q
```

## Priority Mapping

| JIRA Priority | Beads Priority |
|---------------|----------------|
| Highest | 0 (Critical) |
| High | 1 (High) |
| Medium | 2 (Normal) |
| Low | 3 (Low) |
| Lowest | 4 (Trivial) |

## Issue Type Mapping

| JIRA Type | Beads Type |
|-----------|------------|
| Bug | bug |
| Story | feature |
| Task | task |
| Sub-task | task |
| Epic | epic |

## Sync Behavior

### New Tasks
- Created in Beads with full description, attachments, and comments

### Existing Tasks (matched by `external_ref`)
- Updated: priority, description
- Incremental comment sync: only new JIRA comments are added to Beads

### Removed Tasks
- Tasks that exist in Beads but not in JIRA are marked as done

## License

MIT
