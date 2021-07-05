from functools import cache
from typing import Union


@cache
def mt_str(i: Union[int, str]) -> str:
    if isinstance(i, str):
        return i

    return hex(i)[2:]


@cache
def mt_int(i: Union[int, str]) -> int:
    if isinstance(i, int):
        return i

    if i[0] == "*":
        return int(i[1:], 16)

    return int(i, 16)
