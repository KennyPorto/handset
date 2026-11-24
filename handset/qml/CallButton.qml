import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// A round call control with its label underneath, like on a phone.
ColumnLayout {
    id: root

    property alias text: label.text
    property string iconName
    property string iconFallback
    // "positive" (answer, call), "negative" (decline, hang up) or "neutral" (toggles)
    property string role: "neutral"
    property alias checked: button.checked

    signal clicked

    readonly property color fill: {
        if (role === "positive")
            return Kirigami.Theme.positiveTextColor
        if (role === "negative")
            return Kirigami.Theme.negativeTextColor
        return button.checked ? Kirigami.Theme.highlightColor : Kirigami.Theme.alternateBackgroundColor
    }
    readonly property color ink: role !== "neutral" ? "white"
        : button.checked ? Kirigami.Theme.highlightedTextColor : Kirigami.Theme.textColor

    spacing: Kirigami.Units.smallSpacing

    QQC2.AbstractButton {
        id: button

        Layout.alignment: Qt.AlignHCenter
        implicitWidth: Kirigami.Units.gridUnit * 3.5
        implicitHeight: implicitWidth
        opacity: enabled ? 1 : 0.4
        focusPolicy: Qt.StrongFocus

        Accessible.role: Accessible.Button
        Accessible.name: root.text
        Accessible.checkable: root.role === "neutral"
        Accessible.checked: checked

        onClicked: root.clicked()

        background: Rectangle {
            radius: width / 2
            color: button.down ? Qt.darker(root.fill, 1.25)
                 : button.hovered ? Qt.lighter(root.fill, 1.08) : root.fill
            border.width: button.visualFocus ? 2 : 0
            border.color: Kirigami.Theme.focusColor

            Behavior on color {
                ColorAnimation { duration: Kirigami.Units.shortDuration }
            }
        }

        contentItem: Item {
            Kirigami.Icon {
                anchors.centerIn: parent
                width: Kirigami.Units.iconSizes.medium
                height: width
                source: root.iconName
                fallback: root.iconFallback
                isMask: true
                // Hanging up is the call icon tipped over, as on phones.
                rotation: root.role === "negative" ? 135 : 0
                color: root.ink
            }
        }
    }

    QQC2.Label {
        id: label
        Layout.alignment: Qt.AlignHCenter
        font: Kirigami.Theme.smallFont
        opacity: button.enabled ? 0.85 : 0.4
    }
}
