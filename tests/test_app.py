from types import SimpleNamespace

import pytest

from handset import app
from handset.telephony import Call

PHONE = "/org/pipewire/Telephony/ag1"
ANA = {"name": "Ana", "numbers": [{"number": "+351 912 345 678", "label": "Mobile"}]}


@pytest.fixture
def setup(monkeypatch, tmp_path):
    """A Backend with fake D-Bus services. Returns (backend, phones, pulled):
    add to ``phones`` and call refresh() to connect; ``pulled`` lists the downloads."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    stored = {}  # settings, kept out of the user's real config
    monkeypatch.setattr(app.QSettings, "value", lambda self, key, default, type: stored.get(key, default))
    monkeypatch.setattr(app.QSettings, "setValue", lambda self, key, value: stored.update({key: value}))
    phones = []

    class FakeTelephony:
        def __init__(self, conn):
            pass

        def state(self):
            return list(phones), []

        def address(self, phone):
            return "AA:BB:CC:DD:EE:FF"

    monkeypatch.setattr(app, "open_dbus_connection", lambda bus: None)
    monkeypatch.setattr(app, "Telephony", FakeTelephony)
    monkeypatch.setattr(app, "Notifier", lambda conn: None)
    monkeypatch.setattr(app, "Bluetooth", lambda: None)
    monkeypatch.setattr(app.Backend, "_lookup_name", lambda self, phones: "Phone")
    # Run the download right away instead of on a thread.
    monkeypatch.setattr(app.threading, "Thread", lambda target, daemon: SimpleNamespace(start=target))
    pulled = []
    monkeypatch.setattr(app, "download",
                        lambda address, cache_dir: pulled.append(address) or {"contacts": [ANA]})
    return app.Backend(), phones, pulled


def test_contacts_sync_when_the_phone_connects(setup):
    backend, phones, pulled = setup
    assert pulled == []
    phones.append(PHONE)
    backend.refresh()
    assert pulled == ["AA:BB:CC:DD:EE:FF"]
    assert backend.contacts == [ANA]


def test_turning_contacts_off_deletes_them_and_stops_syncing(setup):
    backend, phones, pulled = setup
    phones.append(PHONE)
    backend.refresh()
    backend.setUseContacts(False)
    assert backend.contacts == []
    assert not backend.phonebook.file.exists()
    backend.syncContacts(True)
    assert pulled == ["AA:BB:CC:DD:EE:FF"]  # no second download

    # A download that finishes after contacts were turned off is dropped.
    backend._on_contacts_finished({"contacts": [ANA]}, False)
    assert backend.contacts == []

    backend.setUseContacts(True)
    assert len(pulled) == 2 and backend.contacts == [ANA]


def test_a_muted_call_unmutes_when_it_ends(setup):
    backend, phones, _ = setup
    phones.append(PHONE)
    call = Call(PHONE + "/call1", "123", "Ana", "active")
    unmuted = []
    backend.telephony.state = lambda: (list(phones), [call])
    backend.telephony.muted = lambda phone: True
    backend.telephony.set_muted = lambda phone, muted: unmuted.append(muted)
    backend.refresh()
    backend.telephony.state = lambda: (list(phones), [])
    backend.refresh()
    assert unmuted == [False]


def test_answering_shows_until_the_phone_responds(setup, monkeypatch):
    backend, phones, _ = setup
    phones.append(PHONE)
    call = Call(PHONE + "/call1", "123", "", "incoming")
    timers, messages = [], []
    monkeypatch.setattr(app.QTimer, "singleShot", lambda ms, fn: timers.append(fn))
    backend.message.connect(messages.append)
    backend.telephony.state = lambda: (list(phones), [call])
    backend.telephony.answer = lambda c: None
    backend.notifier = SimpleNamespace(incoming_call=lambda caller: 1, close=lambda n: None)
    backend.telephony.muted = lambda phone: False
    backend.refresh()
    backend.answer(call.path)
    assert backend.calls[0]["answering"]

    timers[0]()  # the phone never answered
    assert not backend.calls[0]["answering"]
    assert messages == ["The phone didn't respond. Answer on the phone."]

    backend.answer(call.path)
    backend.telephony.state = lambda: (list(phones), [Call(call.path, "123", "", "active")])
    backend.refresh()
    timers[1]()  # answered in time: no message
    assert not backend.calls[0]["answering"] and len(messages) == 1


def test_dialing_sends_only_the_characters_phones_accept(setup):
    backend, phones, _ = setup
    phones.append(PHONE)
    backend.refresh()
    dialed = []
    backend.telephony.dial = lambda phone, number: dialed.append(number)
    backend.dial("+351 (912) 345-678")
    backend.dial("*#06#")
    backend.dial(" - ")
    assert dialed == ["+351912345678", "*#06#"]


def test_start_at_login_follows_the_desktops_answer(setup, monkeypatch):
    backend, _, _ = setup
    messages = []
    backend.message.connect(messages.append)

    monkeypatch.setattr(app, "request_autostart", lambda enable: enable)
    backend.setAutostart(True)
    assert backend.autostart and messages == []

    monkeypatch.setattr(app, "request_autostart", lambda enable: False)  # the user said no
    backend.setAutostart(False)
    backend.setAutostart(True)
    assert not backend.autostart and len(messages) == 1
