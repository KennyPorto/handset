import pytest

from handset.echo import AudioError, EchoCancellation

ADDRESS = "12:34:56:78:90:AB"


class FakeAudio:
    def __init__(self):
        self.calls = []
        self.fail = None
        properties = {"api.bluez5.address": ADDRESS, "api.bluez5.profile": "headset-audio-gateway"}
        self.data = {
            "sinks": [{"index": 10, "name": "speakers"}],
            "sources": [{"index": 11, "name": "right-channel"}],
            "sink-inputs": [{"index": 20, "sink": 10, "properties": properties},
                            {"index": 21, "sink": 10, "properties": {"media.role": "phone"}}],
            "source-outputs": [{"index": 30, "source": 11, "properties": properties}],
        }

    def listing(self, kind):
        return self.data[kind]

    def command(self, *args):
        self.calls.append(args)
        if args[0] == self.fail:
            self.fail = None
            raise AudioError("failed")
        if args[0] == "load-module":
            options = dict(arg.split("=", 1) for arg in args[2:])
            self.data["sinks"].append({"index": 40, "name": options["sink_name"]})
            self.data["sources"].append({"index": 41, "name": options["source_name"]})
            return "9"
        if args[0] == "move-sink-input":
            stream = next(s for s in self.data["sink-inputs"] if s["index"] == args[1])
            stream["sink"] = next(s["index"] for s in self.data["sinks"] if s["name"] == args[2])
        if args[0] == "move-source-output":
            stream = next(s for s in self.data["source-outputs"] if s["index"] == args[1])
            stream["source"] = next(s["index"] for s in self.data["sources"] if s["name"] == args[2])
        return ""


def test_routes_only_the_matching_phone_and_restores_it():
    audio = FakeAudio()
    echo = EchoCancellation(audio)
    assert echo.start(ADDRESS.lower())
    assert audio.data["sink-inputs"][0]["sink"] == 40
    assert audio.data["sink-inputs"][1]["sink"] == 10
    assert audio.data["source-outputs"][0]["source"] == 41
    assert echo.routing() == "active"
    echo.stop()
    assert audio.data["sink-inputs"][0]["sink"] == 10
    assert audio.data["source-outputs"][0]["source"] == 11
    assert audio.calls[-1] == ("unload-module", "9")
    assert not any("default" in str(call) for call in audio.calls)


def test_waits_for_both_call_streams():
    audio = FakeAudio()
    audio.data["source-outputs"].clear()
    assert not EchoCancellation(audio).start(ADDRESS)
    assert audio.calls == []


def test_rolls_back_if_second_stream_cannot_move():
    audio = FakeAudio()
    audio.fail = "move-source-output"
    echo = EchoCancellation(audio)
    with pytest.raises(AudioError):
        echo.start(ADDRESS)
    assert audio.data["sink-inputs"][0]["sink"] == 10
    assert audio.calls[-1] == ("unload-module", "9")


def test_device_changed_by_user_is_not_overwritten():
    audio = FakeAudio()
    echo = EchoCancellation(audio)
    echo.start(ADDRESS)
    audio.data["sinks"].append({"index": 50, "name": "headphones"})
    audio.data["sink-inputs"][0]["sink"] = 50
    assert echo.routing() == "changed"
    echo.stop()
    assert audio.data["sink-inputs"][0]["sink"] == 50
    assert audio.data["source-outputs"][0]["source"] == 11


def test_existing_echo_filter_is_not_stacked():
    audio = FakeAudio()
    audio.data["sources"][0]["properties"] = {"node.group": "echo-cancel-123"}
    with pytest.raises(AudioError, match="already using"):
        EchoCancellation(audio).start(ADDRESS)
    assert audio.calls == []


def test_audio_helper_requests_manager_role_without_losing_existing_properties(monkeypatch):
    from types import SimpleNamespace
    from handset.echo import Audio

    monkeypatch.setenv("PULSE_PROP", "application.name=Handset")
    observed = {}

    def run(args, **options):
        observed.update(options)
        return SimpleNamespace(stdout="ok\n")

    monkeypatch.setattr("handset.echo.subprocess.run", run)
    assert Audio().command("info") == "ok"
    assert observed["env"]["PULSE_PROP"] == (
        "application.name=Handset media.category=Manager")


def test_worker_ignores_temporary_route_change_and_stops_for_a_persistent_one():
    import threading
    from handset.echo import EchoWorker

    class Filter:
        module = "9"
        address = ADDRESS
        routes = iter(["changed", "active", "changed", "changed", "changed"])
        stopped = 0

        def routing(self):
            return next(self.routes)

        def stop(self):
            self.stopped += 1
            self.module = None

    class Wake:
        def clear(self):
            pass

        def wait(self, timeout):
            if worker.filter.stopped:
                worker.closed = True

    worker = EchoWorker.__new__(EchoWorker)
    worker.lock = threading.Lock()
    worker.wake = Wake()
    worker.desired = ADDRESS
    worker.closed = False
    worker.filter = Filter()
    errors = []
    worker.notify = errors.append
    worker.run()
    assert worker.filter.stopped == 1
    assert len(errors) == 1 and "device changed" in errors[0]
