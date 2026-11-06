"""Small JSONC editor: preserve unrelated text, comments and trailing commas."""
import json
import math
import re
from dataclasses import dataclass, field

TOKEN = re.compile(r'"(?:[^"\\]|\\.)*"|-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null|[{}\[\]:,]')


@dataclass
class Node:
    value: object
    start: int
    end: int
    children: dict = field(default_factory=dict)
    trailing: bool = False


class Document:
    def __init__(self, text):
        self.text = text
        self.tokens = []
        at = 0
        while at < len(text):
            if text[at].isspace() or (at == 0 and text[at] == '\ufeff'):
                at += 1
                continue
            if text.startswith('//', at):
                end = text.find('\n', at)
                at = len(text) if end < 0 else end
                continue
            if text.startswith('/*', at):
                end = text.find('*/', at + 2)
                if end < 0:
                    raise ValueError('unterminated JSONC comment')
                at = end + 2
                continue
            match = TOKEN.match(text, at)
            if not match:
                raise ValueError('invalid JSONC token')
            self.tokens.append((match.group(), at, match.end()))
            at = match.end()
        self.index = 0
        try:
            self.root = self._value()
        except (IndexError, RecursionError) as exc:
            raise ValueError('incomplete or deeply nested JSONC') from exc
        if self.index != len(self.tokens) or not isinstance(self.root.value, dict):
            raise ValueError('configuration must be a single JSONC object')

    def _take(self, expected=None):
        token = self.tokens[self.index]
        self.index += 1
        if expected is not None and token[0] != expected:
            raise ValueError('invalid JSONC structure')
        return token

    def _value(self):
        token, start, end = self._take()
        if token not in ('{', '['):
            if token in ('}', ']', ':', ','):
                raise ValueError('invalid JSONC value')
            value = json.loads(token)
            if isinstance(value, float) and not math.isfinite(value):
                raise ValueError('nonfinite JSONC number')
            return Node(value, start, end)
        is_object = token == '{'
        close = '}' if is_object else ']'
        value = {} if is_object else []
        children, trailing = {}, False
        if self.tokens[self.index][0] != close:
            while True:
                if is_object:
                    key = json.loads(self._take()[0])
                    if not isinstance(key, str) or key in children:
                        raise ValueError('duplicate or invalid JSONC key')
                    self._take(':')
                else:
                    key = len(value)
                child = self._value()
                children[key] = child
                if is_object:
                    value[key] = child.value
                else:
                    value.append(child.value)
                if self.tokens[self.index][0] == close:
                    break
                self._take(',')
                if self.tokens[self.index][0] == close:
                    trailing = True
                    break
        _, _, end = self._take(close)
        return Node(value, start, end, children, trailing)

    def _insert(self, node, entry, depth):
        comma = ',' if node.children and not node.trailing else ''
        indentation = '  ' * depth
        addition = comma + '\n' + indentation + entry + '\n' + '  ' * (depth - 1)
        return self.text[:node.end - 1] + addition + self.text[node.end - 1:]

    def set(self, path, value):
        node = self.root
        for depth, key in enumerate(path, 1):
            if not isinstance(node.value, dict):
                raise ValueError('configuration parent must be an object')
            if key not in node.children:
                for name in reversed(path[depth:]):
                    value = {name: value}
                entry = json.dumps(key) + ': ' + json.dumps(value, ensure_ascii=False, indent=2)
                return self._insert(node, entry.replace('\n', '\n' + '  ' * depth), depth)
            node = node.children[key]
        encoded = json.dumps(value, ensure_ascii=False, indent=2).replace('\n', '\n' + '  ' * len(path))
        return self.text[:node.start] + encoded + self.text[node.end:]

    def append(self, key, value):
        node = self.root.children.get(key)
        if node is None:
            return self.set([key], [value])
        if not isinstance(node.value, list):
            raise ValueError(key + ' must be an array')
        if value in node.value:
            return self.text
        return self._insert(node, json.dumps(value, ensure_ascii=False), 2)
