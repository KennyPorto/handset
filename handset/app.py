import os
import re
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

from jeepney import MatchRule
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection
from jeepney.wrappers import DBusErrorResponse
from PySide6.QtCore import Property, QObject, QSettings, QStandardPaths, QTimer, QUrl, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import __version__
from .contacts import Contacts, download
from .desktop import ACTION_INVOKED, APP_ID, Notifier, request_autostart
from .telephony import ROOT, Bluetooth, Telephony

QML_DIR = Path(__file__).parent / "qml"
ICON = Path(__file__).parent.parent / "data" / f"{APP_ID}.svg"  # source checkouts; installs use the theme


class Watcher(QObject):
    """Listens on its own bus connection so the UI thread never blocks on signals.

    Runs on a daemon thread: it blocks in receive() forever, and a QThread still running
    at quit aborts the app."""
    telephony_changed = Signal()
    notification_action = Signal(int, str)

    def run(self):
        # Without this thread no incoming call would show, so never let it die quietly.
        while True:
            try:
                self._listen()
            except Exception as e:
                print(f"handset: lost the session bus, listening again: {e}", file=sys.stderr)
                time.sleep(5)

    def _listen(self):
        conn = open_dbus_connection("SESSION")
        try:
            telephony = MatchRule(type="signal", path_namespace=ROOT)
            for rule in (telephony, ACTION_INVOKED):
                conn.send_and_get_reply(message_bus.AddMatch(rule))
            self.telephony_changed.emit()  # catch up on anything missed while not listening
            while True:
                msg = conn.receive()
                if telephony.matches(msg):
                    self.telephony_changed.emit()
                elif ACTION_INVOKED.matches(msg):
                    self.notification_action.emit(*msg.body)
        finally:
            conn.close()


