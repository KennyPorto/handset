"""Phone calls over Bluetooth hands-free.

WirePlumber publishes the calls of every phone connected over HFP on the session
bus as ``org.pipewire.Telephony``, using the same interfaces as oFono. BlueZ, on the
system bus, is only needed to connect and disconnect the phone.
"""
from dataclasses import dataclass

from jeepney import DBusAddress, new_method_call
from jeepney.io.blocking import open_dbus_connection
from jeepney.wrappers import DBusErrorResponse, unwrap_msg

SERVICE = "org.pipewire.Telephony"
ROOT = "/org/pipewire/Telephony"
# The phone's side of the hands-free profile. Connecting only this profile keeps
# music and video audio (A2DP) on the phone.
HFP_AG_UUID = "0000111f-0000-1000-8000-00805f9b34fb"

RINGING = ("incoming", "waiting")


def prop(props, key, default=""):
    """Read an a{sv} value; jeepney gives variants as (signature, value)."""
    return props.get(key, (None, default))[1]


@dataclass(frozen=True)
class Call:
    path: str
    number: str
    name: str
    state: str

    @property
    def phone(self):
        return self.path.rsplit("/", 1)[0]

    @property
    def caller(self):
        return self.name or self.number or "Unknown number"

    @property
    def ringing(self):
        return self.state in RINGING


def call_method(conn, service, path, interface, method, signature=None, *args):
    msg = new_method_call(DBusAddress(path, service, interface), method, signature, args)
    return unwrap_msg(conn.send_and_get_reply(msg, timeout=30))


class Telephony:
    """Calls on the phones WirePlumber knows about."""

    def __init__(self, conn=None):
        self.conn = conn or open_dbus_connection("SESSION")

    def _call(self, path, interface, method, signature=None, *args):
        return call_method(self.conn, SERVICE, path, interface, method, signature, *args)

    def state(self):
        """Return (phones, calls). Both are empty when no phone is connected."""
        try:
            (modems,) = self._call(ROOT, "org.ofono.Manager", "GetModems")
            phones = list(modems)
            calls = []
            for phone in phones:
                (found,) = self._call(phone, "org.ofono.VoiceCallManager", "GetCalls")
                calls += [Call(path, prop(p, "LineIdentification"), prop(p, "Name"),
                               prop(p, "State")) for path, p in found.items()]
            return phones, calls
        except DBusErrorResponse:
            # WirePlumber is restarting, or its telephony support is turned off.
            return [], []

    def address(self, phone):
        (value,) = self._call(phone, "org.freedesktop.DBus.Properties", "Get", "ss",
                              "org.pipewire.Telephony.AudioGateway1", "Address")
        return value[1]

    def answer(self, call):
        if call.state == "waiting":  # a second call while already on one
            self._call(call.phone, "org.ofono.VoiceCallManager", "HoldAndAnswer")
        else:
            self._call(call.path, "org.ofono.VoiceCall", "Answer")

    def hang_up(self, call):
        self._call(call.path, "org.ofono.VoiceCall", "Hangup")

    def dial(self, phone, number):
        self._call(phone, "org.ofono.VoiceCallManager", "Dial", "s", number)

    def send_tones(self, phone, tones):
        self._call(phone, "org.ofono.VoiceCallManager", "SendTones", "s", tones)

    # PipeWire exposes microphone volume on AudioGateway1, rather than CallVolume.
    def _mic_volume(self, phone):
        (value,) = self._call(phone, "org.freedesktop.DBus.Properties", "Get", "ss",
                              "org.pipewire.Telephony.AudioGateway1", "MicrophoneVolume")
        return value[1]

    def muted(self, phone):
        return self._mic_volume(phone) == 0

    def set_muted(self, phone, muted):
        volume = self._mic_volume(phone)
        if muted and volume:
            self._unmuted_volume = volume
        elif not muted and not volume:
            volume = getattr(self, "_unmuted_volume", 15)
        self._call(phone, "org.freedesktop.DBus.Properties", "Set", "ssv",
                   "org.pipewire.Telephony.AudioGateway1", "MicrophoneVolume",
                   ("y", 0 if muted else volume))


class Bluetooth:
    """Connects paired phones through BlueZ. Opens a short-lived system bus connection
    per operation, since connecting can take several seconds and runs off the UI thread."""

    @staticmethod
    def _phones(conn):
        (objects,) = call_method(conn, "org.bluez", "/", "org.freedesktop.DBus.ObjectManager",
                                 "GetManagedObjects")
        for path, interfaces in objects.items():
            device = interfaces.get("org.bluez.Device1")
            if device and prop(device, "Paired", False) and HFP_AG_UUID in prop(device, "UUIDs", []):
                yield path, device

    def _profile(self, method, address=None):
        conn = open_dbus_connection("SYSTEM")
        try:
            for path, device in self._phones(conn):
                if address in (None, prop(device, "Address")):
                    call_method(conn, "org.bluez", path, "org.bluez.Device1", method, "s", HFP_AG_UUID)
                    return prop(device, "Alias", "your phone")
            raise LookupError("No paired phone found. Pair your phone in the Bluetooth settings first.")
        finally:
            conn.close()

    def connect(self):
        # shortcut: connects the first paired phone; add a picker if people pair several
        return self._profile("ConnectProfile")

    def disconnect(self, address):
        return self._profile("DisconnectProfile", address)

    def alias(self, address):
        conn = open_dbus_connection("SYSTEM")
        try:
            for _, device in self._phones(conn):
                if prop(device, "Address") == address:
                    return prop(device, "Alias", address)
            return address
        finally:
            conn.close()
