# Architecture

Handset is a small Python app with a QML interface. It has no daemon of its own: PipeWire
does the Bluetooth hands-free work, and Handset is a front end for it.

```
 phone ──Bluetooth HFP──▶ BlueZ ──▶ PipeWire / WirePlumber ──D-Bus──▶ Handset
                                         │                         org.pipewire.Telephony
                                         └──▶ call audio (your headset)
```

## Code

| File | What it does |
| --- | --- |
| `handset/telephony.py` | D-Bus calls to PipeWire's telephony service (calls, answer, dial, mute) and to BlueZ (connect the hands-free profile only). No Qt here, so it's easy to test. |
| `handset/contacts.py` | Fetching the phone's contacts over PBAP through `obexd`, a small vCard reader, and the saved copy used to put names on calls. Also Qt-free. |
| `handset/desktop.py` | Notifications with Answer/Decline buttons, and the Background portal request for starting at login. |
| `handset/app.py` | The `Backend` object that QML talks to, the D-Bus signal watcher thread, the tray icon and `main()`. |
| `handset/qml/` | The interface: `Main.qml` (window, menu and tabs), `CallView.qml`, `Dialer.qml`, `Contacts.qml`, `Keypad.qml`, `CallButton.qml`, `Avatar.qml`. |
| `data/` | Desktop entry, AppStream metadata and icon. |
| `tests/` | Unit tests for `telephony.py` (using a fake bus) and the vCard reader. |

## How state flows

1. A `Watcher` thread holds its own session bus connection and listens to every signal under
   `/org/pipewire/Telephony` (phones and calls appearing, disappearing or changing state), plus
   `ActionInvoked` from the notification server.
2. Any telephony signal triggers `Backend.refresh()` on the UI thread. It reads the full state
   again (`GetModems`, then `GetCalls` for each phone) instead of applying each signal. There
   are only ever a handful of objects, and it can't drift out of sync.
3. `refresh()` opens a notification for each newly ringing call and closes it once the call
   is answered or ends.
4. QML binds to `Backend` properties (`connected`, `calls`, `muted`…) and calls its slots
   (`answer`, `hangUp`, `dial`…).

Bluetooth connects can take several seconds, so `connectPhone()` runs in a short-lived thread
with its own system bus connection.

## Contacts

When a phone appears, `Backend` starts `contacts.download()` in a thread. It opens a PBAP
session through `org.bluez.obex`, pulls three phonebooks as vCard 3.0: the contacts (`pb`), the
favourites (`fav`, PBAP 1.2, skipped if the phone doesn't have it) and the 200 newest
entries of the call history (`cch`). It asks only for `FN`, `N`, `TEL` and, for the history,
`X-IRMC-CALL-DATETIME`. Each one is written by `obexd` into the app's cache folder. That folder is
the same path inside and outside the sandbox, so the host's `obexd` can write where Handset
can read. The vCard file is parsed and deleted straight away, and the result is saved as
`contacts.json`. The history keeps only the latest call per number, 30 at most.

The sync runs when the phone connects and again when a call ends, so recent calls stay
current.

Calls are matched to contacts on the last nine digits of the number, so `+351 912 345 678`,
`00351912345678` and `912345678` are the same person. PipeWire's own `Name` property wins
when the phone sends one.

Everything here is best-effort. If the phone refuses, or there's no `obexd`, the download
fails quietly (unless the user clicked **Refresh Contacts**), and calls show numbers.

On some systems `obexd` can't read the phone's SDP record (BlueZ 5.87 with kernel 6.18 logs
`setsockopt(L2CAP_OPTIONS): Invalid argument`). Handset then retries on RFCOMM channel 19,
where Android serves PBAP.

## Why these choices

- **jeepney instead of QtDBus.** PySide's QtDBus returns nested D-Bus types such as `a(oa{sv})`
  as opaque `QDBusArgument` objects, which can't be unpacked from Python. jeepney is pure
  Python and decodes them into plain tuples and dicts.
- **PipeWire's oFono compatibility interfaces.** These expose call state and control.
  PipeWire's D-Bus signatures differ from oFono's for some methods. Mute uses the native
  `AudioGateway1.MicrophoneVolume` property and restores the previous volume on unmute.
  This property is not available in upstream PipeWire 1.4; use system mute there.
- **HFP only.** Connecting the whole device would also bring up A2DP, and the PC would take
  over the phone's media audio. `Device1.ConnectProfile` with the HFP Audio Gateway UUID avoids
  that.

## Flatpak permissions

| Permission | Why |
| --- | --- |
| `--talk-name=org.pipewire.Telephony` | Calls |
| `--system-talk-name=org.bluez` | Connecting and disconnecting the phone |
| `--talk-name=org.freedesktop.Notifications` | Notifications with Answer/Decline buttons (the notification portal doesn't support resident, critical notifications yet) |
| `--talk-name=org.kde.StatusNotifierWatcher` | Tray icon |
| `--talk-name=org.bluez.obex` | Fetching contacts from the phone (optional) |
