import unittest.mock as mock

from mtsync.action import ActionKind
from mtsync.connection import Connection
from mtsync.settings import Settings
from mtsync.synchronizer import Synchronizer
from rich.console import Console
from testslide import StrictMock
from testslide.dsl import context
from mtsync.imagined import Imagined


@context
def ImaginedTest(context):
    @context.example
    async def initial_state(self):
        initial_state = [
            {"key": "value1", ".id": "1"},
            {"key": "value2", ".id": "2"},
            {"key": "value3", ".id": "3"},
        ]
        im = Imagined(initial_state=initial_state)
        self.assertEqual(im.state, initial_state)

    @context.example
    async def append(self):
        initial_state = [
            {"key": "value1", ".id": "1"},
            {"key": "value2", ".id": "2"},
        ]
        im = Imagined(initial_state=initial_state)
        im.append(item={"key": "value3"})
        self.assertEqual(
            im.state,
            [
                {"key": "value1", ".id": "1"},
                {"key": "value2", ".id": "2"},
                {"key": "value3", ".id": "3"},
            ],
        )

    @context.example
    async def delete(self):
        initial_state = [
            {"key": "value1", ".id": "1"},
            {"key": "value2", ".id": "2"},
            {"key": "value3", ".id": "3"},
        ]
        im = Imagined(initial_state=initial_state)
        im.delete(id="2")
        self.assertEqual(
            im.state,
            [
                {"key": "value1", ".id": "1"},
                {"key": "value3", ".id": "2"},
            ],
        )

    @context.example
    async def move(self):
        initial_state = [
            {"key": "value1", ".id": "1"},
            {"key": "value2", ".id": "2"},
            {"key": "value3", ".id": "3"},
        ]
        im = Imagined(initial_state=initial_state)
        im.move(number=3, destination=2)
        self.assertEqual(
            im.state,
            [
                {"key": "value1", ".id": "1"},
                {"key": "value3", ".id": "2"},
                {"key": "value2", ".id": "3"},
            ],
        )
