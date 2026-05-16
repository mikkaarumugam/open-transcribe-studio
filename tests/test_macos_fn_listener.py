from app.mac_dictation.macos_fn import FN_FLAG_MASK, MacFnStateTracker


class FakeController:
    def __init__(self):
        self.events = []

    def on_fn_down(self):
        self.events.append("down")

    def on_fn_up(self):
        self.events.append("up")


def test_fn_tracker_emits_down_when_fn_flag_appears():
    controller = FakeController()
    state_changes = []
    tracker = MacFnStateTracker(controller, on_state_change=state_changes.append)

    tracker.handle_flags(0)
    tracker.handle_flags(FN_FLAG_MASK)

    assert controller.events == ["down"]
    assert state_changes == ["down"]


def test_fn_tracker_emits_up_when_fn_flag_disappears():
    controller = FakeController()
    state_changes = []
    tracker = MacFnStateTracker(controller, on_state_change=state_changes.append)

    tracker.handle_flags(FN_FLAG_MASK)
    tracker.handle_flags(0)

    assert controller.events == ["down", "up"]
    assert state_changes == ["down", "up"]


def test_fn_tracker_does_not_repeat_down_while_held():
    controller = FakeController()
    tracker = MacFnStateTracker(controller)

    tracker.handle_flags(FN_FLAG_MASK)
    tracker.handle_flags(FN_FLAG_MASK)
    tracker.handle_flags(FN_FLAG_MASK)
    tracker.handle_flags(0)

    assert controller.events == ["down", "up"]
