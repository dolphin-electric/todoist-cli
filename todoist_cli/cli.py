import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from typing import Any, Iterable

from requests.exceptions import HTTPError
from todoist_api_python.api import TodoistAPI


def parse_labels(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    labels = [label.strip() for label in raw.split(",")]
    labels = [label for label in labels if label]
    return labels or None


def user_priority_to_api(priority: int | None) -> int | None:
    if priority is None:
        return None
    return 5 - priority


def api_priority_to_user(priority: Any) -> Any:
    if isinstance(priority, int) and 1 <= priority <= 4:
        return 5 - priority
    return priority


def flatten_paged(result: Any) -> list[Any]:
    if result is None:
        return []
    if isinstance(result, list):
        if result and isinstance(result[0], list):
            flat: list[Any] = []
            for page in result:
                flat.extend(page)
            return flat
        return result

    if isinstance(result, Iterable) and not isinstance(result, (str, bytes, dict)):
        flat = []
        for item in result:
            if isinstance(item, list):
                flat.extend(item)
            else:
                flat.append(item)
        return flat

    return [result]


def to_dict(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    for method_name in ("to_dict", "model_dump", "dict"):
        method = getattr(obj, method_name, None)
        if callable(method):
            try:
                value = method()
                if isinstance(value, dict):
                    return value
            except Exception:
                pass
    data = getattr(obj, "__dict__", None)
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if not k.startswith("_")}
    return {"value": str(obj)}


def print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, default=str))


def require_token(args: argparse.Namespace) -> str:
    token = args.token or os.getenv("TODOIST_API_TOKEN")
    if not token:
        raise SystemExit(
            "Missing API token. Pass --token or set TODOIST_API_TOKEN in your environment."
        )
    return token


def task_due_text(task: Any) -> str:
    due = getattr(task, "due", None)
    if due is None:
        return ""
    return (
        getattr(due, "string", None)
        or getattr(due, "date", None)
        or getattr(due, "datetime", None)
        or str(due)
    )


def task_due_date(task: Any) -> date | None:
    due = getattr(task, "due", None)
    if due is None:
        return None

    due_date_raw = getattr(due, "date", None)
    if isinstance(due_date_raw, date):
        return due_date_raw
    if isinstance(due_date_raw, str):
        try:
            return date.fromisoformat(due_date_raw[:10])
        except ValueError:
            pass

    due_datetime_raw = getattr(due, "datetime", None)
    if isinstance(due_datetime_raw, datetime):
        return due_datetime_raw.date()
    if isinstance(due_datetime_raw, str):
        normalized = due_datetime_raw.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).date()
        except ValueError:
            try:
                return date.fromisoformat(due_datetime_raw[:10])
            except ValueError:
                return None

    return None


def render_task_line(task: Any) -> str:
    tid = getattr(task, "id", "")
    content = getattr(task, "content", "")
    priority = api_priority_to_user(getattr(task, "priority", ""))
    due_text = task_due_text(task)
    suffix = f" | p{priority}" if priority else ""
    if due_text:
        suffix += f" | due: {due_text}"
    return f"{tid}\t{content}{suffix}"