class Backend(QObject):
    changed = Signal()
    ringing = Signal()          # a new call is ringing: bring the window forward
    message = Signal(str)       # short feedback for the user
    contactsChanged = Signal()
    _connect_finished = Signal(str)
    _contacts_finished = Signal(object, bool)  # phonebook (None on failure), asked by the user
    _autostart_finished = Signal(object, bool)  # now on (None: no portal), asked for

    def __init__(self):
        super().__init__()
        conn = open_dbus_connection("SESSION")
        self.telephony = Telephony(conn)
        self.notifier = Notifier(conn)
        self.bluetooth = Bluetooth()
        self.settings = QSettings()
        self._phones, self._calls = [], []
        self._phone_name = ""
        self._active_since = {}   # call path -> ms since epoch, for the call timer
        self._notifications = {}  # ringing call path -> notification id
        self._answering = set()   # ringing calls we asked the phone to answer
        self._connecting = False
        self._muted = False
        cache = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.GenericCacheLocation)
        self.cache_dir = Path(cache) / "handset"
        self.phonebook = Contacts(self.cache_dir)
        self._syncing = False
        self._connect_finished.connect(self._on_connect_finished)
        self._contacts_finished.connect(self._on_contacts_finished)
        self._autostart_finished.connect(self._on_autostart_finished)
        self.refresh()

    # Properties for QML

    connected = Property(bool, lambda self: bool(self._phones), notify=changed)
    connecting = Property(bool, lambda self: self._connecting, notify=changed)
    phoneName = Property(str, lambda self: self._phone_name, notify=changed)
    muted = Property(bool, lambda self: self._muted, notify=changed)
    version = Property(str, lambda self: __version__, constant=True)
    autostart = Property(bool, lambda self: self.settings.value("autostart", False, bool), notify=changed)

    syncingContacts = Property(bool, lambda self: self._syncing, notify=contactsChanged)
    useContacts = Property(bool, lambda self: self.settings.value("useContacts", True, bool),
                           notify=contactsChanged)
    contacts = Property("QVariantList", lambda self: self.phonebook.items, notify=contactsChanged)
    favourites = Property("QVariantList", lambda self: self.phonebook.favourites, notify=contactsChanged)
    recent = Property("QVariantList", lambda self: self.phonebook.recent, notify=contactsChanged)

    @Property("QVariantList", notify=changed)
    def calls(self):
        return [{"path": c.path, "caller": c.caller, "number": c.number, "hasName": bool(c.name),
                 "state": c.state, "ringing": c.ringing, "answering": c.path in self._answering,
                 "activeSince": self._active_since.get(c.path, 0)} for c in self._calls]

    # State

    @Slot()
    def refresh(self):
        phones, calls = self.telephony.state()
        calls = [c if c.name else replace(c, name=self.phonebook.name_for(c.number)) for c in calls]
        connected = phones and not self._phones
        call_ended = self._calls and not calls
        if phones != self._phones:
            self._phone_name = self._lookup_name(phones)
        self._phones, self._calls = phones, calls
        if call_ended and self._muted and phones:
            # PipeWire keeps the mic volume, so the next call would start muted, and its
            # AT+VGM=0 at ring time can block Answer.
            self._run("Couldn't turn the microphone back on", self.telephony.set_muted, phones[0], False)
        if connected or call_ended:  # after storing phones: syncContacts needs them
            self.syncContacts(False)

        now = time.time() * 1000
        self._active_since = {c.path: self._active_since.get(c.path, now)
                              for c in calls if c.state == "active"}
        self._answering &= {c.path for c in calls if c.ringing}
        self._update_notifications(calls)
        self._muted = self._read_muted() if calls else False
        self.changed.emit()

    def _lookup_name(self, phones):
        if not phones:
            return ""
        try:
            return self.bluetooth.alias(self.telephony.address(phones[0]))
        except Exception:  # the name is cosmetic; never fail a refresh over it
            return "Phone"

    def _read_muted(self):
        try:
            return self.telephony.muted(self._phones[0])
        except DBusErrorResponse:
            return False

    def _update_notifications(self, calls):
        ringing = {c.path: c for c in calls if c.ringing}
        for path, call in ringing.items():
            if path not in self._notifications:
                self._notifications[path] = self._notify(call)
                self.ringing.emit()
        for path in [p for p in self._notifications if p not in ringing]:
            notification_id = self._notifications.pop(path)
            if notification_id:
                try:
                    self.notifier.close(notification_id)
                except DBusErrorResponse:
                    pass

    def _notify(self, call):
        try:
            return self.notifier.incoming_call(call.caller)
        except DBusErrorResponse:  # no notification server: the window still pops up
            return 0

    def _find(self, path):
        return next((c for c in self._calls if c.path == path), None)

    def _run(self, failure, action, *args):
        try:
            action(*args)
            return True
        except DBusErrorResponse as e:
            print(f"handset: {failure}: {e}", file=sys.stderr)
            self.message.emit(failure)
            return False

    # Actions

    @Slot(str)
    def answer(self, path):
        if (call := self._find(path)) and self._run("Couldn't answer the call", self.telephony.answer, call):
            # PipeWire queues the answer behind other commands to the phone and doesn't time
            # out, so on a weak link it can take long or never arrive: show it's on its way.
            self._answering.add(path)
            self.changed.emit()
            QTimer.singleShot(10_000, lambda: self._answer_timed_out(path))

    def _answer_timed_out(self, path):
        if path in self._answering:
            self._answering.discard(path)
            self.message.emit("The phone didn't respond. Answer on the phone.")
            self.changed.emit()

    @Slot(str)
    def hangUp(self, path):
        if call := self._find(path):
            self._run("Couldn't end the call", self.telephony.hang_up, call)

    @Slot(str)
    def dial(self, number):
        # PipeWire refuses anything but these, and contacts come as "+351 912 345 678".
        number = re.sub(r"[^0-9+*#]", "", number)
        if number and self._phones:
            self._run("Couldn't place the call", self.telephony.dial, self._phones[0], number)

    @Slot(str)
    def sendTones(self, tones):
        if self._phones:
            self._run("Couldn't send the tone", self.telephony.send_tones, self._phones[0], tones)

    @Slot(bool)
    def setMuted(self, muted):
        if self._phones:
            self._run("Couldn't change the microphone", self.telephony.set_muted, self._phones[0], muted)
            self.refresh()

    @Slot(int, str)
    def onNotificationAction(self, notification_id, action):
        path = next((p for p, n in self._notifications.items() if n == notification_id), None)
        if not path:
            return
        if action == "answer":
            self.answer(path)
            self.ringing.emit()
        elif action == "decline":
            self.hangUp(path)

    @Slot()
    def connectPhone(self):
        if self._connecting:
            return
        self._connecting = True
        self.changed.emit()

        def work():
            try:
                self.bluetooth.connect()
            except LookupError as e:
                self._connect_finished.emit(str(e))
            except Exception as e:  # BlueZ: phone off, out of range, Bluetooth disabled
                print(f"handset: connect failed: {e}", file=sys.stderr)
                self._connect_finished.emit("Couldn't reach your phone. Is Bluetooth on and the phone nearby?")
            else:
                self._connect_finished.emit("")

        threading.Thread(target=work, daemon=True).start()

    def _on_connect_finished(self, error):
        self._connecting = False
        if error:
            self.message.emit(error)
        self.refresh()

    @Slot()
    def disconnectPhone(self):
        if not self._phones:
            return
        try:
            address = self.telephony.address(self._phones[0])
        except DBusErrorResponse:
            return  # already gone

        def work():  # BlueZ can take seconds; the watcher sees the phone go
            try:
                self.bluetooth.disconnect(address)
            except Exception as e:
                print(f"handset: disconnect failed: {e}", file=sys.stderr)
                self.message.emit("Couldn't disconnect the phone")

        threading.Thread(target=work, daemon=True).start()

    @Slot(bool)
    def syncContacts(self, asked=True):
        """Fetch the phone's contacts. Quiet unless the user asked: they're optional."""
        if self._syncing or not self._phones or not self.useContacts:
            return
        try:
            address = self.telephony.address(self._phones[0])
        except DBusErrorResponse:
            return
        self._syncing = True
        self.contactsChanged.emit()

        def work():
            try:
                self._contacts_finished.emit(download(address, self.cache_dir), asked)
            except Exception as e:  # sharing off, permission refused, no obexd
                print(f"handset: contacts: {e}", file=sys.stderr)
                self._contacts_finished.emit(None, asked)

        threading.Thread(target=work, daemon=True).start()

    def _on_contacts_finished(self, items, asked):
        self._syncing = False
        if not self.useContacts:
            pass  # turned off while downloading: keep nothing
        elif items is not None:
            self.phonebook.replace(items)
            self.refresh()  # name calls that are already showing
        elif asked:
            self.message.emit("Couldn't get your contacts. Allow contact sharing for this PC in "
                              "the phone's Bluetooth settings.")
        self.contactsChanged.emit()

    @Slot(bool)
    def setUseContacts(self, enable):
        """Off deletes the saved contacts and stops syncing; on syncs right away."""
        self.settings.setValue("useContacts", enable)
        if enable:
            self.syncContacts(True)
        else:
            self.phonebook.clear()
        self.contactsChanged.emit()
        self.refresh()

    @Slot(bool)
    def setAutostart(self, enable):
        def work():  # waits for the user to answer the desktop's dialog
            try:
                self._autostart_finished.emit(request_autostart(enable), enable)
            except (DBusErrorResponse, TimeoutError) as e:
                print(f"handset: autostart: {e}", file=sys.stderr)
                self._autostart_finished.emit(None, enable)

        threading.Thread(target=work, daemon=True).start()

    def _on_autostart_finished(self, enabled, asked):
        if enabled is None:
            self.message.emit("Your desktop doesn't support starting apps at login")
        else:
            self.settings.setValue("autostart", enabled)
            if asked and not enabled:
                self.message.emit("Starting at login wasn't allowed. You can allow it in the system settings.")
        self.changed.emit()


