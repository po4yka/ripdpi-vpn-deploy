"""Safe YAML scalar and duplicate-key semantics shared by CLI inputs."""

import re

import yaml


class StrictLoader(yaml.SafeLoader):
    """Match serde YAML scalar rules; refuse ambiguous duplicate mappings."""

    def construct_mapping(self, node, deep=False):
        if not isinstance(node, yaml.MappingNode):
            raise ValueError("invalid YAML mapping")
        mapping = {}
        identities = set()
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                identity = (key_node.tag, key)
                if identity in identities:
                    raise ValueError("duplicate YAML mapping key")
                identities.add(identity)
                mapping[key] = self.construct_object(value_node, deep=deep)
            except TypeError:
                raise ValueError("invalid YAML mapping key") from None
        return mapping


def construct_integer(loader, node):
    value = loader.construct_scalar(node)
    sign = -1 if value.startswith("-") else 1
    unsigned = value.lstrip("+-")
    if unsigned.startswith("0o"):
        return sign * int(unsigned[2:], 8)
    if unsigned.startswith("0x"):
        return sign * int(unsigned[2:], 16)
    if unsigned.startswith("0b"):
        return sign * int(unsigned[2:], 2)
    return int(value, 10)


StrictLoader.yaml_implicit_resolvers = {
    first: [
        (tag, pattern)
        for tag, pattern in resolvers
        if tag
        not in {
            "tag:yaml.org,2002:bool",
            "tag:yaml.org,2002:timestamp",
            "tag:yaml.org,2002:int",
            "tag:yaml.org,2002:float",
            "tag:yaml.org,2002:merge",
        }
    ]
    for first, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:bool", re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"), list("tTfF")
)
StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:int",
    re.compile(r"^[+-]?(?:0|[1-9][0-9]*|0o[0-7]+|0x[0-9a-fA-F]+|0b[01]+)$"),
    list("-+0123456789"),
)
StrictLoader.add_constructor("tag:yaml.org,2002:int", construct_integer)
StrictLoader.add_implicit_resolver(
    "tag:yaml.org,2002:float",
    re.compile(
        r"^(?:[+-]?(?:[0-9]+\.[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?|[+-]?[0-9]+[eE][+-]?[0-9]+|[+-]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
    ),
    list("-+0123456789."),
)


def load_yaml(source):
    """Fail categorically without values, source names or YAML parser excerpts."""
    try:
        return yaml.load(source, Loader=StrictLoader)
    except (yaml.YAMLError, UnicodeError, ValueError, TypeError):
        raise ValueError("invalid YAML document") from None
