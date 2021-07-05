from enum import Enum
from typing import Dict, Generator, List, Optional


class ActionKind(Enum):
    PATCH = 1
    PUT = 2
    DELETE = 3
    POST = 4


# This could have probably been a dataclass but shh
class Action:
    def __init__(
        self,
        kind: ActionKind,
        path: str,
        set_dict: Optional[Dict[str, str]] = None,
        current_dict: Optional[Dict[str, str]] = None,
    ) -> None:
        self.kind = kind
        self.path = path

        self.set_dict: Dict[str, str] = set_dict or {}
        self.current_dict: Dict[str, str] = current_dict or {}

    def diff(self) -> List[str]:
        differences = []

        keys = set(self.set_dict.keys()) | set(self.current_dict.keys()) - {".id"}

        for key in keys:
            left = self.current_dict[key] if key in self.current_dict else "[empty]"
            right = self.set_dict[key] if key in self.set_dict else "[empty]"

            if left != right:
                differences.append(
                    f" [bold blue]{key}[/bold blue]: {left} [bold]->[/bold] {right}"
                )

        return differences

    def __rich_repr__(self) -> Generator:
        yield "kind", self.kind
        yield "path", self.path
        yield "set_dict", self.set_dict

    def __repr__(self) -> str:
        return f"<Action kind={self.kind}, path={self.path}, set_dict={self.set_dict}"
