"""Shell completions and roff pages derived from the live argparse tree."""

import argparse
from pathlib import Path
import shlex
from vpnd.cli import build_parser


def command_tree():
    def visit(parser, path):
        yield path, parser
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    yield from visit(child, path + (name,))

    return list(visit(build_parser(), ()))


def candidates(parser):
    values = []
    for action in parser._actions:
        values.extend(action.option_strings)
        if isinstance(action, argparse._SubParsersAction):
            values.extend(action.choices)
        if action.choices and not isinstance(action, argparse._SubParsersAction):
            values.extend(str(value) for value in action.choices)
    return list(dict.fromkeys(values))


def described_candidates(parser):
    descriptions = {}
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, child in action.choices.items():
                descriptions[name] = child.description or name
        else:
            for option in action.option_strings:
                descriptions[option] = (
                    action.help if action.help not in {None, argparse.SUPPRESS} else option
                )
            for value in action.choices or []:
                descriptions[str(value)] = str(value)
    return descriptions


def generate_completion(shell):
    shell = shell.lower()
    if shell == "pwsh":
        shell = "powershell"
    tree = command_tree()
    if shell == "bash":
        lines = [
            "_vpnd() {",
            '    local cur="${COMP_WORDS[COMP_CWORD]}" path="" word',
            "    local i",
            "    for ((i=1; i<COMP_CWORD; i++)); do",
            '        word="${COMP_WORDS[i]}"',
            '        case "$path:$word" in',
        ]
        for path, _ in tree:
            if path:
                lines.append(
                    f"            {shlex.quote(' '.join(path[:-1]) + ':' + path[-1])}) path={shlex.quote(' '.join(path))} ;;"
                )
        lines += ["        esac", "    done", '    case "$path" in']
        for path, parser in tree:
            lines.append(
                f'        {shlex.quote(" ".join(path))}) COMPREPLY=( $(compgen -W {shlex.quote(" ".join(candidates(parser)))} -- "$cur") ) ;;'
            )
        lines += ["    esac", "}", "complete -F _vpnd vpnd", ""]
        return "\n".join(lines)
    if shell == "zsh":
        lines = [
            "#compdef vpnd",
            "_vpnd() {",
            '    local context="" word',
            "    for word in ${words[2,-2]}; do",
            '        case "$context:$word" in',
        ]
        for path, _ in tree:
            if path:
                lines.append(
                    f"            {shlex.quote(' '.join(path[:-1]) + ':' + path[-1])}) context={shlex.quote(' '.join(path))} ;;"
                )
        lines += ["        esac", "    done", '    case "$context" in']
        for path, parser in tree:
            entries = []
            for value, description in described_candidates(parser).items():
                description = description.replace("\\", "\\\\").replace(":", "\\:")
                entries.append(shlex.quote(value + ":" + description))
            lines.append(
                f"        {shlex.quote(' '.join(path))}) local -a suggestions; suggestions=({' '.join(entries)}); _describe 'vpnd' suggestions ;;"
            )
        lines += ["    esac", "}", '_vpnd "$@"', ""]
        return "\n".join(lines)
    if shell == "fish":
        lines = []
        for path, parser in tree:
            condition = (
                "__fish_use_subcommand"
                if not path
                else "__fish_seen_subcommand_from " + " ".join(path)
            )
            for action in parser._actions:
                if isinstance(action, argparse._SubParsersAction):
                    for name in action.choices:
                        lines.append(
                            f"complete -c vpnd -n {shlex.quote(condition)} -a {shlex.quote(name)} -d {shlex.quote(action.choices[name].description or name)}"
                        )
                elif action.option_strings:
                    opts = " ".join(
                        ("-l " + opt[2:] if opt.startswith("--") else "-s " + opt[1:])
                        for opt in action.option_strings
                    )
                    values = (
                        " -a " + shlex.quote(" ".join(map(str, action.choices)))
                        if action.choices
                        else ""
                    )
                    required = " -r" if action.nargs != 0 else ""
                    description = " -d " + shlex.quote(action.help or action.dest)
                    lines.append(
                        f"complete -c vpnd -n {shlex.quote(condition)} {opts}{required}{values}{description}"
                    )
        return "\n".join(lines) + "\n"
    if shell == "powershell":
        lines = [
            "Register-ArgumentCompleter -Native -CommandName vpnd -ScriptBlock {",
            "    param($wordToComplete, $commandAst, $cursorPosition)",
            "    $context = ''",
            "    foreach ($element in $commandAst.CommandElements | Select-Object -Skip 1) {",
            "        switch ($context + ':' + $element.Extent.Text) {",
        ]
        for path, _ in tree:
            if path:
                lines.append(
                    f"            '{' '.join(path[:-1])}:{path[-1]}' {{ $context = '{' '.join(path)}' }}"
                )
        lines += ["        }", "    }", "    $words = switch ($context) {"]
        for path, parser in tree:
            values = ", ".join("'" + word.replace("'", "''") + "'" for word in candidates(parser))
            lines.append(f"        '{' '.join(path)}' {{ @({values}) }}")
        lines += [
            "    }",
            '    $words | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {',
            '        [System.Management.Automation.CompletionResult]::new($_, $_, "ParameterValue", $_)',
            "    }",
            "}",
            "",
        ]
        return "\n".join(lines)
    raise ValueError(f"unknown shell '{shell}'; supported: bash, zsh, fish, powershell")


def roff_escape(value):
    return str(value).replace("\\", r"\e").replace("-", r"\-").replace("\n.", "\n\\&.")


def render_page_set():
    pages = []
    for path, parser in command_tree():
        name = "-".join(("vpnd",) + path)
        page = f'.TH "{name.upper()}" "1"\n.SH NAME\n{name} \\- {roff_escape(parser.description or "VPN operator command")}\n.SH SYNOPSIS\n{roff_escape(parser.format_usage().strip())}\n.SH OPTIONS\n'
        for action in parser._actions:
            if action.help == argparse.SUPPRESS or isinstance(action, argparse._SubParsersAction):
                continue
            page += (
                ".TP\n"
                + roff_escape(", ".join(action.option_strings) or action.dest)
                + "\n"
                + roff_escape(action.help or action.dest)
                + "\n"
            )
            if (
                action.default is not None
                and action.default != argparse.SUPPRESS
                and action.default is not False
            ):
                page += "Default: " + roff_escape(action.default) + "\n"
            if action.choices:
                page += "Values: " + roff_escape(", ".join(map(str, action.choices))) + "\n"
        subcommands = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        if subcommands:
            page += (
                ".SH COMMANDS\n"
                + "\n".join(roff_escape(name) for a in subcommands for name in a.choices)
                + "\n"
            )
        pages.append((name, page))
    return pages


def write_man_pages(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for name, page in render_page_set():
        (directory / (name + ".1")).write_text(page)


def run(args):
    print(generate_completion(args.shell), end="")
    return 0