def parse_date_arg(raw: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid date '{raw}'. Use YYYY-MM-DD.")


def format_calendar_text(tasks_by_day: list[tuple[date, list[Any]]]) -> str:
    lines: list[str] = []
    for day, day_tasks in tasks_by_day:
        lines.append(f"{day.isoformat()}\t{day.strftime('%A')} ({len(day_tasks)})")
        lines.extend(f"  {render_task_line(task)}" for task in day_tasks)
    return "\n".join(lines)


def calendar_tasks_in_range(api: TodoistAPI, args: argparse.Namespace, start: date, end: date) -> Any:
    kwargs: dict[str, Any] = {}
    if args.project_id:
        kwargs["project_id"] = args.project_id
    if args.label:
        kwargs["label"] = args.label
    if args.limit:
        kwargs["limit"] = args.limit

    tasks = flatten_paged(api.get_tasks(**kwargs))
    buckets: dict[date, list[Any]] = {}
    for task in tasks:
        due_day = task_due_date(task)
        if due_day is None or due_day < start or due_day > end:
            continue
        buckets.setdefault(due_day, []).append(task)

    tasks_by_day = sorted(
        ((day, day_tasks) for day, day_tasks in buckets.items()),
        key=lambda item: item[0],
    )
    for _, day_tasks in tasks_by_day:
        day_tasks.sort(
            key=lambda task: (
                task_due_text(task),
                str(getattr(task, "id", "")),
            )
        )

    if args.json:
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "days": [
                {
                    "date": day.isoformat(),
                    "weekday": day.strftime("%A"),
                    "tasks": [to_dict(task) for task in day_tasks],
                }
                for day, day_tasks in tasks_by_day
            ],
        }

    if not tasks_by_day:
        if start == end:
            return f"No tasks due on {start.isoformat()}."
        return f"No tasks due between {start.isoformat()} and {end.isoformat()}."

    return format_calendar_text(tasks_by_day)