def show(window):
    window.show()
    window.raise_()
    window.requestActivate()


def main():
    QApplication.setOrganizationName("handset")
    QApplication.setApplicationName("handset")
    app = QApplication(sys.argv)
    app.setApplicationDisplayName("Handset")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon.fromTheme(APP_ID, QIcon(str(ICON)) if ICON.exists() else QIcon()))
    app.setQuitOnLastWindowClosed(False)  # closing the window keeps listening for calls

    # One copy only: a second launch asks the running one to show its window, then exits.
    instance = f"{APP_ID}-{os.getuid()}"
    other = QLocalSocket()
    other.connectToServer(instance)
    if other.waitForConnected(500):
        if "--hidden" not in sys.argv:
            other.write(b"show")
            other.waitForBytesWritten(500)
        return 0
    QLocalServer.removeServer(instance)  # left behind if a previous copy crashed
    server = QLocalServer()
    server.listen(instance)
    if not os.environ.get("QT_QUICK_CONTROLS_STYLE"):
        QQuickStyle.setStyle("org.kde.desktop")

    backend = Backend()
    engine = QQmlApplicationEngine()
    engine.setInitialProperties({"backend": backend})
    engine.load(QUrl.fromLocalFile(str(QML_DIR / "Main.qml")))
    if not engine.rootObjects():
        return 1
    window = engine.rootObjects()[0]

    tray = QSystemTrayIcon(app.windowIcon())
    tray.setToolTip("Handset")
    menu = QMenu()
    menu.addAction(QIcon.fromTheme("window"), "Show Handset", lambda: show(window))
    menu.addAction(QIcon.fromTheme("application-exit"), "Quit", app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: reason == QSystemTrayIcon.ActivationReason.Trigger and (
        window.hide() if window.isVisible() else show(window)))
    tray.show()

    backend.ringing.connect(lambda: show(window))
    server.newConnection.connect(lambda: server.nextPendingConnection().readyRead.connect(lambda: show(window)))
    watcher = Watcher()
    watcher.telephony_changed.connect(backend.refresh)
    watcher.notification_action.connect(backend.onNotificationAction)
    threading.Thread(target=watcher.run, daemon=True).start()

    if not backend.connected:
        backend.connectPhone()
    if "--hidden" not in sys.argv:
        show(window)
    return app.exec()
