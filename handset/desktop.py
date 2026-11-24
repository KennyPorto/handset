"""Desktop integration: notifications with call buttons, and starting at login."""
import secrets

from jeepney import MatchRule
from jeepney.bus_messages import message_bus
from jeepney.io.blocking import open_dbus_connection

from .telephony import call_method, prop

APP_ID = "io.github.kennyporto.Handset"
NOTIFICATIONS = "org.freedesktop.Notifications"
NOTIFICATIONS_PATH = "/org/freedesktop/Notifications"
ACTION_INVOKED = MatchRule(type="signal", interface=NOTIFICATIONS, member="ActionInvoked",
                           path=NOTIFICATIONS_PATH)


class Notifier:
    def __init__(self, conn):
        self.conn = conn

    def _call(self, method, signature=None, *args):
        return call_method(self.conn, NOTIFICATIONS, NOTIFICATIONS_PATH, NOTIFICATIONS,
                           method, signature, *args)

    def incoming_call(self, caller):
        """Show a notification that stays until the call is answered or ends."""
        hints = {
            "urgency": ("y", 2),
            "category": ("s", "call.incoming"),
            "desktop-entry": ("s", APP_ID),
            "resident": ("b", True),
        }
        (notification_id,) = self._call(
            "Notify", "susssasa{sv}i", "Handset", 0, APP_ID, "Incoming call", caller,
            ["answer", "Answer", "decline", "Decline"], hints, 0)
        return notification_id

    def close(self, notification_id):
        self._call("CloseNotification", "u", notification_id)


def request_autostart(enable, timeout=600):
    """Ask the desktop to start Handset hidden at login (XDG Background portal).

    The desktop may show the user a dialog, so this blocks until they answer: run it
    off the UI thread. Returns whether Handset now starts at login.
    """
    conn = open_dbus_connection("SESSION")
    try:
        token = f"handset{secrets.token_hex(4)}"
        sender = conn.unique_name.lstrip(":").replace(".", "_")
        response = MatchRule(type="signal", interface="org.freedesktop.portal.Request",
                             member="Response",
                             path=f"/org/freedesktop/portal/desktop/request/{sender}/{token}")
        conn.send_and_get_reply(message_bus.AddMatch(response))
        options = {
            "handle_token": ("s", token),
            "reason": ("s", "Handset runs in the background to show incoming calls."),
            "autostart": ("b", enable),
            "commandline": ("as", ["handset", "--hidden"]),
        }
        with conn.filter(response) as replies:  # set up first: the answer can come at once
            call_method(conn, "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                        "org.freedesktop.portal.Background", "RequestBackground", "sa{sv}", "",
                        options)
            code, results = conn.recv_until_filtered(replies, timeout=timeout).body
        # 0 is allowed; 1 the user said no; 2 something else went wrong
        return code == 0 and prop(results, "autostart", False)
    finally:
        conn.close()
