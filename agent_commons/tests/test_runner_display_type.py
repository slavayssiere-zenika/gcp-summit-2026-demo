import pytest

from agent_commons.runner import run_agent_and_collect


# Mock structures equivalent to ADK event models
class MockPayload:
    def __init__(self, resource_uri):
        self.payload = {"resource_uri": resource_uri}


class MockActions:
    def __init__(self, widgets):
        self.render_ui_widgets = widgets

    def __iter__(self):
        return iter(self.render_ui_widgets)


class MockPart:
    def __init__(self, text=""):
        self.text = text


class MockContent:
    def __init__(self, text=""):
        self.parts = [MockPart(text)]
        self.role = "model"


class MockEvent:
    def __init__(self, text="", actions=None, step=None):
        self.content = MockContent(text)
        self.actions = actions
        self.step = step


class MockStep:
    def __init__(self, text="", is_thought=False):
        self.text = text
        self.is_thought = is_thought
        self.model_dump = lambda: {"text": text, "is_thought": is_thought}


class MockRunner:
    def __init__(self, events):
        self.events = events

    async def run_async(self, user_id, session_id, new_message):
        for event in self.events:
            yield event


@pytest.mark.asyncio
async def test_run_agent_and_collect_display_type_empty():
    """
    Test that run_agent_and_collect correctly extracts display_type="empty"
    from an ADK event that emits a render_ui_widgets action with ui://empty.
    """
    actions = MockActions(widgets=[MockPayload("ui://empty")])
    events = [
        MockEvent(text="This is an empty test", actions=actions)
    ]
    runner = MockRunner(events)

    response_text, steps, thoughts, input_t, output_t, data, display_type = await run_agent_and_collect(
        runner=runner,
        user_id="user_1",
        session_id="session_1",
        query="test query",
        agent_name="test_agent",
        agent_prefix="[TEST]"
    )

    assert display_type == "empty"
    assert response_text == "This is an empty test"


@pytest.mark.asyncio
async def test_run_agent_and_collect_display_type_custom():
    """
    Test that run_agent_and_collect correctly extracts custom display_type
    from an ADK event that emits a render_ui_widgets action.
    """
    actions = MockActions(widgets=[MockPayload("ui://consultants")])
    events = [
        MockEvent(text="Here are consultants", actions=actions)
    ]
    runner = MockRunner(events)

    response_text, steps, thoughts, input_t, output_t, data, display_type = await run_agent_and_collect(
        runner=runner,
        user_id="user_1",
        session_id="session_1",
        query="test query",
        agent_name="test_agent",
        agent_prefix="[TEST]"
    )

    assert display_type == "consultants"


@pytest.mark.asyncio
async def test_run_agent_and_collect_no_display_type():
    """
    Test that run_agent_and_collect returns None for display_type
    when no render_ui_widgets action is emitted.
    """
    events = [
        MockEvent(text="Just text")
    ]
    runner = MockRunner(events)

    response_text, steps, thoughts, input_t, output_t, data, display_type = await run_agent_and_collect(
        runner=runner,
        user_id="user_1",
        session_id="session_1",
        query="test query",
        agent_name="test_agent",
        agent_prefix="[TEST]"
    )

    assert display_type is None
