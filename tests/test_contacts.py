from handset.contacts import Contacts, match_key, parse_history, parse_vcards

VCARDS = """BEGIN:VCARD\r
VERSION:3.0\r
FN:\r
N:;;;;\r
TEL:\r
END:VCARD\r
BEGIN:VCARD\r
VERSION:3.0\r
FN:Zé Ninguém\r
N:Ninguém;Zé;;;\r
TEL;TYPE=CELL:+351 912 345 678\r
TEL;TYPE=X-Telemóvel:912345678\r
TEL;TYPE=WORK,VOICE:+351 21 000 0000\r
END:VCARD\r
BEGIN:VCARD\r
VERSION:3.0\r
N:Silva;Ana;;Dr.;\r
TEL;TYPE=HOME:21 111 22 33\r
END:VCARD\r
BEGIN:VCARD\r
VERSION:3.0\r
FN:No Number\r
END:VCARD\r
BEGIN:VCARD\r
VERSION:3.0\r
FN:Long\\, Folded\r
  Name\r
TEL:123456789\r
END:VCARD\r
"""

HISTORY = """BEGIN:VCARD
VERSION:3.0
FN:
N:
TEL;TYPE=0:+351912345678
X-IRMC-CALL-DATETIME;TYPE=RECEIVED:20261120T090000
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN;CHARSET=UTF-8:
TEL;TYPE=0:912345678
X-IRMC-CALL-DATETIME;TYPE=MISSED:20261123T134455
END:VCARD
BEGIN:VCARD
VERSION:3.0
FN;CHARSET=UTF-8:Ana Silva
TEL;TYPE=Outro:21 111 22 33
X-IRMC-CALL-DATETIME;TYPE=DIALED:20261122T180000Z
END:VCARD
"""


def test_history_keeps_the_latest_call_per_number():
    assert parse_history(HISTORY) == [
        {"name": "", "number": "912345678", "kind": "missed", "when": "2026-11-23T13:44:55"},
        {"name": "Ana Silva", "number": "21 111 22 33", "kind": "dialed", "when": "2026-11-22T18:00:00Z"},
    ]


def test_parse_reads_names_numbers_and_labels():
    contacts = parse_vcards(VCARDS)
    assert [c["name"] for c in contacts] == ["Dr. Ana Silva", "Long, Folded Name", "Zé Ninguém"]
    assert contacts[0]["numbers"] == [{"number": "21 111 22 33", "label": "Home"}]
    assert contacts[1]["numbers"] == [{"number": "123456789", "label": "Phone"}]
    assert contacts[2]["numbers"] == [
        {"number": "+351 912 345 678", "label": "Mobile"},
        {"number": "912345678", "label": "Telemóvel"},
        {"number": "+351 21 000 0000", "label": "Work"},
    ]


def test_numbers_match_with_or_without_country_code():
    assert match_key("+351 912 345 678") == match_key("912345678") == "912345678"


def test_lookup_and_cache_survive_a_restart(tmp_path):
    contacts = Contacts(tmp_path)
    assert contacts.name_for("912345678") == ""
    contacts.replace({"contacts": parse_vcards(VCARDS), "favourites": [],
                      "recent": parse_history(HISTORY)})

    again = Contacts(tmp_path)
    assert again.name_for("00351912345678") == "Zé Ninguém"
    assert again.name_for("112") == ""  # short codes never match a contact
    assert again.recent[0] == {"name": "Zé Ninguém", "number": "912345678",
                               "kind": "missed", "when": "2026-11-23T13:44:55"}
    assert (tmp_path / "contacts.json").stat().st_mode & 0o777 == 0o600

    again.clear()
    assert Contacts(tmp_path).items == []
