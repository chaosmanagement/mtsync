import asyncio
import itertools
import json
from copy import copy
from typing import Any, Callable, DefaultDict, Dict, Generator, List, Optional, Tuple

from frozendict import frozendict
from rich import print as rich_print
from rich.console import Console
from rich.progress import Progress

from mtsync.action import Action, ActionKind
from mtsync.connection import Connection
from mtsync.constants import non_movable_namespaces
from mtsync.imagined import Imagined


class Synchronizer:
    def __init__(
        self,
        console: Console,
        connection: Connection,
    ) -> None:
        self.console = console
        self.connection = connection

    @staticmethod
    def _score_items(
        a: Dict[str, str],
        b: Dict[str, str],
    ) -> int:
        # `a` is meant to have less (or equal) key count
        if len(a.keys()) > len(b.keys()):
            a, b = b, a

        score = 0

        for k, v in a.items():
            if k == ".id":
                continue

            if k in b and b[k] == v:
                score += 1

        return score

    @staticmethod
    def _test_equality(
        a: Dict[str, str],
        b: Dict[str, str],
    ) -> bool:
        a = dict(filter(lambda x: x[0] != ".id", a.items()))
        b = dict(filter(lambda x: x[0] != ".id", b.items()))

        if len(a.keys()) != len(b.keys()):
            return False

        return Synchronizer._score_items(a=a, b=b) == len(a.keys())

    @staticmethod
    def _freeze_list(
        l: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        return [frozendict(d) for d in l]

    async def _analyze_list_add_remove(
        self,
        current_path: str,
        current_items: List[Dict[str, str]],
        desired_items: List[Dict[str, str]],
        imagined_items: Imagined,
    ) -> List[Action]:
        scores: Dict[Any, Dict[Any, Any]] = DefaultDict(dict)
        actions: List[Action] = []

        current_items = self._freeze_list(current_items)
        desired_items = self._freeze_list(desired_items)

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
                    imagined_items.update(
                        id=max_current_item[".id"], new_state=max_desired_item
                    )
                    break

        for desired_item in desired_items:
            actions.append(
                Action(
                    kind=ActionKind.PUT,
                    path=current_path,
                    set_dict=desired_item,
                )
            )
            imagined_items.append(desired_item)

        for current_item in current_items:
            actions.append(
                Action(
                    kind=ActionKind.DELETE,
                    path=f"{current_path}/{current_item['.id']}",
                    current_dict=current_item,
                )
            )
            imagined_items.delete(id=current_item[".id"])

        return actions

    async def _analyze_list_reorder(
        self,
        current_path: str,
        imagined_items: Imagined,
        desired_items: List[Dict[str, str]],
    ) -> List[Action]:
        if current_path in non_movable_namespaces:
            return []

        actions: List[Action] = []

        for desired_i, desired_item in enumerate(desired_items):
            if self._test_equality(desired_item, imagined_items.state[desired_i]):
                continue

            for imagined_item in imagined_items.state[desired_i + 1 :]:
                if self._test_equality(desired_item, imagined_item):
                    current_id = imagined_item[".id"]
                    desired_id = imagined_items.state[desired_i][".id"]
                    imagined_items.move(
                        number=current_id,
                        destination=desired_id,
                    )
                    actions.append(
                        Action(
                            kind=ActionKind.POST,
                            path=f"{current_path}/move",
                            set_dict={
                                "numbers": current_id,
                                "destination": desired_id,
                            },
                        )
                    )
                    break

        return actions

    async def _analyze_list(
        self,
        current_path: str,
        analyzed_list: List[Dict[str, str]],
    ) -> List[Action]:
        desired_items = analyzed_list
        proplist = set(itertools.chain(*[item.keys() for item in desired_items])) | {
            ".id"
        }

        current_items = await self.connection.get(
            endpoint=current_path,
            params={
                "dynamic": "false",
                ".proplist": ",".join(proplist),
            },
        )

        actions: List[Action] = []
        imagined_items = Imagined(initial_state=current_items)

        actions += await self._analyze_list_add_remove(
            current_path=current_path,
            current_items=current_items,
            desired_items=desired_items,
            imagined_items=imagined_items,
        )

        actions += await self._analyze_list_reorder(
            current_path=current_path,
            imagined_items=imagined_items,
            desired_items=desired_items,
        )

        return actions

    async def _analyze_dict(
        self,
        current_path: str,
        analyzed_dict: Dict[str, str],
    ) -> List[Action]:
        current_state = await self.connection.get(endpoint=current_path)
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

        if tree is None:
            return []

        if isinstance(tree, list):
            raise Exception("Expected input data to be a dictionary/mapping")

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
                    result = await self.connection.patch(
                        endpoint=action.path,
                        json=action.set_dict,
                    )
                    progress.update(patch_progress, advance=1)

                elif action.kind == ActionKind.PUT:
                    result = await self.connection.put(
                        endpoint=action.path,
                        json=action.set_dict,
                    )
                    progress.update(put_progress, advance=1)

                elif action.kind == ActionKind.DELETE:
                    result = await self.connection.delete(
                        endpoint=action.path,
                    )
                    progress.update(delete_progress, advance=1)

                elif action.kind == ActionKind.POST:
                    result = await self.connection.post(
                        endpoint=action.path,
                        json=action.set_dict,
                    )
                    progress.update(post_progress, advance=1)

                else:
                    raise Exception(f"Unknown action kind: {action.kind}")

                if result is not None and "error" in result:
                    if (
                        "detail" in result
                        and result["detail"] == "no such command"
                        and action.path.endswith("/move")
                    ):
                        continue

                    self.console.log("Error while executing", action)
                    self.console.log("Result", result)
                    raise Exception()

    def _human_readable_diff(
        self,
        actions: List[Action],
    ) -> str:
        lines: List[str] = ["", ""]

        for action in actions:
            if action.kind in (ActionKind.POST, ActionKind.PATCH):
                color = "cyan"
            elif action.kind == ActionKind.DELETE:
                color = "red"
            elif action.kind == ActionKind.PUT:
                color = "green"
            else:
                color = ""

            lines.append(
                f"[magenta]{action.path}[/magenta] [bold {color}]{action.kind.name}[/bold {color}]:"
            )

            for line in action.diff():
                lines.append(f"  {line}")

            lines.append("")

        return "\n".join(lines)

    async def run(
        self,
        desired_tree: Dict,
    ) -> None:
        self.console.log("Analyzing desired and current configurations...")
        actions = await self._analyze(
            current_path="",
            tree=desired_tree,
        )
        self.console.log(f"Analysis done. Pending actions: {len(actions)}.")

        if len(actions) == 0:
            return

        # This sort is 1) a "safe" heuristic 2) needed for element ids to be stable
        actions.sort(key=lambda action: action.kind.value)

        self.console.log(
            "List of differences:", self._human_readable_diff(actions=actions)
        )

        self.console.log("Applying actions to synchronize the configuration...")
        await self._apply(actions=actions)
        self.console.log("All changes applied!")
