"""Execute owned split-hop cleanup task conditions against private kernel state."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.native_runtime


def test_inactive_split_hop_retires_only_its_tables_and_route_authority(tmp_path):
    if sys.platform != "linux" or os.geteuid() != 0:
        pytest.skip("requires owned root Linux network namespace")
    if not all(shutil.which(tool) for tool in ("ip", "nft", "ansible-playbook")):
        pytest.skip("requires nftables and pinned Ansible")
    namespace = "p2-retire-" + uuid.uuid4().hex[:7]

    def cmd(*args, data=None):
        result = subprocess.run(
            args, input=data, text=True, capture_output=True, timeout=15
        )
        assert result.returncode == 0, result.stderr
        return result.stdout

    def ns(*args, data=None):
        return cmd("ip", "netns", "exec", namespace, *args, data=data)

    try:
        cmd("ip", "netns", "add", namespace)
        ns("ip", "link", "add", "p2dummy", "type", "dummy")
        ns("ip", "link", "set", "p2dummy", "up")
        for table, mark in ((200, 1), (201, 2)):
            ns("ip", "route", "add", "default", "dev", "p2dummy", "table", str(table))
            ns("ip", "rule", "add", "fwmark", str(mark), "table", str(table))
        ns(
            "nft",
            "-f",
            "-",
            data="table inet split_hop_ingress {}\ntable inet split_hop_egress {}\ntable inet p2_foreign {}\n",
        )
        task_list = []
        for role in ("split-hop-ingress", "split-hop-egress"):
            tasks = yaml.safe_load(
                (ROOT / "ansible/roles" / role / "tasks/disable.yml").read_text()
            )
            start = next(
                index
                for index, task in enumerate(tasks)
                if "ansible.builtin.package_facts" in task
            )
            for original in tasks[start:]:
                task = copy.deepcopy(original)
                if "ansible.builtin.command" in task:
                    task["ansible.builtin.command"]["argv"] = [
                        "ip",
                        "netns",
                        "exec",
                        namespace,
                        *task["ansible.builtin.command"]["argv"],
                    ]
                task_list.append(task)
        play = [
            {
                "hosts": "localhost",
                "connection": "local",
                "gather_facts": False,
                "vars": {
                    "ansible_become": False,
                    "ansible_python_interpreter": sys.executable,
                    "split_hop_ingress": {"fwmark": 1, "routing_table": 200},
                },
                "tasks": task_list,
            }
        ]
        path = tmp_path / "retire.yml"
        path.write_text(yaml.safe_dump(play, sort_keys=False))
        for attempt in range(2):
            result = subprocess.run(
                ["ansible-playbook", "-i", "localhost,", str(path)],
                capture_output=True,
                text=True,
                timeout=40,
                env={**os.environ, "ANSIBLE_CONFIG": str(ROOT / "ansible/ansible.cfg")},
            )
            assert result.returncode == 0, result.stdout + result.stderr
            if attempt:
                assert "changed=0" in result.stdout
        names = {
            row["table"]["name"]
            for row in json.loads(ns("nft", "-j", "list", "tables"))["nftables"]
            if "table" in row
        }
        assert names == {"p2_foreign"}
        rules = json.loads(ns("ip", "-j", "rule", "show"))
        assert not any(str(row.get("table")) == "200" for row in rules)
        assert any(
            str(row.get("table")) == "201" and int(str(row.get("fwmark", 0)), 0) == 2
            for row in rules
        )
        routes = json.loads(ns("ip", "-j", "-4", "route", "show", "table", "all"))
        assert not any(str(row.get("table")) == "200" for row in routes)
        assert any(str(row.get("table")) == "201" for row in routes)
    finally:
        subprocess.run(
            ["ip", "netns", "delete", namespace], capture_output=True, timeout=5
        )
