import asyncio
import itertools
import json
from enum import Enum
from typing import Any, Callable, DefaultDict, Dict, Generator, List, Optional

import aiohttp
from frozendict import frozendict
from rich.console import Console
from rich.progress import Progress

from mtsync.settings import Settings


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


class Synchronizer:
    def __init__(
        self,
        console: Console,
        settings: Settings,
        desired_tree: Dict,
    ) -> None:
        self.console = console
        self.settings = settings
        self.desired_tree = desired_tree

        self.session: aiohttp.ClientSession

    def _construct_url(
        self,
        endpoint: str,
    ) -> str:
        return f"https://{self.settings.hostname}/rest{endpoint}"

    async def _call(
        self,
        method: Callable,
        endpoint: str,
        **kwargs: Dict[str, Any],
    ) -> None:
        async with method(
            self._construct_url(endpoint=endpoint),
            verify_ssl=not self.settings.ignore_certificate_errors,
            auth=aiohttp.BasicAuth(
                login=self.settings.username, password=self.settings.password
            ),
            headers={"content-type": "application/json"},
            **kwargs,
        ) as response:
            try:
                return await response.json()
            except aiohttp.client_exceptions.ContentTypeError:
                text = await response.text()

                if text == "":
                    return None

                return json.loads(text)

    def _score_items(
        self,
        a: Dict[str, str],
        b: Dict[str, str],
    ) -> int:
        # `a` is meant to have less (or equal) key count
        if len(a.keys()) > len(b.keys()):
            a, b = b, a

        score = 0

        for k, v in a.items():
            if k in b and b[k] == v:
                score += 1

        return score

    async def _analyze_list(
        self,
        current_path: str,
        analyzed_list: List[Dict[str, str]],
    ) -> List[Action]:
        desired_items = [frozendict(it) for it in analyzed_list]
        proplist = set(itertools.chain(*[item.keys() for item in desired_items])) | {
            ".id"
        }

        current_items = [
            frozendict(it)
            for it in await self._call(
                method=self.session.get,
                endpoint=current_path,
                params={
                    "dynamic": "false",
                    ".proplist": ",".join(proplist),
                },
            )
        ]

        scores: Dict[Any, Dict[Any, Any]] = DefaultDict(dict)
        actions: List[Action] = []

        for current_item in current_items:
            for desired_item in desired_items:
                scores[current_item][desired_item] = self._score_items(
                    a=current_item, b=desired_item
                )

        while len(current_items) > 0 and len(desired_items) > 0:
            max_score = 0
            max_current_item = None
            max_desired_item = None

            for current_item, desired_item in itertools.product(
                current_items, desired_items
            ):
                if scores[current_item][desired_item] > max_score:
                    max_score = scores[current_item][desired_item]
                    max_current_item = current_item
                    max_desired_item = desired_item

            if max_current_item is None or max_desired_item is None:
                raise Exception()

            # max_score is not really important now
            # max_current_item and max_desired item hold values to work on

            current_items.remove(max_current_item)
            desired_items.remove(max_desired_item)

            for k, v in max_desired_item.items():
                if (k not in max_current_item and v != "") or (
                    k in max_current_item and max_current_item[k] != v
                ):
                    actions.append(
                        Action(
                            kind=ActionKind.PATCH,
                            path=f"{current_path}/{max_current_item['.id']}",
                            set_dict=max_desired_item,
                            current_dict=max_current_item,
                        )
                    )
                    break

        for current_item in current_items:
            actions.append(
                Action(
                    kind=ActionKind.DELETE,
                    path=f"{current_path}/{current_item['.id']}",
                    current_dict=current_item,
                )
            )

        for desired_item in desired_items:
            actions.append(
                Action(
                    kind=ActionKind.PUT,
                    path=current_path,
                    set_dict=desired_item,
                )
            )

        return actions

    async def _analyze_dict(
        self,
        current_path: str,
        analyzed_dict: Dict[str, str],
    ) -> List[Action]:
        current_state = await self._call(method=self.session.get, endpoint=current_path)
        desired_state = analyzed_dict

        for k, v in desired_state.items():
            if current_state[k] != v:
                return [
                    Action(
                        kind=ActionKind.POST,
                        path=f"{current_path}/set",
                        set_dict=analyzed_dict,
                        current_dict=current_state,
                    )
                ]

        return []

    async def _analyze(
        self,
        current_path: str,
        tree: Dict[str, Any],
    ) -> List[Action]:
        awaitables = []

        for k, v in tree.items():
            item_path = f"{current_path}/{k}"

            if isinstance(v, list):
                awaitables.append(
                    self._analyze_list(current_path=item_path, analyzed_list=v)
                )
            elif (
                isinstance(v, dict)
                and len(v.values()) > 0
                and isinstance(next(iter(v.values())), str)
            ):
                awaitables.append(
                    self._analyze_dict(current_path=item_path, analyzed_dict=v)
                )
            else:  # No idea what is this, traverse again
                awaitables.append(self._analyze(current_path=item_path, tree=v))

        return list(itertools.chain(*await asyncio.gather(*awaitables)))

    async def _apply(
        self,
        actions: List[Action],
    ) -> None:
        with Progress(
            console=self.console,
            expand=True,
        ) as progress:
            padding_left = " " * 10
            patch_actions_available = len(
                [a for a in actions if a.kind == ActionKind.PATCH]
            )
            put_actions_available = len(
                [a for a in actions if a.kind == ActionKind.PUT]
            )
            delete_actions_available = len(
                [a for a in actions if a.kind == ActionKind.DELETE]
            )
            post_actions_available = len(
                [a for a in actions if a.kind == ActionKind.POST]
            )

            patch_progress = progress.add_task(
                f"{padding_left}[cyan] Patching objects...",
                total=patch_actions_available,
                visible=patch_actions_available > 0,
            )
            put_progress = progress.add_task(
                f"{padding_left}[green] Putting objects...",
                total=put_actions_available,
                visible=put_actions_available > 0,
            )
            delete_progress = progress.add_task(
                f"{padding_left}[red] Deleting objects...",
                total=delete_actions_available,
                visible=delete_actions_available > 0,
            )
            post_progress = progress.add_task(
                f"{padding_left}[cyan] Posting objects...",
                total=post_actions_available,
                visible=post_actions_available > 0,
            )

            # These actions must be executed one after another thus no asyncio.gather possible
            for action in actions:
                if action.kind == ActionKind.PATCH:
                    result = await self._call(
                        method=self.session.patch,
                        endpoint=action.path,
                        json=action.set_dict,
                    )
                    progress.update(patch_progress, advance=1)

                elif action.kind == ActionKind.PUT:
                    result = await self._call(
                        method=self.session.put,
                        endpoint=action.path,
                        json=action.set_dict,
                    )
                    progress.update(put_progress, advance=1)

                elif action.kind == ActionKind.DELETE:
                    result = await self._call(
                        method=self.session.delete,
                        endpoint=action.path,
                    )
                    progress.update(delete_progress, advance=1)

                elif action.kind == ActionKind.POST:
                    result = await self._call(
                        method=self.session.post,
                        endpoint=action.path,
                        json=action.set_dict,
                    )
                    progress.update(post_progress, advance=1)

                else:
                    raise Exception()

                if result is not None and "error" in result:
                    self.console.log("Error while executing", action)
                    self.console.log("Result", result)
                    raise Exception()

    def _print_diff(
        self,
        actions: List[Action],
    ) -> None:
        self.console.print()

        for action in actions:
            if action.kind in (ActionKind.POST, ActionKind.PATCH):
                color = "cyan"
            elif action.kind == ActionKind.DELETE:
                color = "red"
            elif action.kind == ActionKind.PUT:
                color = "green"
            else:
                color = ""

            self.console.print(
                f"[magenta]{action.path}[/magenta] [bold {color}]{action.kind.name}[/bold {color}]:"
            )

            for line in action.diff():
                self.console.print(f"  {line}")

            self.console.print()

    async def run(self) -> None:
        async with aiohttp.ClientSession() as session:
            self.session = session

            self.console.log("Analyzing desired and current configurations...")
            actions = await self._analyze(
                current_path="",
                tree=self.desired_tree,
            )
            self.console.log(f"Analysis done. Pending actions: {len(actions)}.")

            if len(actions) == 0:
                return

            # This sort is 1) a "safe" heuristic 2) needed for element ids to be stable
            actions.sort(key=lambda action: action.kind.value)

            self.console.log("List of differences:")
            self._print_diff(actions=actions)

            self.console.log("Applying actions to synchronize the configuration...")
            await self._apply(actions=actions)
            self.console.log("All changes applied!")
