"""The phone's contacts, for caller names and calling from a list.

Contacts come from the phone over Bluetooth's phonebook profile (PBAP), through the
desktop's ``obexd`` on the session bus. They're optional: if the phone doesn't share
them, every lookup just finds nothing and Handset shows numbers.
"""
import json
import re
import time
from pathlib import Path

from jeepney.io.blocking import open_dbus_connection
from jeepney.wrappers import DBusErrorResponse

from .telephony import call_method

OBEX = "org.bluez.obex"
OBEX_ROOT = "/org/bluez/obex"
# shortcut: Android serves PBAP on RFCOMM channel 19. Used only when BlueZ can't find
# the phone's service record (seen with BlueZ 5.87 on kernel 6.18, where obexd's SDP
# lookup fails); drop it once that's fixed upstream.
ANDROID_PBAP_CHANNEL = 19

# Labels for the standard vCard TEL types. Phones also send their own words, which
# are shown as they are.
LABELS = {"CELL": "Mobile", "HOME": "Home", "WORK": "Work", "MAIN": "Main", "PAGER": "Pager",
          "FAX": "Fax", "VOICE": "Phone", "OTHER": "Other"}


def match_key(number):
    """The last 9 digits, so "+351 912 345 678" and "912345678" are the same number."""
    return re.sub(r"\D", "", number)[-9:]


def _unescape(value):
    return re.sub(r"\\(.)", lambda m: "\n" if m.group(1) in "nN" else m.group(1), value)


def _label(params):
    types = [t for p in params for t in p.removeprefix("TYPE=").split(",")]
    for t in types:
        if t.upper() in LABELS and t.upper() != "VOICE":
            return LABELS[t.upper()]
    # Call history marks numbers with a bare "0", which means nothing to people.
    custom = [t.removeprefix("X-") for t in types
              if t.upper() not in LABELS and t.upper() != "PREF" and not t.isdigit()]
    return custom[0] if custom else "Phone"


def _cards(text):
    """Yield each vCard as ``{"name", "numbers", "kind", "when"}``. Reads FN, N, TEL and
    the call history's X-IRMC-CALL-DATETIME."""
    card = None
    for line in re.sub(r"\r?\n[ \t]", "", text).splitlines():  # unfold long lines
        key, _, value = line.partition(":")
        name, *params = key.split(";")
        name = name.upper()
        if name == "BEGIN":
            card = {"fn": "", "n": "", "numbers": [], "kind": "", "when": ""}
        elif card is None:
            continue
        elif name == "FN":
            card["fn"] = _unescape(value).strip()
        elif name == "N":
            parts = [_unescape(p).strip() for p in value.split(";")]
            # N is family;given;additional;prefix;suffix
            card["n"] = " ".join(p for p in (parts[3:4] + parts[1:3] + parts[:1] + parts[4:5]) if p)
        elif name == "TEL" and value.strip():
            number = value.strip()
            if all(n["number"] != number for n in card["numbers"]):
                card["numbers"].append({"number": number, "label": _label(params)})
        elif name == "X-IRMC-CALL-DATETIME":
            # TYPE=DIALED, RECEIVED or MISSED; the time is 20261123T134455, maybe with a Z
            card["kind"] = next((p.removeprefix("TYPE=").lower() for p in params), "")
            m = re.fullmatch(r"(\d{4})(\d\d)(\d\d)T(\d\d)(\d\d)(\d\d)(Z?)", value.strip())
            card["when"] = "{}-{}-{}T{}:{}:{}{}".format(*m.groups()) if m else ""
        elif name == "END":
            yield {"name": card["fn"] or card["n"], "numbers": card["numbers"],
                   "kind": card["kind"], "when": card["when"]}
            card = None


def parse_vcards(text):
    """Turn vCard 3.0 text into ``[{"name", "numbers": [{"number", "label"}]}]``, sorted by name.

    Contacts without a name or a phone number are left out.
    """
    contacts = [{"name": c["name"], "numbers": c["numbers"]}
                for c in _cards(text) if c["name"] and c["numbers"]]
    return sorted(contacts, key=lambda c: c["name"].casefold())


def parse_history(text, limit=30):
    """The most recent call with each number, newest first:
    ``[{"name", "number", "kind", "when"}]``. ``name`` is empty for unknown numbers."""
    calls = sorted((c for c in _cards(text) if c["numbers"] and c["when"]),
                   key=lambda c: c["when"], reverse=True)
    recent, seen = [], set()
    for c in calls:
        number = c["numbers"][0]["number"]
        if match_key(number) not in seen:
            seen.add(match_key(number))
            recent.append({"name": c["name"], "number": number, "kind": c["kind"], "when": c["when"]})
    return recent[:limit]


