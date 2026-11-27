import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

Kirigami.ApplicationWindow {
    id: root

    required property var backend

    // The call shown full-size: a ringing one takes priority over the one in progress.
    readonly property var currentCall: {
        const calls = backend.calls
        return calls.find(c => c.ringing) ?? calls[0] ?? null
    }
    property string view: "keypad"   // or "contacts", when there's no call
    readonly property bool idle: backend.connected && currentCall === null

    title: currentCall ? currentCall.caller : "Handset"
    width: Kirigami.Units.gridUnit * 21
    height: Kirigami.Units.gridUnit * 34
    minimumWidth: Kirigami.Units.gridUnit * 17
    minimumHeight: Kirigami.Units.gridUnit * 28
    visible: false

    // Keep running in the background so incoming calls still pop up.
    onClosing: close => {
        close.accepted = false
        root.hide()
    }

    Connections {
        target: root.backend
        function onMessage(text) {
            root.showPassiveNotification(text)
        }
    }

    pageStack.initialPage: Kirigami.Page {
        title: root.backend.connected ? root.backend.phoneName : "Handset"
        padding: Kirigami.Units.largeSpacing * 2

        actions: [
            Kirigami.Action {
                text: "Echo Cancellation"
                icon.name: "audio-input-microphone"
                checkable: true
                checked: root.backend.echoCancellation
                displayHint: Kirigami.DisplayHint.AlwaysHide
                onTriggered: root.backend.setEchoCancellation(checked)
            },
            Kirigami.Action {
                text: "Start at Login"
                icon.name: "system-run"
                checkable: true
                checked: root.backend.autostart
                displayHint: Kirigami.DisplayHint.AlwaysHide
                onTriggered: {
                    root.backend.setAutostart(checked)
                    // Clicking unbinds `checked`; follow the backend, which waits for the desktop's answer.
                    checked = Qt.binding(() => root.backend.autostart)
                }
            },
            Kirigami.Action {
                text: "Refresh Contacts"
                icon.name: "view-refresh"
                visible: root.backend.connected && root.backend.useContacts
                enabled: !root.backend.syncingContacts
                displayHint: Kirigami.DisplayHint.AlwaysHide
                onTriggered: root.backend.syncContacts(true)
            },
            Kirigami.Action {
                text: "Use Phone Contacts"
                icon.name: "view-pim-contacts"
                checkable: true
                checked: root.backend.useContacts
                displayHint: Kirigami.DisplayHint.AlwaysHide
                onTriggered: root.backend.setUseContacts(checked)
            },
            Kirigami.Action {
                text: "Disconnect Phone"
                icon.name: "network-disconnect"
                visible: root.backend.connected
                displayHint: Kirigami.DisplayHint.AlwaysHide
                onTriggered: root.backend.disconnectPhone()
            },
            Kirigami.Action {
                text: "About Handset"
                icon.name: "help-about"
                displayHint: Kirigami.DisplayHint.AlwaysHide
                onTriggered: aboutDialog.open()
            },
            Kirigami.Action {
                text: "Quit"
                icon.name: "application-exit"
                shortcut: StandardKey.Quit
                displayHint: Kirigami.DisplayHint.AlwaysHide
                onTriggered: Qt.quit()
            }
        ]

        Kirigami.PlaceholderMessage {
            anchors.centerIn: parent
            width: parent.width - Kirigami.Units.gridUnit * 2
            visible: !root.backend.connected
            icon.name: "smartphone"
            text: root.backend.connecting ? "Connecting to your phone…" : "No phone connected"
            explanation: root.backend.connecting
                ? ""
                : "Pair your phone in the Bluetooth settings, then connect it here. Handset only uses it for calls, so music and videos keep playing on the phone."
            helpfulAction: Kirigami.Action {
                text: "Connect Phone"
                icon.name: "network-bluetooth"
                enabled: !root.backend.connecting
                onTriggered: root.backend.connectPhone()
            }

            QQC2.BusyIndicator {
                Layout.alignment: Qt.AlignHCenter
                visible: root.backend.connecting
                running: visible
            }
        }

        CallView {
            anchors.fill: parent
            visible: root.backend.connected && root.currentCall !== null
            backend: root.backend
            call: root.currentCall ?? ({})
        }

        Dialer {
            anchors.fill: parent
            visible: root.idle && root.view === "keypad"
            onDial: number => root.backend.dial(number)
        }

        Contacts {
            anchors.fill: parent
            visible: root.idle && root.view === "contacts"
            backend: root.backend
            onDial: number => root.backend.dial(number)
        }

        footer: Kirigami.NavigationTabBar {
            visible: root.idle
            actions: [
                Kirigami.Action {
                    text: "Keypad"
                    icon.name: "input-dialpad"
                    checked: root.view === "keypad"
                    onTriggered: root.view = "keypad"
                },
                Kirigami.Action {
                    text: "Contacts"
                    icon.name: "view-pim-contacts"
                    checked: root.view === "contacts"
                    shortcut: StandardKey.Find
                    onTriggered: root.view = "contacts"
                }
            ]
        }
    }

    Kirigami.Dialog {
        id: aboutDialog
        title: "About Handset"
        padding: Kirigami.Units.largeSpacing * 2
        standardButtons: Kirigami.Dialog.Close

        ColumnLayout {
            spacing: Kirigami.Units.smallSpacing

            Kirigami.Icon {
                source: "io.github.kennyporto.Handset"
                Layout.preferredWidth: Kirigami.Units.iconSizes.huge
                Layout.preferredHeight: Kirigami.Units.iconSizes.huge
                Layout.alignment: Qt.AlignHCenter
            }
            Kirigami.Heading {
                text: "Handset " + root.backend.version
                Layout.alignment: Qt.AlignHCenter
            }
            QQC2.Label {
                text: "Answer your phone calls on your PC."
                Layout.alignment: Qt.AlignHCenter
            }
            QQC2.Label {
                text: "© 2026 KennyPorto · MIT License"
                opacity: 0.7
                Layout.alignment: Qt.AlignHCenter
            }
            Kirigami.UrlButton {
                url: "https://github.com/KennyPorto/handset"
                text: "Website"
                Layout.alignment: Qt.AlignHCenter
            }
        }
    }
}
