# Changelog

All notable changes to Handset are listed here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.1] - 2026-11-26

### Changed

- The FlatPark download is about a quarter of its old size (8 MB instead of 30 MB): it no longer ships FFmpeg and Qt build tools that Handset never uses.
- Release archives are now built and attested by GitHub Actions, so each one can be traced to the tagged source.

## [0.1.0] - 2026-11-24

First release.

### Added

- Answer, decline and end calls from the window or from the notification.
- Dial pad for outgoing calls.
- Caller names, the phone's favourites and recent calls, and a searchable contact list,
  when the phone shares its contacts.
- Mute, keypad tones (DTMF), call waiting and hold.
- Connects the phone for calls only, so media audio stays on the phone.
- Tray icon, and Start at Login through the desktop's background portal.
