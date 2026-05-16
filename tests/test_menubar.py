from app.mac_dictation.menubar import WhisperTypeMenuBarApp


def test_menubar_app_retains_status_item_and_menu_slots():
    app = WhisperTypeMenuBarApp(run_listener=lambda: None)

    assert app.status_title == "WT"
    assert app._status_item is None
    assert app._menu is None
