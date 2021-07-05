import unittest.mock as mock

from mtsync.action import ActionKind
from mtsync.connection import Connection
from mtsync.imagined import Imagined
from mtsync.settings import Settings
from mtsync.synchronizer import Synchronizer
from rich.console import Console
from testslide import StrictMock
from testslide.dsl import context


@context
def SynchronizerTest(context):
    @context.before
    async def prepare(self):
        self.console = Console()
        self.settings = Settings()
        self.connection = StrictMock(template=Connection)
        self.synchronizer = Synchronizer(
            console=self.console,
            connection=self.connection,
        )

    @context.sub_context
    def score(context):
        @context.sub_context
        def test_equality(context):
            @context.example
            async def simple(self):
                self.assertTrue(
                    Synchronizer._test_equality(
                        a={
                            ".id": "1",
                            "field-a": "a",
                            "field-b": "b",
                        },
                        b={
                            ".id": "1",
                            "field-a": "a",
                            "field-b": "b",
                        },
                    )
                )
                self.assertFalse(
                    Synchronizer._test_equality(
                        a={
                            ".id": "1",
                            "field-a": "a",
                            "field-b": "b",
                        },
                        b={
                            ".id": "1",
                            "field-a": "a",
                            "field-b": "bbb",
                        },
                    )
                )

            @context.example
            async def without_id(self):
                self.assertTrue(
                    Synchronizer._test_equality(
                        a={
                            ".id": "1",
                            "field-a": "a",
                            "field-b": "b",
                        },
                        b={
                            "field-a": "a",
                            "field-b": "b",
                        },
                    )
                )

    @context.sub_context
    def analyze(context):
        @context.sub_context
        def triage(context):
            @context.before
            async def prepare(self):
                self.m_analyze_list = mock.patch.object(
                    self.synchronizer, "_analyze_list"
                ).__enter__()
                self.m_analyze_dict = mock.patch.object(
                    self.synchronizer, "_analyze_dict"
                ).__enter__()

            @context.sub_context
            def empty(context):
                @context.example
                async def dict(self):
                    self.assertEqual(
                        await self.synchronizer._analyze(current_path="", tree={}),
                        [],
                    )
                    self.m_analyze_list.assert_not_called()
                    self.m_analyze_dict.assert_not_called()

                @context.example
                async def list(self):
                    with self.assertRaises(Exception):
                        await self.synchronizer._analyze(current_path="", tree=[])
                    self.m_analyze_list.assert_not_called()
                    self.m_analyze_dict.assert_not_called()

                @context.example
                async def none(self):
                    self.assertEqual(
                        await self.synchronizer._analyze(current_path="", tree=None),
                        [],
                    )
                    self.m_analyze_list.assert_not_called()
                    self.m_analyze_dict.assert_not_called()

            @context.sub_context
            def list(context):
                @context.example
                async def simple(self):
                    inner_list = [
                        {
                            "interface": "bridge",
                            "address": "2010::7/64",
                            "disabled": "false",
                        },
                        {
                            "interface": "bridge",
                            "address": "2010::1/64",
                            "disabled": "false",
                            "comment": "Hello worldd!",
                        },
                    ]

                    await self.synchronizer._analyze(
                        current_path="",
                        tree={
                            "ipv6": {
                                "address": inner_list,
                            }
                        },
                    )
                    self.m_analyze_list.assert_called_with(
                        current_path="/ipv6/address",
                        analyzed_list=inner_list,
                    )

            @context.sub_context
            def dict(context):
                @context.example
                async def simple(self):
                    inner_dict = {"rp-filter": "no"}

                    await self.synchronizer._analyze(
                        current_path="",
                        tree={
                            "ip": {
                                "settings": inner_dict,
                            }
                        },
                    )
                    self.m_analyze_dict.assert_called_with(
                        current_path="/ip/settings",
                        analyzed_dict=inner_dict,
                    )

        @context.sub_context
        def dict(context):
            @context.example
            async def simple(self):
                desired_dict = {
                    "rp-filter": "no",
                    "other-setting": "no",
                }

                self.mock_async_callable(self.connection, "get").to_return_value(
                    {
                        "rp-filter": "yes",
                        "other-setting": "no",
                    }
                ).and_assert_called_once()

                response = await self.synchronizer._analyze_dict(
                    current_path="/ip/settings",
                    analyzed_dict=desired_dict,
                )

                self.assertEqual(len(response), 1)
                self.assertEqual(response[0].set_dict["rp-filter"], "no")
                self.assertEqual(response[0].set_dict["other-setting"], "no")

            @context.example
            async def no_op(self):
                desired_dict = {
                    "rp-filter": "no",
                    "other-setting": "no",
                }

                self.mock_async_callable(self.connection, "get").to_return_value(
                    {
                        "rp-filter": "no",
                        "other-setting": "no",
                    }
                ).and_assert_called_once()

                response = await self.synchronizer._analyze_dict(
                    current_path="/ip/settings",
                    analyzed_dict=desired_dict,
                )

                self.assertEqual(len(response), 0)

        @context.sub_context
        def list(context):
            @context.sub_context
            def triage(context):
                pass  # @TODO

            @context.sub_context
            def add_remove(context):
                pass  # @TODO

            @context.sub_context
            def reorder(context):
                @context.example
                async def simple(self):
                    actions = await self.synchronizer._analyze_list_reorder(
                        current_path="/ip/example",
                        imagined_items=Imagined(
                            initial_state=[
                                {"field": "value2", ".id": "1"},
                                {"field": "value3", ".id": "2"},
                                {"field": "value1", ".id": "3"},
                            ]
                        ),
                        desired_items=[
                            {"field": "value1"},
                            {"field": "value2"},
                            {"field": "value3"},
                        ],
                    )

                    self.assertEqual(len(actions), 1, f"Got actions: {actions}")

                    action = actions[0]

                    self.assertEqual(action.kind, ActionKind.POST)
                    self.assertEqual(action.path, "/ip/example/move")
                    self.assertEqual(
                        action.set_dict,
                        {
                            "numbers": "3",
                            "destination": "1",
                        },
                    )

                @context.example
                async def same(self):
                    actions = await self.synchronizer._analyze_list_reorder(
                        current_path="/ip/example",
                        imagined_items=Imagined(
                            initial_state=[
                                {"field": "value", ".id": "1"},
                                {"field": "value", ".id": "2"},
                            ]
                        ),
                        desired_items=[
                            {"field": "value"},
                            {"field": "value"},
                        ],
                    )

                    self.assertEqual(len(actions), 0, f"Got actions: {actions}")

                @context.example
                async def long(self):
                    actions = await self.synchronizer._analyze_list_reorder(
                        current_path="/ip/example",
                        imagined_items=Imagined(
                            initial_state=[
                                {"field": "value2", ".id": "1"},
                                {"field": "value3", ".id": "2"},
                                {"field": "value1", ".id": "3"},
                                {"field": "value5", ".id": "4"},
                                {"field": "value4", ".id": "5"},
                                {"field": "value6", ".id": "6"},
                            ]
                        ),
                        desired_items=[
                            {"field": "value1"},
                            {"field": "value2"},
                            {"field": "value3"},
                            {"field": "value4"},
                            {"field": "value5"},
                            {"field": "value6"},
                        ],
                    )

                    self.assertEqual(len(actions), 2)

                    self.assertEqual(
                        actions[0].set_dict,
                        {"numbers": "3", "destination": "1"},
                    )
                    self.assertEqual(
                        actions[1].set_dict,
                        {"numbers": "5", "destination": "4"},
                    )
