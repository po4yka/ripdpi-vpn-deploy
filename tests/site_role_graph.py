"""Ordered static role declarations in site roles and normal task blocks."""
from copy import deepcopy


def site_roles(play):
    result = deepcopy(play.get("roles", []))
    def visit(tasks, inherited_tags=()):
        for task in tasks:
            tags = list(dict.fromkeys([*inherited_tags, *task.get("tags", [])]))
            imported = task.get("ansible.builtin.import_role")
            if imported:
                role = {"role": imported["name"], "tags": tags}
                role.update({key: deepcopy(value) for key, value in imported.items()
                             if key not in {"name", "public"}})
                role.update({key: deepcopy(task[key]) for key in ("when", "vars") if key in task})
                result.append(role)
            visit(task.get("block", []), tags)
    visit(play.get("tasks", []))
    return result