def task_list(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {}
    if args.project_id:
        kwargs["project_id"] = args.project_id
    if args.label:
        kwargs["label"] = args.label
    if args.limit:
        kwargs["limit"] = args.limit

    tasks = flatten_paged(api.get_tasks(**kwargs))
    if args.json:
        return [to_dict(task) for task in tasks]
    if not tasks:
        return "No tasks found."

    return "\n".join(render_task_line(task) for task in tasks)


def task_get(api: TodoistAPI, args: argparse.Namespace) -> Any:
    task = api.get_task(args.task_id)
    if args.json:
        return to_dict(task)
    tid = getattr(task, "id", "")
    content = getattr(task, "content", "")
    description = getattr(task, "description", "")
    return f"{tid}\t{content}\n{description}".strip()


def task_add(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {
        "content": args.content,
    }
    if args.project_id:
        kwargs["project_id"] = args.project_id
    if args.description:
        kwargs["description"] = args.description
    if args.due_string:
        kwargs["due_string"] = args.due_string
    if args.priority is not None:
        kwargs["priority"] = user_priority_to_api(args.priority)
    labels = parse_labels(args.labels)
    if labels:
        kwargs["labels"] = labels
    task = api.add_task(**kwargs)
    return to_dict(task) if args.json else f"Created task {getattr(task, 'id', '')}"


def task_update(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {}
    if args.content is not None:
        kwargs["content"] = args.content
    if args.description is not None:
        kwargs["description"] = args.description
    if args.due_string is not None:
        kwargs["due_string"] = args.due_string
    if args.priority is not None:
        kwargs["priority"] = user_priority_to_api(args.priority)
    if args.labels is not None:
        kwargs["labels"] = parse_labels(args.labels) or []
    if not kwargs:
        raise SystemExit("No fields provided to update.")
    task = api.update_task(args.task_id, **kwargs)
    return to_dict(task) if args.json else f"Updated task {args.task_id}"


def task_complete(api: TodoistAPI, args: argparse.Namespace) -> Any:
    if hasattr(api, "complete_task"):
        api.complete_task(args.task_id)
    else:
        api.close_task(args.task_id)
    return {"status": "ok", "task_id": args.task_id} if args.json else f"Completed task {args.task_id}"


def task_delete(api: TodoistAPI, args: argparse.Namespace) -> Any:
    api.delete_task(args.task_id)
    return {"status": "ok", "task_id": args.task_id} if args.json else f"Deleted task {args.task_id}"


def project_list(api: TodoistAPI, args: argparse.Namespace) -> Any:
    projects = flatten_paged(api.get_projects())
    if args.json:
        return [to_dict(project) for project in projects]
    if not projects:
        return "No projects found."
    return "\n".join(
        f"{getattr(project, 'id', '')}\t{getattr(project, 'name', '')}" for project in projects
    )


def project_add(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {"name": args.name}
    if args.view_style is not None:
        kwargs["view_style"] = args.view_style
    project = api.add_project(**kwargs)
    return to_dict(project) if args.json else f"Created project {getattr(project, 'id', '')}"


def project_update(api: TodoistAPI, args: argparse.Namespace) -> Any:
    project = api.update_project(args.project_id, name=args.name)
    return to_dict(project) if args.json else f"Updated project {args.project_id}"


def project_view_style(api: TodoistAPI, args: argparse.Namespace) -> Any:
    project = api.update_project(args.project_id, view_style=args.style)
    if args.json:
        return to_dict(project)
    return f"Set project {args.project_id} view style to {args.style}"


def comment_list(api: TodoistAPI, args: argparse.Namespace) -> Any:
    comments = flatten_paged(api.get_comments(task_id=args.task_id))
    if args.json:
        return [to_dict(comment) for comment in comments]
    if not comments:
        return "No comments found."
    return "\n".join(
        f"{getattr(comment, 'id', '')}\t{getattr(comment, 'content', '')}" for comment in comments
    )


def comment_add(api: TodoistAPI, args: argparse.Namespace) -> Any:
    comment = api.add_comment(task_id=args.task_id, content=args.content)
    return to_dict(comment) if args.json else f"Created comment {getattr(comment, 'id', '')}"


def label_list(api: TodoistAPI, args: argparse.Namespace) -> Any:
    labels = flatten_paged(api.get_labels())
    if args.json:
        return [to_dict(label) for label in labels]
    if not labels:
        return "No labels found."
    return "\n".join(f"{getattr(label, 'id', '')}\t{getattr(label, 'name', '')}" for label in labels)


def section_list(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {}
    if args.project_id:
        kwargs["project_id"] = args.project_id
    if args.limit:
        kwargs["limit"] = args.limit

    sections = flatten_paged(api.get_sections(**kwargs))
    if args.json:
        return [to_dict(section) for section in sections]
    if not sections:
        return "No sections found."

    ordered_sections = sorted(
        sections,
        key=lambda section: (
            str(getattr(section, "project_id", "")),
            getattr(section, "order", 0),
            str(getattr(section, "name", "")),
        ),
    )

    lines = []
    for section in ordered_sections:
        section_id = getattr(section, "id", "")
        name = getattr(section, "name", "")
        project_id = getattr(section, "project_id", "")
        order = getattr(section, "order", "")
        suffix = []
        if project_id:
            suffix.append(f"project: {project_id}")
        if order != "":
            suffix.append(f"order: {order}")
        details = f" | {' | '.join(suffix)}" if suffix else ""
        lines.append(f"{section_id}\t{name}{details}")
    return "\n".join(lines)


def section_add(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {"name": args.name, "project_id": args.project_id}
    if args.order is not None:
        kwargs["order"] = args.order
    section = api.add_section(**kwargs)
    return to_dict(section) if args.json else f"Created section {getattr(section, 'id', '')}"


def section_update(api: TodoistAPI, args: argparse.Namespace) -> Any:
    section = api.update_section(args.section_id, args.name)
    return to_dict(section) if args.json else f"Updated section {args.section_id}"


def section_delete(api: TodoistAPI, args: argparse.Namespace) -> Any:
    api.delete_section(args.section_id)
    return {"status": "ok", "section_id": args.section_id} if args.json else f"Deleted section {args.section_id}"


def board_show(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {}
    if args.limit:
        kwargs["limit"] = args.limit

    sections = flatten_paged(api.get_sections(project_id=args.project_id, **kwargs))
    tasks = flatten_paged(api.get_tasks(project_id=args.project_id, **kwargs))

    ordered_sections = sorted(
        sections,
        key=lambda section: (
            getattr(section, "order", 0),
            str(getattr(section, "name", "")),
        ),
    )

    columns: list[dict[str, Any]] = []
    columns_by_section_id: dict[Any, dict[str, Any]] = {}

    for section in ordered_sections:
        section_id = getattr(section, "id", None)
        column = {
            "section_id": section_id,
            "name": getattr(section, "name", ""),
            "order": getattr(section, "order", None),
            "tasks": [],
        }
        columns.append(column)
        columns_by_section_id[section_id] = column

    no_section_column: dict[str, Any] = {
        "section_id": None,
        "name": "No section",
        "order": None,
        "tasks": [],
    }

    for task in tasks:
        task_section_id = getattr(task, "section_id", None)
        target_column = columns_by_section_id.get(task_section_id, no_section_column)
        if args.json:
            task_data = to_dict(task)
            if "priority" in task_data:
                task_data["priority"] = api_priority_to_user(task_data["priority"])
            target_column["tasks"].append(task_data)
        else:
            target_column["tasks"].append(task)

    if no_section_column["tasks"]:
        columns.append(no_section_column)

    if args.json:
        return {"project_id": args.project_id, "columns": columns}

    if not columns:
        return "No sections or tasks found."

    lines = []
    for column in columns:
        section_id = column["section_id"]
        section_name = column["name"]
        column_tasks = column["tasks"]
        section_id_text = section_id if section_id is not None else "-"
        lines.append(f"{section_id_text}\t{section_name} ({len(column_tasks)})")
        if column_tasks:
            lines.extend(f"  {render_task_line(task)}" for task in column_tasks)
        else:
            lines.append("  (empty)")
    return "\n".join(lines)


def board_move(api: TodoistAPI, args: argparse.Namespace) -> Any:
    api.move_task(args.task_id, section_id=args.section_id)
    if args.json:
        return {"status": "ok", "task_id": args.task_id, "section_id": args.section_id}
    return f"Moved task {args.task_id} to section {args.section_id}"


def calendar_today(api: TodoistAPI, args: argparse.Namespace) -> Any:
    today = date.today()
    return calendar_tasks_in_range(api, args, today, today)


def calendar_week(api: TodoistAPI, args: argparse.Namespace) -> Any:
    start = date.today()
    end = start + timedelta(days=6)
    return calendar_tasks_in_range(api, args, start, end)


def calendar_range(api: TodoistAPI, args: argparse.Namespace) -> Any:
    if args.date_from > args.date_to:
        raise SystemExit("--from must be less than or equal to --to.")
    return calendar_tasks_in_range(api, args, args.date_from, args.date_to)


def calendar_reschedule(api: TodoistAPI, args: argparse.Namespace) -> Any:
    kwargs: dict[str, Any] = {}
    if args.due_string is not None:
        kwargs["due_string"] = args.due_string
    if args.due_date is not None:
        kwargs["due_date"] = args.due_date
    task = api.update_task(args.task_id, **kwargs)
    if args.json:
        return to_dict(task)
    if args.due_string is not None:
        return f"Rescheduled task {args.task_id} to '{args.due_string}'"
    return f"Rescheduled task {args.task_id} to {args.due_date.isoformat()}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="todoist", description="Todoist CLI powered by todoist-api-python.")
    parser.add_argument("--token", help="Todoist API token. Defaults to TODOIST_API_TOKEN env var.")
    parser.add_argument("--json", action="store_true", help="Print output as JSON.")

    resources = parser.add_subparsers(dest="resource", required=True)

    tasks = resources.add_parser("tasks", help="Manage tasks.")
    task_cmds = tasks.add_subparsers(dest="action", required=True)

    task_list_p = task_cmds.add_parser("list", help="List active tasks.")
    task_list_p.add_argument("--project-id")
    task_list_p.add_argument("--label", help="Filter by label name.")
    task_list_p.add_argument("--limit", type=int, help="Max items per page (1-200).")
    task_list_p.set_defaults(handler=task_list)

    task_get_p = task_cmds.add_parser("get", help="Get a task.")
    task_get_p.add_argument("task_id")
    task_get_p.set_defaults(handler=task_get)

    task_add_p = task_cmds.add_parser("add", help="Create a task.")
    task_add_p.add_argument("content")
    task_add_p.add_argument("--project-id")
    task_add_p.add_argument("--description")
    task_add_p.add_argument("--due-string")
    task_add_p.add_argument(
        "--priority",
        type=int,
        choices=[1, 2, 3, 4],
        help="Priority value where p1 is highest and p4 is lowest.",
    )
    task_add_p.add_argument("--labels", help="Comma-separated labels.")
    task_add_p.set_defaults(handler=task_add)

    task_up_p = task_cmds.add_parser("update", help="Update a task.")
    task_up_p.add_argument("task_id")
    task_up_p.add_argument("--content")
    task_up_p.add_argument("--description")
    task_up_p.add_argument("--due-string")
    task_up_p.add_argument(
        "--priority",
        type=int,
        choices=[1, 2, 3, 4],
        help="Priority value where p1 is highest and p4 is lowest.",
    )
    task_up_p.add_argument("--labels", help="Comma-separated labels. Use empty string to clear.")
    task_up_p.set_defaults(handler=task_update)

    task_complete_p = task_cmds.add_parser("complete", help="Complete a task.")
    task_complete_p.add_argument("task_id")
    task_complete_p.set_defaults(handler=task_complete)

    task_delete_p = task_cmds.add_parser("delete", help="Delete a task.")
    task_delete_p.add_argument("task_id")
    task_delete_p.set_defaults(handler=task_delete)

    projects = resources.add_parser("projects", help="Manage projects.")
    project_cmds = projects.add_subparsers(dest="action", required=True)

    project_list_p = project_cmds.add_parser("list", help="List projects.")
    project_list_p.set_defaults(handler=project_list)

    project_add_p = project_cmds.add_parser("add", help="Create a project.")
    project_add_p.add_argument("name")
    project_add_p.add_argument("--view-style", choices=["list", "board"])
    project_add_p.set_defaults(handler=project_add)

    project_up_p = project_cmds.add_parser("update", help="Update a project name.")
    project_up_p.add_argument("project_id")
    project_up_p.add_argument("name")
    project_up_p.set_defaults(handler=project_update)

    project_view_style_p = project_cmds.add_parser(
        "view-style",
        help="Set a project's view style (list or board).",
    )
    project_view_style_p.add_argument("project_id")
    project_view_style_p.add_argument("style", choices=["list", "board"])
    project_view_style_p.set_defaults(handler=project_view_style)

    sections = resources.add_parser("sections", help="Manage sections.")
    section_cmds = sections.add_subparsers(dest="action", required=True)

    section_list_p = section_cmds.add_parser("list", help="List sections.")
    section_list_p.add_argument("--project-id")
    section_list_p.add_argument("--limit", type=int, help="Max items per page (1-200).")
    section_list_p.set_defaults(handler=section_list)

    section_add_p = section_cmds.add_parser("add", help="Create a section.")
    section_add_p.add_argument("--project-id", required=True)
    section_add_p.add_argument("name")
    section_add_p.add_argument("--order", type=int, help="Sort order within project.")
    section_add_p.set_defaults(handler=section_add)

    section_up_p = section_cmds.add_parser("update", help="Rename a section.")
    section_up_p.add_argument("section_id")
    section_up_p.add_argument("name")
    section_up_p.set_defaults(handler=section_update)

    section_del_p = section_cmds.add_parser("delete", help="Delete a section.")
    section_del_p.add_argument("section_id")
    section_del_p.set_defaults(handler=section_delete)

    comments = resources.add_parser("comments", help="Manage comments.")
    comment_cmds = comments.add_subparsers(dest="action", required=True)

    comment_list_p = comment_cmds.add_parser("list", help="List comments for a task.")
    comment_list_p.add_argument("--task-id", required=True)
    comment_list_p.set_defaults(handler=comment_list)

    comment_add_p = comment_cmds.add_parser("add", help="Add comment to a task.")
    comment_add_p.add_argument("--task-id", required=True)
    comment_add_p.add_argument("content")
    comment_add_p.set_defaults(handler=comment_add)

    labels = resources.add_parser("labels", help="List labels.")
    label_cmds = labels.add_subparsers(dest="action", required=True)
    label_list_p = label_cmds.add_parser("list", help="List labels.")
    label_list_p.set_defaults(handler=label_list)

    boards = resources.add_parser("boards", help="Board view helpers.")
    board_cmds = boards.add_subparsers(dest="action", required=True)

    board_show_p = board_cmds.add_parser("show", help="Show project tasks grouped by section.")
    board_show_p.add_argument("--project-id", required=True)
    board_show_p.add_argument("--limit", type=int, help="Max items per page (1-200).")
    board_show_p.set_defaults(handler=board_show)

    board_move_p = board_cmds.add_parser("move", help="Move a task to a board section.")
    board_move_p.add_argument("task_id")
    board_move_p.add_argument("--section-id", required=True)
    board_move_p.set_defaults(handler=board_move)

    calendar = resources.add_parser("calendar", help="Calendar and scheduling helpers.")
    calendar_cmds = calendar.add_subparsers(dest="action", required=True)

    calendar_today_p = calendar_cmds.add_parser("today", help="Show tasks due today.")
    calendar_today_p.add_argument("--project-id")
    calendar_today_p.add_argument("--label", help="Filter by label name.")
    calendar_today_p.add_argument("--limit", type=int, help="Max items per page (1-200).")
    calendar_today_p.set_defaults(handler=calendar_today)

    calendar_week_p = calendar_cmds.add_parser("week", help="Show tasks due in the next 7 days.")
    calendar_week_p.add_argument("--project-id")
    calendar_week_p.add_argument("--label", help="Filter by label name.")
    calendar_week_p.add_argument("--limit", type=int, help="Max items per page (1-200).")
    calendar_week_p.set_defaults(handler=calendar_week)

    calendar_range_p = calendar_cmds.add_parser("range", help="Show tasks due in a date range.")
    calendar_range_p.add_argument("--from", dest="date_from", required=True, type=parse_date_arg)
    calendar_range_p.add_argument("--to", dest="date_to", required=True, type=parse_date_arg)
    calendar_range_p.add_argument("--project-id")
    calendar_range_p.add_argument("--label", help="Filter by label name.")
    calendar_range_p.add_argument("--limit", type=int, help="Max items per page (1-200).")
    calendar_range_p.set_defaults(handler=calendar_range)

    calendar_reschedule_p = calendar_cmds.add_parser("reschedule", help="Reschedule a task.")
    calendar_reschedule_p.add_argument("task_id")
    reschedule_target = calendar_reschedule_p.add_mutually_exclusive_group(required=True)
    reschedule_target.add_argument("--due-string", help="Natural language due value, e.g. 'tomorrow 9am'.")
    reschedule_target.add_argument("--to", dest="due_date", type=parse_date_arg, help="Due date as YYYY-MM-DD.")
    calendar_reschedule_p.set_defaults(handler=calendar_reschedule)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        token = require_token(args)
        with TodoistAPI(token) as api:
            result = args.handler(api, args)
        if args.json:
            print_json(result)
        elif result is not None:
            print(result)
        return 0
    except HTTPError as err:
        response = getattr(err, "response", None)
        status = getattr(response, "status_code", "unknown")
        text = getattr(response, "text", "") if response is not None else str(err)
        print(f"Todoist API error (status {status}): {text}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130
    except Exception as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
