import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

ColumnLayout {
    id: root

    signal dial(string number)

    function call() {
        if (number.text.trim().length > 0) {
            root.dial(number.text)
            number.clear()
        }
    }

    // The dialer starts hidden while the phone connects, so `focus: true` alone never
    // reaches the field; take focus whenever it appears.
    onVisibleChanged: if (visible) number.forceActiveFocus()
    Component.onCompleted: if (visible) number.forceActiveFocus()

    spacing: Kirigami.Units.largeSpacing

    Item { Layout.fillHeight: true }

    RowLayout {
        Layout.fillWidth: true
        Layout.maximumWidth: Kirigami.Units.gridUnit * 16
        Layout.alignment: Qt.AlignHCenter

        // Balances the erase button so the number stays centred.
        Item { implicitWidth: erase.implicitWidth }

        QQC2.TextField {
            id: number
            Layout.fillWidth: true
            horizontalAlignment: TextInput.AlignHCenter
            font.pointSize: Kirigami.Theme.defaultFont.pointSize * 1.8
            placeholderText: "Enter a number"
            inputMethodHints: Qt.ImhDialableCharactersOnly
            validator: RegularExpressionValidator { regularExpression: /[0-9+*#() -]*/ }
            background: null
            focus: true
            Accessible.name: "Phone number"
            onAccepted: root.call()
        }

        QQC2.ToolButton {
            id: erase
            icon.name: "edit-clear"
            display: QQC2.AbstractButton.IconOnly
            text: "Erase"
            enabled: number.length > 0
            opacity: enabled ? 1 : 0
            onClicked: number.remove(number.cursorPosition - 1, number.cursorPosition)
            onPressAndHold: number.clear()
            QQC2.ToolTip.text: "Erase (hold to clear)"
            QQC2.ToolTip.visible: hovered
            QQC2.ToolTip.delay: Kirigami.Units.toolTipDelay
        }
    }

    Kirigami.Separator {
        Layout.fillWidth: true
        Layout.maximumWidth: Kirigami.Units.gridUnit * 16
        Layout.alignment: Qt.AlignHCenter
    }

    Keypad {
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: Kirigami.Units.largeSpacing
        onPressed: key => {
            number.insert(number.cursorPosition, key)
            number.forceActiveFocus()
        }
    }

    CallButton {
        Layout.alignment: Qt.AlignHCenter
        Layout.topMargin: Kirigami.Units.largeSpacing
        text: "Call"
        iconName: "call-start"
        role: "positive"
        enabled: number.text.trim().length > 0
        onClicked: root.call()
    }

    Item { Layout.fillHeight: true }
}
