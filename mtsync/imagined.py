from copy import copy
from typing import Dict, List, Optional, Union

from mtsync.helpers import mt_int, mt_str


class Imagined:
    def __init__(
        self,
        initial_state: List[Dict[str, str]],
    ) -> None:
        self.state = copy(initial_state)

    @property
    def _max_id(self) -> int:
        # In an ideal world this wouldn't have been a property
        max_id = 1
        for item in self.state:
            item_id = mt_int(item[".id"])
            if item_id > max_id:
                max_id = item_id

        return max_id

    def _sort(self) -> None:
        self.state.sort(key=lambda x: mt_int(x[".id"]))

    def update(
        self,
        id: str,
        new_state: Dict[str, str],
    ) -> None:
        for i, item in enumerate(self.state):
            if item[".id"] == mt_str(id):
                self.state[i] = new_state | {".id": item[".id"]}
                return

    def append(
        self,
        item: Dict[str, str],
    ) -> None:
        self.state.append(dict(item.items()) | {".id": mt_str(self._max_id + 1)})

    def _move_all_between(
        self,
        bottom: Optional[Union[int, str]],
        top: Optional[Union[int, str]],
        change: int,
    ) -> None:
        for item in self.state:
            item_id = mt_int(item[".id"])
            if (bottom is None or item_id >= mt_int(bottom)) and (
                top is None or item_id < mt_int(top)
            ):
                item_id += change
                item[".id"] = mt_str(item_id)

    def delete(self, id: Union[str, int]) -> None:
        for i, item in enumerate(self.state):
            if item[".id"] == mt_str(id):
                del self.state[i]
                self._move_all_between(bottom=i + 1, top=None, change=-1)
                return

    def move(self, number: Union[int, str], destination: Union[int, str]) -> None:
        source_i = destination_i = None

        for i, item in enumerate(self.state):
            if item[".id"] == mt_str(number):
                source_i = i
            if item[".id"] == mt_str(destination):
                destination_i = i

        if source_i is None or destination_i is None:
            raise Exception(
                f"Unable to find either source id ({source_i}) or destination id ({destination_i})"
            )

        self._move_all_between(bottom=destination, top=number, change=1)

        self.state.insert(destination_i, self.state[source_i])
        del self.state[source_i + 1]  # This assumes items will be moving down
        self.state[destination_i][".id"] = mt_str(destination)
