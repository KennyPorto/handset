import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// 3×4 phone keypad. Holding 0 types "+".
GridLayout {
    id: root

    signal pressed(string key)

    columns: 3
    rowSpacing: Kirigami.Units.smallSpacing
    columnSpacing: Kirigami.Units.largeSpacing

    Repeater {
        model: [
            ["1", ""], ["2", "ABC"], ["3", "DEF"],
            ["4", "GHI"], ["5", "JKL"], ["6", "MNO"],
            ["7", "PQRS"], ["8", "TUV"], ["9", "WXYZ"],
            ["*", ""], ["0", "+"], ["#", ""]
        ]

        delegate: QQC2.AbstractButton {
            id: key

            required property var modelData
            readonly property string digit: modelData[0]

            Layout.alignment: Qt.AlignHCenter
            implicitWidth: Kirigami.Units.gridUnit * 3.5
            implicitHeight: Kirigami.Units.gridUnit * 3.4
            focusPolicy: Qt.TabFocus
            Accessible.name: digit === "0" ? "0, hold for plus" : digit

            onClicked: root.pressed(digit)
            onPressAndHold: if (digit === "0") root.pressed("+")

            background: Rectangle {
                radius: Kirigami.Units.cornerRadius * 2
                color: key.down ? Kirigami.Theme.alternateBackgroundColor
                     : key.hovered ? Qt.alpha(Kirigami.Theme.alternateBackgroundColor, 0.6) : "transparent"
                border.width: key.visualFocus ? 2 : 0
                border.color: Kirigami.Theme.focusColor
            }

            contentItem: ColumnLayout {
                spacing: 0

                QQC2.Label {
                    text: key.digit
                    font.pointSize: Kirigami.Theme.defaultFont.pointSize * 2.1
                    Layout.alignment: Qt.AlignHCenter
                }
                QQC2.Label {
                    // Keep the row height even when a key has no letters.
                    text: key.modelData[1] || " "
                    font: Kirigami.Theme.smallFont
                    opacity: 0.6
                    Layout.alignment: Qt.AlignHCenter
                }
            }
        }
    }
}
