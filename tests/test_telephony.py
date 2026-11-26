from jeepney.wrappers import DBusErrorResponse

from handset.telephony import Call, Telephony, prop

PHONE = "/org/pipewire/Telephony/ag1"


class FakeTelephony(Telephony):
    """Records D-Bus calls and answers them from a dict instead of a real bus."""

    def __init__(self, replies=None):
        super().__init__(conn=object())
        self.replies = replies or {}
        self.sent = []
        self.signatures = []

    def _call(self, path, interface, method, signature=None, *args):
        self.sent.append((path, method, args))
        self.signatures.append((interface, signature))
        reply = self.replies.get(method)
        if isinstance(reply, Exception):
            raise reply
        return reply


def variant(value):
    return ("s", value)


def test_prop_unwraps_variants_and_falls_back():
    assert prop({"State": ("s", "incoming")}, "State") == "incoming"
    assert prop({}, "Name") == ""
    assert prop({}, "Muted", False) is False


def test_state_lists_calls_of_every_phone():
    calls = {PHONE + "/call1": {"LineIdentification": variant("+351912345678"),
                               "Name": variant(""), "State": variant("incoming")}}
    tel = FakeTelephony({"GetModems": ({PHONE: {}},), "GetCalls": (calls,)})

    phones, found = tel.state()

    assert phones == [PHONE]
    assert found == [Call(PHONE + "/call1", "+351912345678", "", "incoming")]
    assert found[0].ringing and found[0].phone == PHONE


def test_state_is_empty_when_telephony_is_unavailable():
    error = DBusErrorResponse.__new__(DBusErrorResponse)
    tel = FakeTelephony({"GetModems": error})
    assert tel.state() == ([], [])


def test_caller_prefers_name_then_number():
    assert Call("/c", "123", "Ana", "active").caller == "Ana"
    assert Call("/c", "123", "", "active").caller == "123"
    assert Call("/c", "", "", "incoming").caller == "Unknown number"


def test_answering_a_waiting_call_puts_the_current_one_on_hold():
    tel = FakeTelephony()
    tel.answer(Call(PHONE + "/call2", "123", "", "waiting"))
    tel.answer(Call(PHONE + "/call1", "456", "", "incoming"))
    assert tel.sent == [(PHONE, "HoldAndAnswer", ()), (PHONE + "/call1", "Answer", ())]


def test_mute_sets_mic_volume_to_zero_and_unmute_restores_it():
    tel = FakeTelephony({"Get": (("y", 8),)})
    tel.set_muted(PHONE, True)
    assert tel.sent[-1] == (PHONE, "Set", ("org.pipewire.Telephony.AudioGateway1",
                                         "MicrophoneVolume", ("y", 0)))
    assert tel.signatures[-1] == ("org.freedesktop.DBus.Properties", "ssv")
    tel.replies["Get"] = (("y", 0),)
    assert tel.muted(PHONE)
    tel.set_muted(PHONE, False)
    assert tel.sent[-1] == (PHONE, "Set", ("org.pipewire.Telephony.AudioGateway1",
                                         "MicrophoneVolume", ("y", 8)))


def test_dial_uses_pipewire_single_argument():
    tel = FakeTelephony()
    tel.dial(PHONE, "123")
    assert tel.sent == [(PHONE, "Dial", ("123",))]
    assert tel.signatures == [("org.ofono.VoiceCallManager", "s")]
