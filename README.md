# lvl3dev-todoist-cli

```bash
  ______          __      _      __ 
 /_  __/___  ____/ /___  (_)____/ /_
  / / / __ \/ __  / __ \/ / ___/ __/
 / / / /_/ / /_/ / /_/ / (__  ) /_  
/_/  \____/\__,_/\____/_/____/\__/  
                                    
```

[![CI](https://github.com/dolphin-electric/todoist-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/dolphin-electric/todoist-cli/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/lvl3dev-todoist-cli?logo=pypi&logoColor=white)](https://pypi.org/project/lvl3dev-todoist-cli/)
[![Python versions](https://img.shields.io/pypi/pyversions/lvl3dev-todoist-cli?logo=python&logoColor=white)](https://pypi.org/project/lvl3dev-todoist-cli/)
[![License](https://img.shields.io/github/license/dolphin-electric/todoist-cli)](LICENSE)

A practical Todoist command-line interface built on the official `todoist-api-python` SDK.
It gives you direct terminal control over tasks, projects, sections, boards, comments, labels,
and calendar-oriented workflows. It is also a great tool for AI agents to manage and control
Todoist reliably through explicit CLI commands and JSON output.

## Install

```bash
pipx install lvl3dev-todoist-cli
```

## Authentication

Set your API token:

```bash
export TODOIST_API_TOKEN="YOUR_API_TOKEN"
```

You can also pass `--token` per command.

## Usage

```bash
todoist --help
```

### Tasks

Create, inspect, update, complete, and delete tasks from the terminal.

```bash
todoist tasks list
todoist tasks add "Pay rent" --due-string "tomorrow 9am" --priority 1
todoist tasks get <task_id>
todoist tasks update <task_id> --content "Pay rent and utilities"
todoist tasks complete <task_id>
todoist tasks delete <task_id>
```

Priority values are user-facing Todoist priorities: `p1` highest, `p4` lowest.

### Projects

Manage project containers and switch between list/board view styles.

```bash
todoist projects list
todoist projects add "Operations"
todoist projects update <project_id> "Ops"
todoist projects view-style <project_id> board
```

### Sections

Organize project work into named columns/lanes by listing and managing sections.

```bash
todoist sections list --project-id <project_id>
todoist sections add --project-id <project_id> "In Progress"
todoist sections update <section_id> "Doing"
todoist sections delete <section_id>
```

### Boards

See a board-style overview of tasks by section and move tasks between sections.

```bash
todoist boards show --project-id <project_id>
todoist boards move <task_id> --section-id <section_id>
```

### Calendar

View due tasks by day/week/range and quickly reschedule deadlines.

```bash
todoist calendar today
todoist calendar week
todoist calendar range --from 2026-02-20 --to 2026-02-27
todoist calendar reschedule <task_id> --due-string "tomorrow 9am"
```

### Comments

List task comments and add progress/context notes directly from CLI.

```bash
todoist comments list --task-id <task_id>
todoist comments add --task-id <task_id> "Started work"
```

### Labels

List available labels so you can filter and tag tasks consistently.

```bash
todoist labels list
```

### JSON Output

Use `--json` to get structured output:

```bash
todoist --json tasks list
```
