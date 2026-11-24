import QtCore
import QtQuick
import QtQuick.Controls as QQC2
import QtQuick.Layouts
import org.kde.kirigami as Kirigami

// Favourites and recent calls first; the full list is one click away. Search covers
// everyone, by name or number. Clicking a person calls them.
ColumnLayout {
    id: root

    required property var backend

    signal dial(string number)

    property bool showAll: false

    // Clicking a section header folds it away; remembered between launches.
    Settings {
        id: folded
        category: "contacts"
        property bool favourites: false
        property bool recent: false
    }

    readonly property var all: backend?.contacts ?? []
    readonly property var favourites: backend?.favourites ?? []
    readonly property var recent: backend?.recent ?? []
    readonly property bool searching: search.text.trim().length > 0
    readonly property bool empty: all.length === 0 && favourites.length === 0 && recent.length === 0
    readonly property var found: {
        const words = fold(search.text).split(/\s+/).filter(w => w.length > 0)
        const digits = search.text.replace(/\D/g, "")
        if (words.length === 0)
            return []
        return all.filter(c => {
            const name = fold(c.name)
            return words.every(w => name.includes(w))
                || (digits.length >= 3 && c.numbers.some(n => n.number.replace(/\D/g, "").includes(digits)))
        })
    }

    // Lower case without accents, so "joao" finds "João".
    function fold(text) {
        return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase()
    }

    function letter(name) {
        const first = fold(name).charAt(0).toUpperCase()
        return /[A-Z]/.test(first) ? first : "#"
    }

    // Recent entries carry one number; contacts can have several.
    function numbersOf(person) {
        return person.numbers ?? [{ number: person.number, label: "" }]
    }

    function call(person, anchor) {
        const numbers = numbersOf(person)
        if (numbers.length === 1) {
            root.dial(numbers[0].number)
        } else {
            numberMenu.numbers = numbers
            numberMenu.popup(anchor)
        }
    }

    // "13:44", "Yesterday", "Friday" or a date, like a phone's call log.
    function when(iso) {
        const date = new Date(iso)
        if (isNaN(date))
            return ""
        const day = d => new Date(d.getFullYear(), d.getMonth(), d.getDate())
        const days = Math.round((day(new Date()) - day(date)) / 86400000)
        if (days === 0)
            return date.toLocaleTimeString(Qt.locale(), Locale.ShortFormat)
        if (days === 1)
            return "Yesterday"
        if (days < 7)
            return date.toLocaleDateString(Qt.locale(), "dddd")
        return date.toLocaleDateString(Qt.locale(), Locale.ShortFormat)
    }

    onVisibleChanged: if (visible && !empty) search.forceActiveFocus()

    spacing: Kirigami.Units.largeSpacing

    Kirigami.SearchField {
        id: search
        Layout.fillWidth: true
        visible: root.all.length > 0
        placeholderText: "Search contacts"
        autoAccept: false  // Enter calls the first match, so never accept while typing
        Keys.onDownPressed: { list.forceActiveFocus(); list.currentIndex = 0 }
        Keys.onEscapePressed: event => {
            if (text.length > 0) clear()
            else if (root.showAll) root.showAll = false
            else event.accepted = false
        }
        onAccepted: if (root.found.length > 0) root.call(root.found[0], search)
    }

    // A way into the full list, and back. Kept outside the list so it never scrolls away.
    QQC2.ItemDelegate {
        Layout.fillWidth: true
        visible: !root.showAll && !root.searching && root.all.length > 0
        Accessible.name: "All contacts, " + root.all.length
        onClicked: root.showAll = true

        contentItem: RowLayout {
            spacing: Kirigami.Units.largeSpacing
            Rectangle {
                implicitWidth: Kirigami.Units.gridUnit * 2
                implicitHeight: implicitWidth
                radius: width / 2
                color: Qt.alpha(Kirigami.Theme.highlightColor, 0.18)
                Kirigami.Icon {
                    anchors.centerIn: parent
                    width: Kirigami.Units.iconSizes.small
                    height: width
                    source: "view-pim-contacts"
                    isMask: true
                    color: Kirigami.Theme.highlightColor
                }
            }
            QQC2.Label {
                Layout.fillWidth: true
                text: "All contacts"
            }
            QQC2.Label {
                text: root.all.length
                opacity: 0.6
            }
            Kirigami.Icon {
                implicitWidth: Kirigami.Units.iconSizes.small
                implicitHeight: implicitWidth
                source: "go-next"
                opacity: 0.6
            }
        }
    }

    // In the full list: the way back.
    QQC2.ItemDelegate {
        Layout.fillWidth: true
        visible: root.showAll && !root.searching
        icon.name: "go-previous"
        text: "Favourites and recent"
        onClicked: root.showAll = false
    }

    QQC2.ScrollView {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: !root.empty && !(root.searching && root.found.length === 0)

        ListView {
            id: list
            model: root.searching ? root.found : root.showAll ? root.all : folded.recent ? [] : root.recent
            clip: true
            reuseItems: true
            keyNavigationEnabled: true
            onModelChanged: positionViewAtBeginning()
            Keys.onUpPressed: event => {
                if (currentIndex === 0) search.forceActiveFocus()
                else event.accepted = false
            }

            header: ColumnLayout {
                width: ListView.view.width
                visible: !root.searching
                height: visible ? implicitHeight : 0
                // ListView keeps its scroll position when the header grows (favourites
                // arriving, or coming back from the full list), which hides the header.
                onHeightChanged: list.positionViewAtBeginning()
                spacing: 0

                Kirigami.ListSectionHeader {
                    Layout.fillWidth: true
                    visible: !root.showAll && root.favourites.length > 0
                    text: "Favourites"
                    Accessible.role: Accessible.Button
                    Accessible.description: folded.favourites ? "Expand" : "Collapse"
                    onClicked: folded.favourites = !folded.favourites
                    Kirigami.Icon {
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: implicitWidth
                        source: folded.favourites ? "arrow-down" : "arrow-up"
                        opacity: 0.6
                    }
                }

                GridLayout {
                    id: grid
                    readonly property real tile: Kirigami.Units.gridUnit * 4.5
                    Layout.fillWidth: true
                    Layout.topMargin: Kirigami.Units.smallSpacing
                    Layout.bottomMargin: Kirigami.Units.largeSpacing
                    visible: !root.showAll && !folded.favourites && root.favourites.length > 0
                    columns: Math.max(1, Math.floor(width / tile))
                    rowSpacing: Kirigami.Units.largeSpacing
                    columnSpacing: 0

                    Repeater {
                        model: root.favourites

                        delegate: QQC2.AbstractButton {
                            id: tile
                            required property var modelData
                            Layout.fillWidth: true
                            implicitHeight: content.implicitHeight + Kirigami.Units.smallSpacing * 2
                            Accessible.name: "Call " + modelData.name
                            onClicked: root.call(modelData, tile)

                            background: Rectangle {
                                radius: Kirigami.Units.cornerRadius * 2
                                color: tile.down ? Kirigami.Theme.alternateBackgroundColor
                                     : tile.hovered ? Qt.alpha(Kirigami.Theme.alternateBackgroundColor, 0.6)
                                     : "transparent"
                                border.width: tile.visualFocus ? 2 : 0
                                border.color: Kirigami.Theme.focusColor
                            }

                            contentItem: ColumnLayout {
                                id: content
                                spacing: Kirigami.Units.smallSpacing
                                Avatar {
                                    name: tile.modelData.name
                                    Layout.alignment: Qt.AlignHCenter
                                    Layout.preferredWidth: Kirigami.Units.gridUnit * 3
                                    Layout.preferredHeight: Layout.preferredWidth
                                }
                                QQC2.Label {
                                    Layout.fillWidth: true
                                    Layout.maximumWidth: grid.tile
                                    Layout.alignment: Qt.AlignHCenter
                                    text: tile.modelData.name.split(/\s+/)[0]
                                    font: Kirigami.Theme.smallFont
                                    horizontalAlignment: Text.AlignHCenter
                                    elide: Text.ElideRight
                                }
                            }
                        }
                    }
                }

                Kirigami.ListSectionHeader {
                    Layout.fillWidth: true
                    visible: !root.showAll && root.recent.length > 0
                    text: "Recent"
                    Accessible.role: Accessible.Button
                    Accessible.description: folded.recent ? "Expand" : "Collapse"
                    onClicked: folded.recent = !folded.recent
                    Kirigami.Icon {
                        implicitWidth: Kirigami.Units.iconSizes.small
                        implicitHeight: implicitWidth
                        source: folded.recent ? "arrow-down" : "arrow-up"
                        opacity: 0.6
                    }
                }
            }

            delegate: ColumnLayout {
                id: row

                required property var modelData
                required property int index
                readonly property var numbers: root.numbersOf(modelData)
                readonly property bool isCall: modelData.when !== undefined
                readonly property bool missed: modelData.kind === "missed"
                readonly property bool firstOfLetter: index === 0
                    || root.letter(root.all[index - 1]?.name ?? "") !== root.letter(modelData.name)

                width: ListView.view.width
                spacing: 0

                Kirigami.ListSectionHeader {
                    Layout.fillWidth: true
                    visible: root.showAll && !root.searching && row.firstOfLetter
                    text: root.letter(row.modelData.name)
                }

                QQC2.ItemDelegate {
                    id: item
                    Layout.fillWidth: true
                    highlighted: row.ListView.isCurrentItem && list.activeFocus
                    Accessible.name: (row.modelData.name || row.numbers[0].number) + ", " + subtitle.text
                    Accessible.description: "Call"
                    onClicked: root.call(row.modelData, button)
                    Keys.onReturnPressed: root.call(row.modelData, button)

                    contentItem: RowLayout {
                        spacing: Kirigami.Units.largeSpacing

                        Avatar {
                            name: row.modelData.name
                        }

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0

                            QQC2.Label {
                                Layout.fillWidth: true
                                text: row.modelData.name || row.numbers[0].number
                                color: row.missed ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                                elide: Text.ElideRight
                            }
                            RowLayout {
                                spacing: Kirigami.Units.smallSpacing
                                Kirigami.Icon {
                                    visible: row.isCall
                                    implicitWidth: Kirigami.Units.iconSizes.small * 0.8
                                    implicitHeight: implicitWidth
                                    source: row.missed ? "call-missed"
                                          : row.modelData.kind === "dialed" ? "call-outgoing" : "call-incoming"
                                    isMask: true
                                    color: row.missed ? Kirigami.Theme.negativeTextColor : Kirigami.Theme.textColor
                                    opacity: row.missed ? 1 : 0.7
                                }
                                QQC2.Label {
                                    id: subtitle
                                    Layout.fillWidth: true
                                    text: row.isCall
                                        ? (row.modelData.name ? row.numbers[0].number + " · " : "") + root.when(row.modelData.when)
                                        : row.numbers[0].label + " · " + row.numbers[0].number
                                          + (row.numbers.length > 1 ? "  +" + (row.numbers.length - 1) : "")
                                    font: Kirigami.Theme.smallFont
                                    opacity: 0.7
                                    elide: Text.ElideRight
                                }
                            }
                        }

                        QQC2.ToolButton {
                            id: button
                            icon.name: "call-start"
                            icon.color: Kirigami.Theme.positiveTextColor
                            display: QQC2.AbstractButton.IconOnly
                            text: "Call " + (row.modelData.name || row.numbers[0].number)
                            focusPolicy: Qt.NoFocus
                            opacity: item.hovered || item.highlighted ? 1 : 0.55
                            onClicked: root.call(row.modelData, button)
                        }
                    }
                }
            }
        }
    }

    // Asks which number to call, for people with more than one.
    QQC2.Menu {
        id: numberMenu
        property var numbers: []
        Repeater {
            model: numberMenu.numbers
            QQC2.MenuItem {
                required property var modelData
                text: modelData.label + "\t" + modelData.number
                icon.name: "call-start"
                onTriggered: root.dial(modelData.number)
            }
        }
    }

    Kirigami.PlaceholderMessage {
        Layout.fillWidth: true
        Layout.fillHeight: true
        visible: root.empty || (root.searching && root.found.length === 0)
        icon.name: root.searching ? "edit-find" : "view-pim-contacts"
        text: root.searching ? "No contacts found"
            : !(root.backend?.useContacts ?? true) ? "Contacts are off"
            : root.backend?.syncingContacts ? "Getting your contacts…" : "No contacts yet"
        explanation: root.searching || root.backend?.syncingContacts ? ""
            : !(root.backend?.useContacts ?? true) ? "Handset shows numbers only, and keeps no contacts on this PC."
            : "To call people by name, allow contact sharing for this PC in your phone's Bluetooth settings. Calls work without it."
        helpfulAction: Kirigami.Action {
            text: "Get Contacts"
            icon.name: "view-refresh"
            visible: root.empty && !(root.backend?.syncingContacts ?? true)
            onTriggered: root.backend.setUseContacts(true)  // also turns contacts back on
        }

        QQC2.BusyIndicator {
            Layout.alignment: Qt.AlignHCenter
            visible: root.empty && (root.backend?.syncingContacts ?? false)
            running: visible
        }
    }
}
