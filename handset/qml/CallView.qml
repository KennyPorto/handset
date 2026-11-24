import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: root

    required property var backend
    required property var call

    property bool keypadOpen: false
    property string tones: ""
    property real now: Date.now()

    readonly property bool ringing: call.ringing ?? false
    readonly property var otherCalls: (backend?.calls ?? []).filter(c => c.path !== call.path)

    function duration(ms) {
        const s = Math.max(0, Math.floor(ms / 1000))
        const pad = n => String(n).padStart(2, "0")
        const h = Math.floor(s / 3600)
        return (h > 0 ? h + ":" + pad(Math.floor(s / 60) % 60) : Math.floor(s / 60)) + ":" + pad(s % 60)
    }

    function stateText(call) {
        switch (call.state) {
        case "incoming": return call.answering ? "Answering…" : "Incoming call"
        case "waiting": return "Call waiting"
        case "dialing": return "Calling…"
        case "alerting": return "Ringing…"
        case "held": return "On hold"
        case "disconnected": return "Call ended"
        case "active": return duration(now - call.activeSince)
        default: return ""
        }
    }

    onCallChanged: if (call.path === undefined) { keypadOpen = false; tones = "" }

    Timer {
        interval: 1000
        repeat: true
        running: root.visible && (root.backend?.calls ?? []).some(c => c.state === "active")
        triggeredOnStart: true
        onTriggered: root.now = Date.now()
    }

    spacing: Kirigami.Units.largeSpacing

    Item { Layout.fillHeight: true }

    Avatar {
        name: root.call.hasName ? root.call.caller : ""
        Layout.alignment: Qt.AlignHCenter
        Layout.preferredWidth: Kirigami.Units.gridUnit * (root.keypadOpen ? 3 : 6)
        Layout.preferredHeight: Layout.preferredWidth
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Kirigami.Units.smallSpacing

        Kirigami.Heading {
            Layout.fillWidth: true
            text: root.call.caller ?? ""
            level: 1
            font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.9
            horizontalAlignment: Text.AlignHCenter
            elide: Text.ElideRight
        }
        QQC2.Label {
            Layout.fillWidth: true
            visible: root.call.hasName ?? false
            text: root.call.number ?? ""
            horizontalAlignment: Text.AlignHCenter
        }
        QQC2.Label {
            Layout.fillWidth: true
            text: root.stateText(root.call)
            font.features: { "tnum": 1 }  // keeps the timer from jittering
            horizontalAlignment: Text.AlignHCenter
            opacity: 0.7
            Accessible.role: Accessible.StaticText
        }
    }

    // A second call, e.g. one on hold or waiting while you're talking.
    Repeater {
        model: root.otherCalls

        delegate: RowLayout {
            required property var modelData
            Layout.fillWidth: true
            Layout.maximumWidth: Kirigami.Units.gridUnit * 16
            Layout.alignment: Qt.AlignHCenter

            QQC2.Label {
                Layout.fillWidth: true
                text: modelData.caller + " · " + root.stateText(modelData)
                elide: Text.ElideRight
            }
            QQC2.ToolButton {
                visible: modelData.ringing
                enabled: !modelData.answering
                text: modelData.answering ? "Answering…" : "Answer"
                onClicked: root.backend.answer(modelData.path)
            }
            QQC2.ToolButton {
                text: "End"
                onClicked: root.backend.hangUp(modelData.path)
            }
        }
    }

    Item { Layout.fillHeight: true }

    QQC2.Label {
        Layout.fillWidth: true
        visible: root.keypadOpen
        text: root.tones || " "
        font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.6
        horizontalAlignment: Text.AlignHCenter
        elide: Text.ElideLeft
    }

    Keypad {
        Layout.alignment: Qt.AlignHCenter
        visible: root.keypadOpen
        onPressed: key => {
            root.tones += key
            root.backend.sendTones(key)
        }
    }

    RowLayout {
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.gridUnit * 2

        CallButton {
            visible: root.ringing
            text: "Decline"
            iconName: "call-start"
            role: "negative"
            onClicked: root.backend.hangUp(root.call.path)
        }
        CallButton {
            visible: root.ringing
            enabled: !root.call.answering
            text: root.call.answering ? "Answering…" : "Answer"
            iconName: "call-start"
            role: "positive"
            onClicked: root.backend.answer(root.call.path)
        }

        CallButton {
            visible: !root.ringing
            text: root.backend?.muted ? "Unmute" : "Mute"
            iconName: "microphone-sensitivity-muted"
            iconFallback: "audio-input-microphone-muted"
            checked: root.backend?.muted ?? false
            onClicked: root.backend.setMuted(!root.backend.muted)
        }
        CallButton {
            visible: !root.ringing
            text: "End"
            iconName: "call-start"
            role: "negative"
            onClicked: root.backend.hangUp(root.call.path)
        }
        CallButton {
            visible: !root.ringing
            text: "Keypad"
            iconName: "input-dialpad"
            iconFallback: "input-keyboard"
            checked: root.keypadOpen
            onClicked: root.keypadOpen = !root.keypadOpen
        }
    }
}
