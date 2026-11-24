import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami

// Initials on a soft circle, or a person icon when there's no name.
// Each name gets its own hue, so faces in a list are easy to tell apart.
Rectangle {
    id: root

    property string name

    readonly property string initials: name.split(/\s+/).filter(w => w.length > 0 && w[0].toUpperCase() !== w[0].toLowerCase())  // words starting with a letter
        .map(w => w[0]).filter((c, i, all) => i === 0 || i === all.length - 1)
        .join("").toUpperCase()
    readonly property real hue: {
        if (initials.length === 0)
            return -1
        let h = 0
        for (let i = 0; i < name.length; i++)
            h = (h * 31 + name.charCodeAt(i)) % 100003
        return (h * 0.618034) % 1  // golden ratio steps spread similar names across the wheel
    }
    readonly property bool dark: Kirigami.ColorUtils.brightnessForColor(Kirigami.Theme.backgroundColor)
        === Kirigami.ColorUtils.Dark
    readonly property color ink: hue < 0 ? Kirigami.Theme.highlightColor
        : Qt.hsla(hue, 0.55, dark ? 0.72 : 0.38, 1)

    implicitWidth: Kirigami.Units.gridUnit * 2
    implicitHeight: implicitWidth
    radius: width / 2
    color: Qt.alpha(ink, dark ? 0.22 : 0.16)
    Accessible.ignored: true

    QQC2.Label {
        anchors.centerIn: parent
        visible: root.initials.length > 0
        text: root.initials
        font.pixelSize: root.height * 0.38
        font.weight: Font.DemiBold
        color: root.ink
    }
    Kirigami.Icon {
        anchors.centerIn: parent
        visible: root.initials.length === 0
        width: root.width * 0.5
        height: width
        source: "user"
        isMask: true
        color: root.ink
    }
}