class Contacts:
    """The phone's contacts, favourites and recent calls, kept in a file so names work
    before the phone has synced."""

    def __init__(self, cache_dir):
        self.file = Path(cache_dir) / "contacts.json"
        self._set({})
        try:
            data = json.loads(self.file.read_text(encoding="utf-8"))
            self._set(data if isinstance(data, dict) else {})
        except (OSError, ValueError):
            pass

    def _set(self, data):
        self.items = data.get("contacts", [])
        self.favourites = data.get("favourites", [])
        self._names = {}
        for contact in self.items + self.favourites:
            for n in contact["numbers"]:
                self._names.setdefault(match_key(n["number"]), contact["name"])
        self.recent = [dict(r, name=r["name"] or self.name_for(r["number"]))
                       for r in data.get("recent", [])]

    def name_for(self, number):
        key = match_key(number)
        return self._names.get(key, "") if len(key) >= 6 else ""  # short codes are ambiguous

    def replace(self, data):
        self._set(data)
        self.file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.file.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self.file)

    def clear(self):
        self._set({})
        self.file.unlink(missing_ok=True)


# What to pull from the phone: folder, the fields to ask for, how many entries (0: all),
# and whether the phone may lack the folder. "fav" is new in PBAP 1.2.
FOLDERS = {
    "contacts": ("pb", ["FN", "N", "TEL"], 0, False),
    "favourites": ("fav", ["FN", "N", "TEL"], 0, True),
    "recent": ("cch", ["FN", "N", "TEL", "X-IRMC-CALL-DATETIME"], 200, True),
}


def download(address, cache_dir, timeout=120):
    """Pull the phone's contacts, favourites and recent calls over PBAP.

    Returns ``{"contacts", "favourites", "recent"}``. Raises DBusErrorResponse or
    TimeoutError when the phone doesn't share contacts. Blocks, so run it off the UI
    thread. The phone may ask the user for permission the first time.
    """
    conn = open_dbus_connection("SESSION")
    # obexd runs outside the sandbox, so it writes into the app's cache folder,
    # which both sides can see.
    target = Path(cache_dir) / "phonebook.vcf"
    target.parent.mkdir(parents=True, exist_ok=True)

    def obex(path, interface, method, signature=None, *args):
        full = interface if interface.startswith("org.") else f"{OBEX}.{interface}"
        return call_method(conn, OBEX, path, full, method, signature, *args)

    def pull(session, folder, fields, count):
        obex(session, "PhonebookAccess1", "Select", "ss", "int", folder)
        options = {"Format": ("s", "vcard30"), "Fields": ("as", fields)}
        if count:
            options["MaxCount"] = ("q", count)  # history comes newest first
        transfer, _ = obex(session, "PhonebookAccess1", "PullAll", "sa{sv}", str(target), options)
        _wait(obex, transfer, timeout)
        try:
            return target.read_text(encoding="utf-8", errors="replace")
        finally:
            target.unlink(missing_ok=True)

    try:
        try:
            (session,) = obex(OBEX_ROOT, "Client1", "CreateSession", "sa{sv}", address,
                              {"Target": ("s", "pbap")})
        except DBusErrorResponse:
            (session,) = obex(OBEX_ROOT, "Client1", "CreateSession", "sa{sv}", address,
                              {"Target": ("s", "pbap"), "Channel": ("y", ANDROID_PBAP_CHANNEL)})
        try:
            result = {}
            for key, (folder, fields, count, optional) in FOLDERS.items():
                try:
                    text = pull(session, folder, fields, count)
                except (DBusErrorResponse, TimeoutError, OSError):
                    if not optional:
                        raise
                    text = ""
                result[key] = parse_history(text) if key == "recent" else parse_vcards(text)
            return result
        finally:
            obex(OBEX_ROOT, "Client1", "RemoveSession", "o", session)
    finally:
        target.unlink(missing_ok=True)
        conn.close()


def _wait(obex, transfer, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            (status,) = obex(transfer, "org.freedesktop.DBus.Properties", "Get", "ss",
                             f"{OBEX}.Transfer1", "Status")
        except DBusErrorResponse as e:
            if e.name == "org.freedesktop.DBus.Error.UnknownObject":
                return  # obexd drops the transfer as soon as it completes
            raise
        if status[1] == "complete":
            return
        if status[1] == "error":
            raise TimeoutError("The phone stopped sending contacts")
        time.sleep(0.3)
    raise TimeoutError("The phone took too long to send contacts")
