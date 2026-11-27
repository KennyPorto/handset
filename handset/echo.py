"""Route a phone's HFP streams through PipeWire's echo canceller.

All pactl calls run off the UI thread. No default devices are changed.
"""
import json
import os
import subprocess
import threading
import uuid


class AudioError(Exception):
    pass


class Audio:
    def command(self, *args):
        # WirePlumber gives Flatpak manager clients permission to route streams.
        # Confine this role to the short-lived audio helper, not the whole app.
        env = os.environ.copy()
        env["PULSE_PROP"] = (env.get("PULSE_PROP", "") + " media.category=Manager").strip()
        try:
            return subprocess.run(["pactl", *map(str, args)], check=True, text=True,
                                  capture_output=True, timeout=3, env=env).stdout.strip()
        except subprocess.CalledProcessError as exc:
            raise AudioError(exc.stderr.strip() or str(exc)) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise AudioError(str(exc)) from exc

    def listing(self, kind):
        try:
            return json.loads(self.command("-f", "json", "list", kind))
        except (ValueError, TypeError) as exc:
            raise AudioError("Couldn't read the audio graph") from exc


def phone_streams(streams, address):
    return [stream for stream in streams
            if stream.get("properties", {}).get("api.bluez5.address", "").upper() == address.upper()
            and stream.get("properties", {}).get("api.bluez5.profile") == "headset-audio-gateway"]


class EchoCancellation:
    """One temporary filter, owned by this instance and never the default device."""

    def __init__(self, audio=None):
        self.audio = audio or Audio()
        self.module = None
        self.address = None
        self.sink = self.source = None
        self.playback = self.capture = None
        self.old_sink = self.old_source = None
        token = uuid.uuid4().hex
        self.sink_name = "handset_echo_output_" + token
        self.source_name = "handset_echo_input_" + token

    @staticmethod
    def _device(devices, index):
        return next((device for device in devices if device["index"] == index), None)

    def start(self, address):
        """Return False while streams are not present; raise on a setup error."""
        playback = phone_streams(self.audio.listing("sink-inputs"), address)
        capture = phone_streams(self.audio.listing("source-outputs"), address)
        if len(playback) != 1 or len(capture) != 1:
            return False
        sink = self._device(self.audio.listing("sinks"), playback[0]["sink"])
        source = self._device(self.audio.listing("sources"), capture[0]["source"])
        if not sink or not source:
            return False
        # Avoid stacking echo cancellers (or making a feedback loop).
        if ("echo-cancel" in sink.get("properties", {}).get("node.group", "") or
                "echo-cancel" in source.get("properties", {}).get("node.group", "")):
            raise AudioError("The call is already using echo-cancelled audio")
        self.playback, self.capture = playback[0]["index"], capture[0]["index"]
        self.old_sink, self.old_source = sink["name"], source["name"]
        try:
            self.module = self.audio.command("load-module", "module-echo-cancel",
                "aec_method=webrtc", "sink_name=" + self.sink_name,
                "source_name=" + self.source_name, "sink_master=" + self.old_sink,
                "source_master=" + self.old_source)
            self.audio.command("move-sink-input", self.playback, self.sink_name)
            self.audio.command("move-source-output", self.capture, self.source_name)
            self.address = address
            return True
        except AudioError:
            self.stop()
            raise

    def stop(self):
        if self.module is None:
            return
        # Only restore streams that still use our filter, so a device selected by the
        # user during the call is not replaced. Streams can disappear on hangup.
        error = None
        try:
            sinks = self.audio.listing("sinks")
            sources = self.audio.listing("sources")
            playback = self.audio.listing("sink-inputs")
            capture = self.audio.listing("source-outputs")
            sink = next((x for x in sinks if x["name"] == self.sink_name), None)
            source = next((x for x in sources if x["name"] == self.source_name), None)
            moves = []
            if sink and any(x["index"] == self.playback and x["sink"] == sink["index"] for x in playback):
                moves.append(("move-sink-input", self.playback, self.old_sink))
            if source and any(x["index"] == self.capture and x["source"] == source["index"] for x in capture):
                moves.append(("move-source-output", self.capture, self.old_source))
            for move in moves:
                try:
                    self.audio.command(*move)
                except AudioError as exc:
                    error = exc
        finally:
            try:
                self.audio.command("unload-module", self.module)
            finally:
                self.module = self.address = None
        if error:
            raise error

    def routing(self):
        """Return active, missing, or changed without overriding a user's device choice."""
        playback = next((x for x in self.audio.listing("sink-inputs")
                         if x["index"] == self.playback), None)
        capture = next((x for x in self.audio.listing("source-outputs")
                        if x["index"] == self.capture), None)
        if not playback or not capture:
            return "missing"
        sink = self._device(self.audio.listing("sinks"), playback["sink"])
        source = self._device(self.audio.listing("sources"), capture["source"])
        if not sink or not source:
            return "missing"
        if sink["name"] != self.sink_name or source["name"] != self.source_name:
            return "changed"
        return "active"


class EchoWorker:
    """Serialize audio operations away from Qt and reconcile call changes."""

    def __init__(self, notify, audio=None):
        self.notify = notify
        self.filter = EchoCancellation(audio)
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.desired = None
        self.closed = False
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def update(self, address):
        with self.lock:
            if address != self.desired:
                self.desired = address
                self.wake.set()

    def close(self):
        with self.lock:
            self.desired = None
            self.closed = True
            self.wake.set()
        self.thread.join(timeout=15)

    def run(self):
        failed = None
        changed = 0
        while True:
            with self.lock:
                desired, closed = self.desired, self.closed
                self.wake.clear()
            try:
                if self.filter.module is not None and self.filter.address != desired:
                    self.filter.stop()
                    changed = 0
                if self.filter.module is not None:
                    routing = self.filter.routing()
                    changed = changed + 1 if routing == "changed" else 0
                    # WirePlumber can report the old route briefly after a move.
                    if routing == "missing" or changed >= 3:
                        self.filter.stop()
                        changed = 0
                        if routing == "changed":
                            failed = desired
                            self.notify("Audio device changed; echo cancellation stopped for this call")
                if desired != failed:
                    failed = None
                if desired and not closed and self.filter.module is None and not failed:
                    self.filter.start(desired)
            except AudioError as exc:
                failed = desired
                self.notify(str(exc))
            if closed:
                return
            self.wake.wait(1)
