#!/usr/bin/env python3
"""setupMSIFedora.py - Personal Fedora/KDE restore script for the MSI laptop.

Recreates, on a fresh Fedora install:
  * Repos: RPM Fusion (free + nonfree), MSI-EC COPRs, Darkly COPR,
    GitHub CLI and Mullvad VPN repos
  * The user-installed RPMs (chosen apps/tools/theme, NOT the OS defaults)
  * Every user-installed Flatpak app (runtimes are pulled automatically)
  * KDE Plasma configs, global themes and the eye-care widget from a
    sanitized payload embedded in this file (no absolute paths, no
    personal data - home is templated and substituted on install)
  * The personal scripts from ./scripts -> ~/.local/bin

Usage:
  ./setupMSIFedora.py                     # run everything (asks to confirm)
  ./setupMSIFedora.py --yes               # run everything, no prompt
  ./setupMSIFedora.py --dry-run           # print what would happen
  ./setupMSIFedora.py --only kde,scripts  # run selected steps only
  ./setupMSIFedora.py --export DIR        # dump the sanitized payload
                                          # (for reviewing/refreshing it)

Steps: repos, packages, flatpaks, kde, scripts, services
"""

import argparse
import base64
import gzip
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

# --------------------------------------------------------------------------
# Repos
# --------------------------------------------------------------------------
REPOS = [
    {
        "id": "rpmfusion-free",
        "name": "RPM Fusion Free",
        "kind": "rpmfusion",
        "pkg": "rpmfusion-free-release",
        "url": "https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-{ver}.noarch.rpm",
    },
    {
        "id": "rpmfusion-nonfree",
        "name": "RPM Fusion Nonfree",
        "kind": "rpmfusion",
        "pkg": "rpmfusion-nonfree-release",
        "url": "https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-{ver}.noarch.rpm",
    },
    {
        "id": "copr:copr.fedorainfracloud.org:xabi08:MSI-EC",
        "name": "COPR xabi08/MSI-EC (msi-ec akmod)",
        "kind": "copr",
        "spec": "xabi08/MSI-EC",
    },
    {
        "id": "copr:copr.fedorainfracloud.org:teackot:msi",
        "name": "COPR teackot/msi (acpi_ec akmod, mcontrolcenter)",
        "kind": "copr",
        "spec": "teackot/msi",
    },
    {
        "id": "copr:copr.fedorainfracloud.org:deltacopy:darkly",
        "name": "COPR deltacopy/darkly (Darkly theme)",
        "kind": "copr",
        "spec": "deltacopy/darkly",
    },
    {
        "id": "gh-cli",
        "name": "GitHub CLI repo",
        "kind": "ghcli",
    },
    {
        "id": "mullvad-stable",
        "name": "Mullvad VPN repo",
        "kind": "repofile",
        "url": "https://repository.mullvad.net/rpm/stable/mullvad.repo",
    },
]

# --------------------------------------------------------------------------
# RPM packages - only what the user actually chose (from dnf history),
# plus what the ~/.local/bin scripts need to run.
# --------------------------------------------------------------------------
RPM_PACKAGES = {
    "Script dependencies": [
        "ffmpeg",
        "python3-rich",
        "python3-pikepdf",
        "qpdf",
        "poppler-utils",
        "ghostscript",
        "yt-dlp",
        "mpv",
    ],
    "CLI tools": [
        "git",
        "git-lfs",
        "gh",
        "ripgrep",
        "micro",
        "fastfetch",
        "tree",
        "powertop",
        "unoconv",
    ],
    "Document & media": [
        "mupdf",
        "pdfgrep",
        "tesseract",
        "ocrmypdf",
        "libheif-freeworld",
        "libheif-tools",
        "clamav",
        "clamav-freshclam",
    ],
    "Python helpers": [
        "python3-openpyxl",
        "python3-reportlab",
        "python3-PyMuPDF",
    ],
    "KDE apps & theming": [
        "kate",
        "darkly",
        "darkly-qt6",
        "papirus-icon-theme",
        "mcontrolcenter",
    ],
    "Hardware (MSI laptop)": [
        "akmod-nvidia",
        "xorg-x11-drv-nvidia",
        "akmod-acpi_ec",
        "acpi_ec-kmod-common",
        "akmod-msi-ec",
        "msi-ec-kmod-common",
    ],
}

SERVICES = [
    "mullvad-daemon",
    "clamav-freshclam",
]

# --------------------------------------------------------------------------
# Flatpak apps (apps only; runtimes come as dependencies)
# --------------------------------------------------------------------------
FLATPAKS = [
    ("ai.lmstudio.lm-studio", "flathub"),
    ("ca.edestcroix.Recordbox", "flathub"),
    ("com.github.hugolabe.Wike", "fedora"),
    ("com.github.tchx84.Flatseal", "flathub"),
    ("com.github.wwmm.easyeffects", "flathub"),
    ("com.mattjakeman.ExtensionManager", "flathub"),
    ("com.maxint.maxint", "flathub"),
    ("com.obsproject.Studio", "flathub"),
    ("com.rtosta.zapzap", "flathub"),
    ("com.super_productivity.SuperProductivity", "flathub"),
    ("com.usebottles.bottles", "flathub"),
    ("com.warlordsoftwares.youtube-downloader-4ktube", "flathub"),
    ("dev.andy128k.Hearts", "flathub"),
    ("fm.reaper.Reaper", "flathub"),
    ("fr.free.Homebank", "flathub"),
    ("io.dbeaver.DBeaverCommunity", "flathub"),
    ("io.github.diegopvlk.Tomatillo", "flathub"),
    ("io.github.flattool.Ignition", "flathub"),
    ("io.github.flattool.Warehouse", "flathub"),
    ("io.github.ilya_zlobintsev.LACT", "flathub"),
    ("io.github.jeffshee.Hidamari", "flathub"),
    ("io.github.kolunmi.Bazaar", "flathub"),
    ("io.github.linx_systems.ClamUI", "flathub"),
    ("io.github.thetumultuousunicornofdarkness.cpu-x", "flathub"),
    ("io.github.whelanh.scidCommunity", "flathub"),
    ("io.github.wiiznokes.fan-control", "flathub"),
    ("io.gitlab.librewolf-community", "flathub"),
    ("io.gitlab.theevilskeleton.Upscaler", "flathub"),
    ("io.missioncenter.MissionCenter", "flathub"),
    ("md.obsidian.Obsidian", "flathub"),
    ("net.sourceforge.scidvspc.scidvspc", "flathub"),
    ("org.chessmd.chessmd", "flathub"),
    ("org.fooyin.fooyin", "flathub"),
    ("org.freedesktop.Piper", "flathub"),
    ("org.gimp.GIMP", "flathub"),
    ("org.gnome.DejaDup", "flathub"),
    ("org.gnome.Maps", "flathub"),
    ("org.gnome.Rhythmbox3", "flathub"),
    ("org.gnome.gitlab.wwarner.Solitaire", "flathub"),
    ("org.inkscape.Inkscape", "flathub"),
    ("org.kde.haruna", "flathub"),
    ("org.kde.kdenlive", "flathub"),
    ("org.kde.krita", "flathub"),
    ("org.keepassxc.KeePassXC", "fedora"),
    ("org.localsend.localsend_app", "flathub"),
    ("org.nickvision.tagger", "flathub"),
    ("org.onlyoffice.desktopeditors", "flathub"),
    ("org.qbittorrent.qBittorrent", "fedora"),
    ("org.torproject.torbrowser-launcher", "flathub"),
    ("page.codeberg.grinka.Transition", "flathub"),
    ("re.fossplant.songrec", "flathub"),
]

# ==== EMBEDDED KDE PAYLOAD (sanitized; generated by --export) ====
KDE_FILES = {'.config/arkrc': '[General]\n'
                  'LockSidebar=true\n'
                  'ShowSidebar=true\n'
                  '\n'
                  '[MainWindow]\n'
                  'StatusBar=Disabled\n',
 '.config/baloofilerc': '[Basic Settings]\nIndexing-Enabled=false\n\n[General]\ndbVersion=2\n',
 '.config/dolphinrc': '[General]\n'
                      'Version=202\n'
                      'ViewPropsTimestamp=2026,9,1,22,32,41.14\n'
                      '\n'
                      '[KFileDialog Settings]\n'
                      'Places Icons Auto-resize=false\n'
                      'Places Icons Static Size=22\n'
                      '\n'
                      '[MainWindow]\n'
                      'MenuBar=Disabled\n',
 '.config/katerc': '[General]\n'
                   'Days Meta Infos=30\n'
                   'PinnedDocuments=\n'
                   'Save Meta Infos=true\n'
                   'Show Full Path in Title=false\n'
                   'Show Menu Bar=true\n'
                   'Show Status Bar=true\n'
                   'Show Tab Bar=true\n'
                   'Show Url Nav Bar=true\n'
                   '\n'
                   '[filetree]\n'
                   'editShade=36,87,114\n'
                   'listMode=false\n'
                   'middleClickToClose=false\n'
                   'shadingEnabled=true\n'
                   'showCloseButton=false\n'
                   'showFullPathOnRoots=false\n'
                   'showToolbar=true\n'
                   'sortRole=0\n'
                   'viewShade=67,67,105\n',
 '.config/kded5rc': '[Module-device_automounter]\nautoload=false\n',
 '.config/kdedefaults/kcminputrc': '[Mouse]\ncursorTheme=breeze_cursors\n',
 '.config/kdedefaults/kdeglobals': '[General]\n'
                                   'ColorScheme=Darkly\n'
                                   '\n'
                                   '[Icons]\n'
                                   'Theme=Papirus\n'
                                   '\n'
                                   '[KDE]\n'
                                   'widgetStyle=Darkly\n',
 '.config/kdedefaults/ksplashrc': '[KSplash]\nEngine=KSplashQML\nTheme=Darkly\n',
 '.config/kdedefaults/kwinrc': '[TabBox]\n'
                               'LayoutName=org.kde.breeze.desktop\n'
                               '\n'
                               '[org.kde.kdecoration2]\n'
                               'NoPlugin=false\n'
                               'library=org.kde.darkly\n'
                               'theme=Darkly\n',
 '.config/kdedefaults/package': 'Darkly',
 '.config/kdedefaults/plasmarc': '[Theme]\nname=darkly\n',
 '.config/kdeglobals': '[ColorEffects:Disabled]\n'
                       'ChangeSelectionColor=\n'
                       'Color=36,36,36\n'
                       'ColorAmount=0.5\n'
                       'ColorEffect=3\n'
                       'ContrastAmount=0.5\n'
                       'ContrastEffect=0\n'
                       'Enable=\n'
                       'IntensityAmount=0\n'
                       'IntensityEffect=0\n'
                       '\n'
                       '[ColorEffects:Inactive]\n'
                       'ChangeSelectionColor=true\n'
                       'Color=51,51,51\n'
                       'ColorAmount=0.4\n'
                       'ColorEffect=3\n'
                       'ContrastAmount=0.4\n'
                       'ContrastEffect=0\n'
                       'Enable=true\n'
                       'IntensityAmount=-0.2\n'
                       'IntensityEffect=0\n'
                       '\n'
                       '[Colors:Button]\n'
                       'BackgroundAlternate=77,77,77\n'
                       'BackgroundNormal=50,50,50\n'
                       'DecorationFocus=52,120,218\n'
                       'DecorationHover=0,161,236\n'
                       'ForegroundActive=61,174,233\n'
                       'ForegroundInactive=199,199,199\n'
                       'ForegroundLink=0,100,255\n'
                       'ForegroundNegative=218,68,83\n'
                       'ForegroundNeutral=246,116,0\n'
                       'ForegroundNormal=241,241,241\n'
                       'ForegroundPositive=36,173,89\n'
                       'ForegroundVisited=115,115,158\n'
                       '\n'
                       '[Colors:Complementary]\n'
                       'BackgroundAlternate=59,64,69\n'
                       'BackgroundNormal=49,54,59\n'
                       'DecorationFocus=30,146,255\n'
                       'DecorationHover=61,174,230\n'
                       'ForegroundActive=246,116,0\n'
                       'ForegroundInactive=175,176,179\n'
                       'ForegroundLink=61,174,230\n'
                       'ForegroundNegative=237,21,21\n'
                       'ForegroundNeutral=201,206,59\n'
                       'ForegroundNormal=239,240,241\n'
                       'ForegroundPositive=17,209,22\n'
                       'ForegroundVisited=61,174,230\n'
                       '\n'
                       '[Colors:Selection]\n'
                       'BackgroundAlternate=29,153,243\n'
                       'BackgroundNormal=27,145,213\n'
                       'DecorationFocus=52,120,218\n'
                       'DecorationHover=0,161,236\n'
                       'ForegroundActive=252,252,252\n'
                       'ForegroundInactive=241,241,241\n'
                       'ForegroundLink=0,100,255\n'
                       'ForegroundNegative=218,68,83\n'
                       'ForegroundNeutral=246,116,0\n'
                       'ForegroundNormal=241,241,241\n'
                       'ForegroundPositive=36,173,89\n'
                       'ForegroundVisited=115,115,158\n'
                       '\n'
                       '[Colors:Tooltip]\n'
                       'BackgroundAlternate=77,77,77\n'
                       'BackgroundNormal=59,59,59\n'
                       'DecorationFocus=52,120,218\n'
                       'DecorationHover=0,161,236\n'
                       'ForegroundActive=61,174,233\n'
                       'ForegroundInactive=199,199,199\n'
                       'ForegroundLink=0,100,255\n'
                       'ForegroundNegative=218,68,83\n'
                       'ForegroundNeutral=246,116,0\n'
                       'ForegroundNormal=239,240,241\n'
                       'ForegroundPositive=36,173,89\n'
                       'ForegroundVisited=115,115,158\n'
                       '\n'
                       '[Colors:View]\n'
                       'BackgroundAlternate=54,54,54\n'
                       'BackgroundNormal=44,44,44\n'
                       'DecorationFocus=52,120,218\n'
                       'DecorationHover=0,161,236\n'
                       'ForegroundActive=61,174,233\n'
                       'ForegroundInactive=199,199,199\n'
                       'ForegroundLink=0,100,255\n'
                       'ForegroundNegative=218,68,83\n'
                       'ForegroundNeutral=246,116,0\n'
                       'ForegroundNormal=241,241,241\n'
                       'ForegroundPositive=36,173,89\n'
                       'ForegroundVisited=115,115,158\n'
                       '\n'
                       '[Colors:Window]\n'
                       'BackgroundAlternate=77,77,77\n'
                       'BackgroundNormal=34,34,34\n'
                       'DecorationFocus=52,120,218\n'
                       'DecorationHover=0,161,236\n'
                       'ForegroundActive=61,174,233\n'
                       'ForegroundInactive=199,199,199\n'
                       'ForegroundLink=0,100,255\n'
                       'ForegroundNegative=218,68,83\n'
                       'ForegroundNeutral=246,116,0\n'
                       'ForegroundNormal=239,240,241\n'
                       'ForegroundPositive=36,173,89\n'
                       'ForegroundVisited=115,115,158\n'
                       '\n'
                       '[General]\n'
                       'ColorSchemeHash=6f1a610db41ddac6068e241961601df443dc1a4d\n'
                       'UseSystemBell=false\n'
                       '\n'
                       '[KDE]\n'
                       'LookAndFeelPackage=Darkly\n'
                       'contrast=0\n'
                       'frameContrast=0.2\n'
                       '\n'
                       '[KFileDialog Settings]\n'
                       'Allow Expansion=false\n'
                       'Automatically select filename extension=true\n'
                       'Breadcrumb Navigation=false\n'
                       'Decoration position=2\n'
                       'Show Full Path=false\n'
                       'Show Inline Previews=true\n'
                       'Show Preview=false\n'
                       'Show Speedbar=true\n'
                       'Show hidden files=false\n'
                       'Sort by=Name\n'
                       'Sort directories first=true\n'
                       'Sort hidden files last=false\n'
                       'Sort reversed=false\n'
                       'Speedbar Width=140\n'
                       'View Style=DetailTree\n'
                       '\n'
                       '[WM]\n'
                       'activeBackground=34,34,34\n'
                       'activeBlend=255,255,255\n'
                       'activeForeground=204,204,204\n'
                       'inactiveBackground=44,44,44\n'
                       'inactiveBlend=44,44,44\n'
                       'inactiveForeground=144,144,144\n',
 '.config/kiorc': '[Confirmations]\nConfirmDelete=true\n',
 '.config/konsolerc': '[Desktop Entry]\n'
                      'DefaultProfile=Profile 1.profile\n'
                      '\n'
                      '[General]\n'
                      'ConfigVersion=1\n'
                      '\n'
                      '[Notification Messages]\n'
                      'CloseAllTabs=true\n'
                      '\n'
                      '[UiSettings]\n'
                      'ColorScheme=\n',
 '.config/kwinrc': '[Desktops]\n'
                   '\n'
                   'Number=2\n'
                   'Rows=1\n'
                   '\n'
                   '[Plugins]\n'
                   'zoomEnabled=false\n'
                   '\n'
                   '[Xwayland]\n'
                   'Scale=1\n',
 '.config/okularrc': '[Desktop Entry]\n'
                     'FullScreen=false\n'
                     '\n'
                     '[General]\n'
                     'LockSidebar=true\n'
                     'ShowSidebar=true\n'
                     '\n',
 '.config/plasma-localerc': '[Formats]\n'
                            'LANG=en_US.UTF-8\n'
                            'LC_ADDRESS=en_GB.UTF-8\n'
                            'LC_MEASUREMENT=en_GB.UTF-8\n'
                            'LC_MONETARY=en_GB.UTF-8\n'
                            'LC_NAME=en_GB.UTF-8\n'
                            'LC_PAPER=en_GB.UTF-8\n'
                            'LC_TELEPHONE=en_GB.UTF-8\n'
                            'LC_TIME=en_GB.UTF-8\n',
 '.config/plasma-org.kde.plasma.desktop-appletsrc': '[ActionPlugins][0]\n'
                                                    'RightButton;NoModifier=org.kde.contextmenu\n'
                                                    '\n'
                                                    '[ActionPlugins][1]\n'
                                                    'RightButton;NoModifier=org.kde.contextmenu\n'
                                                    '\n'
                                                    '[Containments][2]\n'
                                                    'activityId=\n'
                                                    'formfactor=2\n'
                                                    'immutability=1\n'
                                                    'lastScreen=0\n'
                                                    'location=4\n'
                                                    'plugin=org.kde.panel\n'
                                                    'wallpaperplugin=org.kde.image\n'
                                                    '\n'
                                                    '[Containments][2][Applets][22]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.digitalclock\n'
                                                    '\n'
                                                    '[Containments][2][Applets][22][Configuration]\n'
                                                    'popupHeight=451\n'
                                                    'popupWidth=810\n'
                                                    '\n'
                                                    '[Containments][2][Applets][22][Configuration][Appearance]\n'
                                                    'customDateFormat=ddd dd\\s\n'
                                                    'dateFormat=longDate\n'
                                                    'enabledCalendarPlugins=holidaysevents,pimevents\n'
                                                    'fontWeight=400\n'
                                                    'use24hFormat=2\n'
                                                    '\n'
                                                    '[Containments][2][Applets][22][Configuration][ConfigDialog]\n'
                                                    'DialogHeight=630\n'
                                                    'DialogWidth=810\n'
                                                    '\n'
                                                    '[Containments][2][Applets][23]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.showdesktop\n'
                                                    '\n'
                                                    '[Containments][2][Applets][3]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.kickoff\n'
                                                    '\n'
                                                    '[Containments][2][Applets][3][Configuration]\n'
                                                    'popupHeight=509\n'
                                                    'popupWidth=649\n'
                                                    '\n'
                                                    '[Containments][2][Applets][3][Configuration][General]\n'
                                                    'favoritesPortedToKAstats=true\n'
                                                    'icon=start-here\n'
                                                    '\n'
                                                    '[Containments][2][Applets][4]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.pager\n'
                                                    '\n'
                                                    '[Containments][2][Applets][5]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.icontasks\n'
                                                    '\n'
                                                    '[Containments][2][Applets][5][Configuration][General]\n'
                                                    'groupingAppIdBlacklist=io.gitlab.librewolf-community.desktop,com.abdownloadmanager.desktop\n'
                                                    'groupingLauncherUrlBlacklist=applications:io.gitlab.librewolf-community.desktop,applications:com.abdownloadmanager.desktop\n'
                                                    'launchers=applications:org.kde.discover.desktop,applications:systemsettings.desktop,preferred://filemanager,preferred://browser,file:///var/lib/flatpak/exports/share/applications/md.obsidian.Obsidian.desktop,file:///var/lib/flatpak/exports/share/applications/com.super_productivity.SuperProductivity.desktop,applications:org.kde.kcalc.desktop,applications:org.kde.konsole.desktop,applications:mullvad-vpn.desktop,file:///var/lib/flatpak/exports/share/applications/org.keepassxc.KeePassXC.desktop,applications:org.kde.kfind.desktop,file:///var/lib/flatpak/exports/share/applications/io.missioncenter.MissionCenter.desktop,file:///var/lib/flatpak/exports/share/applications/org.qbittorrent.qBittorrent.desktop,file:///var/lib/flatpak/exports/share/applications/io.github.diegopvlk.Tomatillo.desktop\n'
                                                    '\n'
                                                    '[Containments][2][Applets][6]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.marginsseparator\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7]\n'
                                                    'activityId=\n'
                                                    'formfactor=0\n'
                                                    'immutability=1\n'
                                                    'lastScreen=-1\n'
                                                    'location=0\n'
                                                    'plugin=org.kde.plasma.systemtray\n'
                                                    'popupHeight=432\n'
                                                    'popupWidth=432\n'
                                                    'wallpaperplugin=org.kde.image\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][10]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.networkmanagement\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][11]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.cameraindicator\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][12]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.clipboard\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][13]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.devicenotifier\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][14]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.manage-inputmethod\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][15]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.notifications\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][16]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.keyboardlayout\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][17]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.printmanager\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][18]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.keyboardindicator\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][19]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.weather\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][19][Configuration][ConfigDialog]\n'
                                                    'DialogHeight=630\n'
                                                    'DialogWidth=810\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][19][Configuration][Units]\n'
                                                    'pressureUnit=5029\n'
                                                    'temperatureUnit=6001\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][20]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.kscreen\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][21]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.volume\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][21][Configuration][General]\n'
                                                    'migrated=true\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][24]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.bluetooth\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][25]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.battery\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][25][Configuration][General]\n'
                                                    'showPercentage=true\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][26]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.brightness\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][28]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.mediacontroller\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][8]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.kdeconnect\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][Applets][9]\n'
                                                    'immutability=1\n'
                                                    'plugin=org.kde.plasma.vault\n'
                                                    '\n'
                                                    '[Containments][2][Applets][7][General]\n'
                                                    'extraItems=org.kde.kdeconnect,org.kde.plasma.vault,org.kde.plasma.battery,org.kde.plasma.brightness,org.kde.plasma.networkmanagement,org.kde.plasma.cameraindicator,org.kde.plasma.clipboard,org.kde.plasma.devicenotifier,org.kde.plasma.manage-inputmethod,org.kde.plasma.mediacontroller,org.kde.plasma.notifications,org.kde.plasma.keyboardlayout,org.kde.plasma.printmanager,org.kde.plasma.keyboardindicator,org.kde.plasma.weather,org.kde.kscreen,org.kde.plasma.bluetooth,org.kde.plasma.volume\n'
                                                    'knownItems=org.kde.kdeconnect,org.kde.plasma.vault,org.kde.plasma.battery,org.kde.plasma.brightness,org.kde.plasma.networkmanagement,org.kde.plasma.cameraindicator,org.kde.plasma.clipboard,org.kde.plasma.devicenotifier,org.kde.plasma.manage-inputmethod,org.kde.plasma.mediacontroller,org.kde.plasma.notifications,org.kde.plasma.keyboardlayout,org.kde.plasma.printmanager,org.kde.plasma.keyboardindicator,org.kde.plasma.weather,org.kde.kscreen,org.kde.plasma.bluetooth,org.kde.plasma.volume\n'
                                                    '\n'
                                                    '[Containments][2][General]\n'
                                                    'AppletOrder=3;5;4;6;7;22;23\n'
                                                    '\n'
                                                    '[ScreenMapping]\n'
                                                    '\n'
                                                    '\n',
 '.config/plasmashellrc': '[PIMEventsPlugin]\n'
                          'calendars=17\n'
                          '\n'
                          '[PlasmaViews][Panel 2]\n'
                          'floating=1\n'
                          'shell=org.kde.plasma.desktop\n'
                          '\n'
                          '[PlasmaViews][Panel 2][Defaults]\n'
                          'thickness=34\n'
                          '\n',
 '.config/spectaclerc': '[Annotations]\n'
                        'annotationToolType=6\n'
                        'arrowStrokeWidth=9\n'
                        '\n'
                        '[ImageSave]\n'
                        '\n'
                        'translatedScreenshotsFolder=Screenshots\n'
                        '\n'
                        '[VideoSave]\n'
                        'translatedScreencastsFolder=Screencasts\n',
 '.local/share/konsole/Breeze.colorscheme': '[Background]\n'
                                            'Color=35,38,39\n'
                                            '\n'
                                            '[BackgroundFaint]\n'
                                            'Color=49,54,59\n'
                                            '\n'
                                            '[BackgroundIntense]\n'
                                            'Color=0,0,0\n'
                                            '\n'
                                            '[Color0]\n'
                                            'Color=35,38,39\n'
                                            '\n'
                                            '[Color0Faint]\n'
                                            'Color=49,54,59\n'
                                            '\n'
                                            '[Color0Intense]\n'
                                            'Color=127,140,141\n'
                                            '\n'
                                            '[Color1]\n'
                                            'Color=237,21,21\n'
                                            '\n'
                                            '[Color1Faint]\n'
                                            'Color=120,50,40\n'
                                            '\n'
                                            '[Color1Intense]\n'
                                            'Color=192,57,43\n'
                                            '\n'
                                            '[Color2]\n'
                                            'Color=17,209,22\n'
                                            '\n'
                                            '[Color2Faint]\n'
                                            'Color=23,162,98\n'
                                            '\n'
                                            '[Color2Intense]\n'
                                            'Color=28,220,154\n'
                                            '\n'
                                            '[Color3]\n'
                                            'Color=246,116,0\n'
                                            '\n'
                                            '[Color3Faint]\n'
                                            'Color=182,86,25\n'
                                            '\n'
                                            '[Color3Intense]\n'
                                            'Color=253,188,75\n'
                                            '\n'
                                            '[Color4]\n'
                                            'Color=29,153,243\n'
                                            '\n'
                                            '[Color4Faint]\n'
                                            'Color=27,102,143\n'
                                            '\n'
                                            '[Color4Intense]\n'
                                            'Color=61,174,233\n'
                                            '\n'
                                            '[Color5]\n'
                                            'Color=155,89,182\n'
                                            '\n'
                                            '[Color5Faint]\n'
                                            'Color=97,74,115\n'
                                            '\n'
                                            '[Color5Intense]\n'
                                            'Color=142,68,173\n'
                                            '\n'
                                            '[Color6]\n'
                                            'Color=26,188,156\n'
                                            '\n'
                                            '[Color6Faint]\n'
                                            'Color=24,108,96\n'
                                            '\n'
                                            '[Color6Intense]\n'
                                            'Color=22,160,133\n'
                                            '\n'
                                            '[Color7]\n'
                                            'Color=252,252,252\n'
                                            '\n'
                                            '[Color7Faint]\n'
                                            'Color=99,104,109\n'
                                            '\n'
                                            '[Color7Intense]\n'
                                            'Color=255,255,255\n'
                                            '\n'
                                            '[Foreground]\n'
                                            'Color=252,252,252\n'
                                            '\n'
                                            '[ForegroundFaint]\n'
                                            'Color=239,240,241\n'
                                            '\n'
                                            '[ForegroundIntense]\n'
                                            'Color=61,174,233\n'
                                            '\n'
                                            '[General]\n'
                                            'Anchor=0.5,0.5\n'
                                            'Blur=true\n'
                                            'ColorRandomization=false\n'
                                            'Description=Breeze\n'
                                            'FillStyle=Tile\n'
                                            'Opacity=0.59\n'
                                            'Wallpaper=\n'
                                            'WallpaperFlipType=NoFlip\n'
                                            'WallpaperOpacity=1\n',
 '.local/share/konsole/Profile 1.profile': '[Appearance]\n'
                                           'ColorScheme=Breeze\n'
                                           '\n'
                                           '[General]\n'
                                           'Name=Profile 1\n'
                                           'Parent=FALLBACK/\n'
                                           'TerminalColumns=110\n'
                                           '\n'
                                           '[Scrolling]\n'
                                           'HistoryMode=2\n',
 '.local/share/konsole/bookmarks.xml': '<?xml version="1.0" encoding="UTF-8"?>\n'
                                       '<!DOCTYPE xbel>\n'
                                       '<xbel '
                                       'xmlns:bookmark="http://www.freedesktop.org/standards/desktop-bookmarks" '
                                       'xmlns:kdepriv="http://www.kde.org/kdepriv" '
                                       'xmlns:mime="http://www.freedesktop.org/standards/shared-mime-info">\n'
                                       ' <bookmark '
                                       'href="file://__HOME__/Documents/Project/Deobf">\n'
                                       '  <title>Deobf</title>\n'
                                       '  <info>\n'
                                       '   <metadata owner="http://freedesktop.org">\n'
                                       '    <bookmark:icon name=""/>\n'
                                       '   </metadata>\n'
                                       '  </info>\n'
                                       ' </bookmark>\n'
                                       '</xbel>\n'}

KDE_ASSETS_B64 = (
    "H4sIAPIbvGoC/+y7BZwVx7YvXO3eDQS3kMF9cHd3h+AMzAwZBmZgBA0SXIIF12AJ7pAAgeAeXIJbcN3t3v0VkHPukXffle/d+3tC"
    "b4a9d++u1auWV/V/lSpdqnTt1jFDG8fFxMalgP+SI/rj8a+9R0eXK/8vn9+fLxNdtkxZkG8o+G840lPTYlLg7cH/m0fZyvkGpCUM"
    "iKtRplLlKtHlK0ZXqlyqXNnoSuUqV2TBp+P/+qNU/+Q+Mf1Lp34VkxJXemD/mNQBMaX7JycnloxJii0ZHxfXv3T9mJTE/sNK90lO"
    "SotLSkstHRsXH5PePy31P+b/FT/6e5lKFf7u/cNRoVJFUKZC2QrRFcpWLA8/Q++vVKEMyBf93+n/wwf8z6/7t37/P/TomthnQELS"
    "wPS0lD7du7ZITk+N6872SU9JTU5p/1UcDAu9U+Lihsf1/HgqlWW7JsbG9e2f3Dumf2r3ro3ikuJSYvp3Z+sl909Oadfnw4iP9vIP"
    "VzaB5pPanf1Is3XMwISU9H8k1qx+g+7skITYvnFp7dKG9f9bQkMSkt6zVz8uNTEteWC7IQlp8FYp3dnmMcOS09NaxkCaySl9S0Fq"
    "pT7yWyr246V/M7hTQlJs8pD/3Ni/XAD/+iSnxKQlJCeV7c72T+idEpMy7K/DYz/ym/b3UvjoU++pfJh8dzbp/S3/vPZ/A///lP8/"
    "5f9/yP9lK1eGEbjcp/z/Kf//S/4fEJcWExuTFlOqX2py0n/c/yuWL/+v5v+KlSr8Y/6PLl/hU/7/7zhGsPngEdWsdUyfxJi+ce3S"
    "UtL7pKWnxEVVzRfV+qM5NIfmUCcptiE0hqgSf7m8f3rfhCR40cfxH07WSU/7CtYI8GTXv558f4z4u28fLm0wICah//tb/Enw7358"
    "n5M//PZ3P43867fu/zImCpYEfVISBr7PyP9ALqpJ7PszH633b883T+gTl5Qa94+X/+Wu/zygU1zv1IS0v2Fp5F+kEDdsSHJKbOqH"
    "YR+LhmqdklMSUwfG9ImrVmfgwLiYlJgk+PG9BPNBh8r3XobV/iLEL0t+FHDJOq2bdIxLSf1zDmX/6fcWMQlJ7T5M8/3vf9bfUexI"
    "9v+a/F/un/N/mU/5/78l/1f6u/xfpkKVyqXgf+WqfFr+f8r/f5P/SzZP6PtV2n9uF+DfWv9XjC73Z/4vU6Hih/xfDm4KfMr//2eu"
    "/+t+GPHBXD5tAvxvvwnwaf3/af3/T/k/ukolWAJ8KgA+5f9/zP//qV2Af2v9XwkW+3+f/+EGwKf9/0/r//9l6/+P1vsf3gX452H/"
    "1+0FfFr/f1r//yX/Vy5bpXL56PKlKpavEF2xwqf0//9q/v/wlpwQmwqX+wNK9U1I+yq9d6m+SekDkhPhde+XOSXjhsWV7PN+yF83"
    "BOCH+IS+f76VGjSg/78//5eL/rD/X75CxfJl4f8g+v3yv9yn/P/fcSQMGJickpavTVqb9IQ+ieyfX/+ymv1oEKU+KjX946KXhav9"
    "919bJMfG9f8zuX88Uy8mLa5vcsqwv8n479e5VfMllKmcVCTqz92CqKJ//TUBEoZZbGBKXHxcShzMjqkl/1x3/0vuT01OT+kDaUR9"
    "ZOJPIu8N7M8E/L9mH/z/Wf//tP7/tP7/p/xfBUIAK39yq0/5/z+c/+HCLqnU0L/N/v9m/i9TqVK5v8//ZStV+JT//3uO6rWgsvIN"
    "/rjkrBFVplR0VD6YiZNjE5L61ojq0L5hycpRtWqy1RP7xPfNBy9NSq0R9VVa2sCqpUsPGTLkQ5EAi4XSUIhJcDsbmsz7C0u/J/Nn"
    "Bv8wpurQ1IS/Gzek3IdhZaH2S3/ZovmHRwcxJROS3tPpE/fXsakJVVM//NQcWmnaBw7/XTf/p02Ffzn+XeM/fCg1NDU2quYHUh+m"
    "H5/QP+5DQVMjKqr0n+f7piSnD/zz5F/qm5p/vXt16BmwHPr4c+pXyUOaJMUmwIkkp0TlSxs2EJ6sm5z8twM+DPpzUV8TbsXEVf/L"
    "g7a/IVr6A9X/yV1aJqclxCd8FNh/2Y2S3t9kWN24+GS4WfTnTZokpf1r9ygb/T+4w4cr4OOnmhWql37/9g8/xAytWREOe//+72QK"
    "PryJSYRcxKUMhor4/8tVmX+NqzJl/xNstYdZFj5s+q+T1b/BVfXSH4wV+vIH667Jfqr/PtV//+P6r0K58mU/Pf/5VP/9R+o/uE5P"
    "+jhiYP+4tLhSQ2IG//vqv0rly8Hf/mH/B25Afqr//juOtk0aNrwDA22nOh0bxA9Iy5cBnkPgK6ojAPU3AYCCDKB5k3btc8LzTVo2"
    "bNWkXcP2IvzcPGZwfMWypcrAf/BR3ftHgvM/hGsMCCAPKAuaglgwEswFP4DtYCfYBJaA0eBLUAREwu1hUlgsfB5sDAYHzYPooGBQ"
    "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"
    "tJ+NS/BajdlojuFf45dxy9hgZgiVSowEFcqQj0mFpdtipFRLngO+QIQRTpahDzAC9yNXkj/O+djPGIMqSZYxwrQJ8ERtpAdiBemG"
    "9LqyG7SlD4kJ1JvMKhA/eP53rilXip1J7yT3Gyc1szoXue6clE9aLm2XQ1VFu4+4bDP4C1HIkRe5MdxYtiDTmYohkmCdJuUqcus5"
    "KV7qIW9T7Fo7owmk2MV42b0ouw4ZyzPAJWDIgkaINk2pL9tQb0vsdW+k/KRu1JcRE6lwZg47gfud+5YrCw5CEr0cxJNjWgF1Jfq6"
    "PDLVD0o/yh3VImCU3MFsVomN4E4gN70X14d9REdQXYg4/WO1mPJIaiNVkt6XRsqnlfFafyMSPbIZZJYV3EVuKreNHcJ8Rz0kOCNY"
    "+wC5/KOk6lIccr77K48Qt6wnpoIlM5EdzB3n1nAKe57pQr9LfmIc0YqoW+XdyHPvKN2SvHK8WlUPIO5jZn+NDeS2cDs57G1hz9JW"
    "qhkxQF8KegQnx0itkA2+CPyMBVoyODel6dXMKXYq8vrt3Cy2LbOJukooerC2EHv+50jtpBlSW3kcGBXn9Z3ENCqISWE7cZu4ydwF"
    "FpnOdCr5kXFAe039Rj4l9ZeGSYJcAlm8TfXSRDqiHAsbwM1FjnwxriT7BS1QYUQvfYVaQykFjzEI+eRfygXUrdrbRh8wfxYx+9h4"
    "5OQ35xLANphHfU88hhQrlSR5ozQE5O14eakSpP2uHyDepaxMNFuXm4Xc+R2gGJSiB5LvgghhhT+8I42WZsNbRChr1J56FUJExKeh"
    "r0dww7nHrI9ZQD8kA0EQWq3WU2rKi6Qpkke6KtdQj2mzjRiyJNgX69jO3CiuHNcOZJrR1C7iDqTYoLwjH5WmSyekWfJXSjNN108Q"
    "M6mSTGe2LDcMtjkX2eYG1Y4cD9JTZfWabEgLpe3wFr2UA2oC2AcquYi+z1wDH6Q7d4r9iRlNXyKLElH6WrWV0hJj9VOphGzI7dTr"
    "2kpjCFmcnsjMY8O53pzOVmX/pKOpT0ExCdZ2KPPk69Ja6YG0Vb6q9NUKGuchRQGmMctyXTgr52R7wpLrkinGHi1YfSiXBNviR3iL"
    "NOVnjOoWALXPpa8x37INudrcRvYLpj99kGSJNvoGtZvSRz4rHZXqyVbFoUradmMYWQS8hwlsaa4+d4U1sSfpSMRwF/QQbb+yVlak"
    "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"
    "3EI8CZ674kLcOSfipsLxtE+yBdNj/5EI2Tvin0vhtNfI0E5mrzzp4ZcL0zXZkZi7LNm7NcfJQc6khPrWOjnecyXVt4aH/BNxM5qZ"
    "Zo3OqD+zR61BKXa4ydiUKv+SwDnMKReJQ1+QODTsH4mc8Qj3adxvDcKDjVSX/d+RNsuG/5Z6/yVhY1OdGRbwKtX+h4PqvPW/vPj/"
    "f3X8Xzc0ol7e+l9e/P/P4n//g5gcC39/K/4PrV07LCRn/B8WXjckL/7//yD+/4crfU9C/kw7Cn5iRy85HeOPilBDp4yXzf0x2MsK"
    "4u1Ev5VZawWHZL/kyfsvuRBPf522lGcXtMx4/a/cxGQPNc3mTlkNi3TZE7KtUjqTklyZUToCk9ikxPi0nMuCOaK3rpnBSn3rk8qC"
    "M2+fs6KZ4ByFsZ6UFXrmXnO29cjM9SjbSP+SW24faK1htcfbkvHsMeuNKi+uX+YsUN/63BJnNFZLrY6Urq6k5GT/A89ni7A5i2Qq"
    "zR7bbbAjpXlazLP12pxLn4iOE2yuLk+aEJSS/VEpJMAaUAIWNzMaNig+KckZlGKtCX1ke3SaWcqJUinWijiVfVnTlepEbJhgfRMP"
    "sa2NrYEhgVYsZwRWwXpHgn/No34gfgc5czvvzLEG+lRgPFe3uzIaFJRd1JxagyzZxHhBFTidoYuXfEJqYoekETlqz/6hz+rN/tQ6"
    "cwn5VeaUFYtXyf1DXUlxWODtZEtNydmupz0Nmcs9fZGjjqcf6ojx32y/fPHSBbvo5kiOQld3y7Y20zLNbm2O6SQrcM8q1TU1OrOQ"
    "f2AFP/3kp4I1zro6Q+TYbEH/0xswXJ113+VItFYMDaz+grFlVP10+FSp8lx7Mqa3ka5UrAdmKAmDoc/Tj3nmuIIzzz53D+TKRfin"
    "Qnexp6QmoMFPhc1oxXPrU351BidiO0Mu1QRmbKio4V/PiLbFDK2R0f0ZtvvcieSMis05l6WyrcNk1Jyj85/dPVX/h4192jYs2PrD"
    "SufLGxQ43GEfUQNraLDswX8lXnbr/3el62YbinnH+uQZwohXiJipyZShjuQaMJwRNmfsXwqaNXKfuwHt91+4wFbuJcPhFYtrGVc8"
    "55+qvbC0luVFs20oyTk6XlyIe4mzeeUzHv9RqVJWK17wi7kVzbHE95KPfOmjnBfqaJT7KiEeK2U8T8jxkNBvNlCD326Sg164xH/k"
    "tKYML2PNfA4RWP0fXpDykiueiv7C2VyWMXNtRoodS8jDESjltvCZez/4dxPB+l62BPrEADIuzjXMgJpf6LtcFZ9j2PytJdfsbXtu"
    "TTy35puzLwRnxIsdMkd3ZpQ4YESSc6h/B1A2H2n3KysS9QVmD/yenXc5XP5oJtfJ64kPyfqQV+7jScX+osSYtPo5mhTcwT9HxXfP"
    "PJe94dk2WD7X7uc3yD3Ze5CU8nIXOvbJxrasbQxd7Mn+Mtj8kvnI3K8uW4wr59tm8xNNvnAKsWcSpo+mECWXnQr+4v74+OnGrJgY"
    "e7LLHpu5dyNz5157+yBX1l6OjG15UY7Y2Hh75jvPKsTKgSPG4cradfH0cXQXhEA5ziGAe24/F3obe+Fy2c/15Lonm6JyrTTzpPnZ"
    "VqHhdmfLRBvW9p/sbDHnsu3jSXgVlOBXzvMDwD+GMk4ER2e2u2HDhjk18dIhk2PGfm7cIBZNsb+08uxqfWn19pF43B+bGfTleOPV"
    "QzSz9T0H2/2PaZ+2fYT/dZXcJqXcw9qMPVX+a4KfmMkL/ijbPiB0Uq57//yml70n/+s2BmY3pBwXPN2Y+oqZ8dkCzH9+Z+Bz7fD7"
    "Kf++rawW/e1Ng/+wmiS/plxpuQSxIcF1ELGGBoe8Yp75GxvaXhJjP7kxsGaV+Ivg/+/MPYOwm/Z5t5f94UJwzpPZJM7SJVZUHAmp"
    "Cbn3R5zTEev/C84pNPwlV76kD7JfWtv8z8wg+7UR5n/Y+TllfuYeMxYUnlPOk1HhX23w++Cc/fmycfyXm43/0XB94aq/Gnj/fPD9"
    "KwPQf6uRmvC3qvrLUfiSusa+8E6Ozsm9U54c8YiJoPmwXE+6XnWb/vzx0tv2549X3Mb/neFc5VXKfNWG2mcPdBxPt/S29P/dJUcA"
    "kLtax+Y2Q2U9Jfc/L6z/qt3qf2cjeq6zWAIKOPxR1KsuNL/Y9c8eob58E+3f1Nh/17OK/5onKc9FZa945vFil/53quoVT0Fyfary"
    "N5qV67OS/3Cr/urByT98JpNrM59/0vJiEzOfz2eX/4nr9Dcglyn+/94ugbz1/7z1/xfW//GrXq16eev/eev/f7n+j5QsW6x/Z9aQ"
    "lKTEV4z/V+z/Da0VEvrc+n+d2rVD89b//xNH5mwf2K4Toi8bQkVMjDFYMbUHYhLPjBBqNk32p89kPZxGyfhUhJqB2ZcYApumuvxh"
    "aGD21TH/8WIsEdgS4Xm8v3ZXUjS2vtpdLnuTOP97/mX+XJ6AB/qfo/rLd8sob+3qvyLwJZN+v2fXBzZHFmtckjPNf23XtBR/KBCZ"
    "mHnL4H+Wm61kC3tKjNORnPE2CrfMsm3cwsYnZyQoYkESC4fx8Xjs6hpsR6JXjYz/sCSDB+XRaf6H3P7nTLh3yirs8oczGcFMitVu"
    "ixnsT2LM2koZnP2T/XecgTnuKnOcjfWf+8sxmP2S9g48z0rJ0FfrTu1rYLtEjSRnjXiowpm92BOdPn10ne1cD6RYZmkiJBhPZrKf"
    "62mPTvGnAeLcYJcrOaV+zZpZokHKmk/Fq5lDPHO2tbrAt2pkWlWNpp0ia0RlPtGoke0jw59+4LOi/tXirhk95C+RbaNRYN62zrwj"
    "78g78o68I+/IO/KOvCPvyDvyjrwj78g78o68I+/IO/KOvCPvyDvyjrwj78g78o68I+/IO/KO/wdTuVJwABgBAA=="
)
# ==== END EMBEDDED KDE PAYLOAD ====

STEP_NAMES = ["repos", "packages", "flatpaks", "kde", "scripts", "services"]


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def run(cmd, dry=False, check=True, quiet=False, capture=False):
    line = " ".join(str(c) for c in cmd)
    if not quiet:
        print(f"  $ {line}")
    if dry:
        return subprocess.CompletedProcess(cmd, 0, b"", b"")
    return subprocess.run(
        cmd,
        check=check,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )


def dnf_enabled_repo_ids():
    try:
        out = subprocess.run(
            ["dnf", "repolist", "--enabled"],
            capture_output=True, text=True, check=False,
        ).stdout
    except FileNotFoundError:
        return set()
    return set(out.split())


def rpm_installed(name):
    return subprocess.run(
        ["rpm", "-q", name], capture_output=True, check=False
    ).returncode == 0


# --------------------------------------------------------------------------
# steps
# --------------------------------------------------------------------------
def step_repos(dry):
    print("\n[1/6] Repositories")
    enabled = dnf_enabled_repo_ids()
    fedora_ver = subprocess.run(
        ["rpm", "-E", "%fedora"], capture_output=True, text=True, check=False
    ).stdout.strip() or "0"

    for repo in REPOS:
        if repo["kind"] == "rpmfusion" and rpm_installed(repo["pkg"]):
            print(f"  ok  {repo['name']} (already installed)")
            continue
        if repo["kind"] != "rpmfusion" and repo["id"] in enabled:
            print(f"  ok  {repo['name']} (already enabled)")
            continue
        print(f"  +   {repo['name']}")
        kind = repo["kind"]
        if kind == "rpmfusion":
            run(["sudo", "dnf", "install", "-y", repo["url"].format(ver=fedora_ver)],
                dry=dry, check=False)
        elif kind == "copr":
            run(["sudo", "dnf", "copr", "enable", "-y", repo["spec"]],
                dry=dry, check=False)
        elif kind == "repofile":
            run(["sudo", "dnf", "config-manager", "addrepo",
                 f"--from-repofile={repo['url']}"], dry=dry, check=False)
        elif kind == "ghcli":
            if not rpm_installed("fedora-workstation-repositories"):
                run(["sudo", "dnf", "install", "-y",
                     "fedora-workstation-repositories"], dry=dry, check=False)
            run(["sudo", "dnf", "config-manager", "setopt", "gh-cli.enabled=1"],
                dry=dry, check=False)


def step_packages(dry):
    print("\n[2/6] RPM packages")
    if not rpm_installed("plasma-desktop"):
        print("  + KDE Plasma not found, installing the KDE environment first")
        run(["sudo", "dnf", "install", "-y", "@kde-desktop-environment"],
            dry=dry, check=False)

    for group, pkgs in RPM_PACKAGES.items():
        if dry:
            print(f"  + {group}: {' '.join(pkgs)}")
            continue
        print(f"  + {group}")
        res = run(["sudo", "dnf", "install", "-y"] + pkgs,
                  quiet=True, check=False, capture=True)
        if res.returncode == 0:
            continue
        # Batch failed - retry one by one so a single bad name cannot
        # block the whole list, and report exactly what failed.
        failed = []
        for pkg in pkgs:
            one = run(["sudo", "dnf", "install", "-y", pkg],
                      quiet=True, check=False, capture=True)
            if one.returncode != 0:
                failed.append(pkg)
        if failed:
            print(f"    [!] Could not install: {', '.join(failed)}")
        else:
            print("    (batch retry: all installed)")


def flatpak_installed(app_id):
    return subprocess.run(
        ["flatpak", "info", app_id], capture_output=True, check=False
    ).returncode == 0


def flatpak_remotes():
    out = subprocess.run(
        ["flatpak", "remotes", "--columns=name"],
        capture_output=True, text=True, check=False,
    ).stdout
    return set(out.split())


def step_flatpaks(dry):
    print("\n[3/6] Flatpak apps")
    if not shutil.which("flatpak"):
        print("  [!] flatpak is not installed - skipping.")
        return
    remotes = flatpak_remotes()
    if "flathub" not in remotes:
        run(["flatpak", "remote-add", "--if-not-exists", "flathub",
             "https://dl.flathub.org/repo/flathub.flatpakrepo"],
            dry=dry, check=False)
        remotes.add("flathub")

    installed = subprocess.run(
        ["flatpak", "list", "--app", "--columns=application"],
        capture_output=True, text=True, check=False,
    ).stdout.split()
    missing = [(a, r) for a, r in FLATPAKS if a not in installed]
    if not missing:
        print(f"  ok  all {len(FLATPAKS)} apps already installed")
        return
    for app_id, remote in missing:
        if remote not in remotes:
            remote = "flathub"
        print(f"  +   {app_id} ({remote})")
        res = run(["flatpak", "install", "--noninteractive", remote, app_id],
                  dry=dry, check=False, capture=True)
        if res.returncode != 0 and remote != "flathub":
            run(["flatpak", "install", "--noninteractive", "flathub", app_id],
                dry=dry, check=False, capture=True)


def _safe_extract(tar, dest):
    dest = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest) + os.sep):
            raise RuntimeError(f"unsafe path in payload: {member.name}")
    tar.extractall(dest)


def step_kde(dry):
    print("\n[4/6] KDE configs, themes and widgets")
    if not KDE_FILES and not KDE_ASSETS_B64:
        print("  [!] No embedded KDE payload in this copy - skipping.")
        return
    home = Path.home()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    for rel, content in KDE_FILES.items():
        dest = home / rel
        text = content.replace("__HOME__", str(home))
        if dry:
            print(f"  +   {rel}")
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and dest.read_text(errors="replace") != text:
            shutil.copy2(dest, dest.with_name(dest.name + f".bak-{stamp}"))
        dest.write_text(text)
    if not dry and KDE_FILES:
        print(f"  ok  {len(KDE_FILES)} config files written (existing ones backed up)")

    if KDE_ASSETS_B64:
        names = []
        if dry:
            print("  +   themes: Darkly, Darkly-Light, eye-care widget")
        else:
            raw = gzip.decompress(base64.b64decode(KDE_ASSETS_B64))
            with tarfile.open(fileobj=BytesIO(raw), mode="r:") as tar:
                names = [m.name for m in tar.getmembers() if m.isfile()]
                _safe_extract(tar, home)
            print(f"  ok  {len(names)} theme/widget files extracted")

    # Apply what can be applied without a re-login (best effort).
    if not dry:
        for cmd in (
            ["kbuildsycoca6", "--noincremental"],
            ["plasma-apply-colorscheme", "Darkly"],
            ["plasma-apply-desktoptheme", "darkly"],
        ):
            if shutil.which(cmd[0]):
                subprocess.run(cmd, capture_output=True, check=False)
        print("  ok  applied theme where possible")
    print("  ->  log out and back in for the panel/theme changes to fully apply")


def step_scripts(dry):
    print("\n[5/6] Personal scripts -> ~/.local/bin")
    src = Path(__file__).resolve().parent / "scripts"
    dest_dir = Path.home() / ".local" / "bin"
    if not src.is_dir():
        print(f"  [!] {src} not found - skipping.")
        return
    if not dry:
        dest_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for item in sorted(src.iterdir()):
        if not item.is_file():
            continue
        dest = dest_dir / item.name
        if dry:
            print(f"  +   {dest}")
        else:
            shutil.copy2(item, dest)
            dest.chmod(0o755)
        count += 1
    if not dry:
        print(f"  ok  {count} scripts installed")
        if str(dest_dir) not in os.environ.get("PATH", ""):
            bashrc = Path.home() / ".bashrc"
            line = '\nexport PATH="$HOME/.local/bin:$PATH"\n'
            if bashrc.exists() and "local/bin" not in bashrc.read_text(errors="replace"):
                with bashrc.open("a") as fh:
                    fh.write(line)
                print("  ok  added ~/.local/bin to ~/.bashrc PATH")
            else:
                print("  note: add ~/.local/bin to your PATH")


def step_services(dry):
    print("\n[6/6] Services")
    for svc in SERVICES:
        unit = subprocess.run(
            ["systemctl", "list-unit-files", f"{svc}.service"],
            capture_output=True, text=True, check=False,
        ).stdout
        if svc not in unit:
            print(f"  -   {svc} not present, skipping")
            continue
        run(["sudo", "systemctl", "enable", "--now", svc], dry=dry, check=False)


# --------------------------------------------------------------------------
# payload export (for reviewing/refreshing the embedded payload)
# --------------------------------------------------------------------------
def _drop_section(text, section):
    out, dropping = [], False
    header = f"[{section.lower()}]"
    for line in text.splitlines():
        if re.match(r"^\[.*\]$", line):
            dropping = line.strip().lower() == header
        if not dropping:
            out.append(line)
    return "\n".join(out) + "\n"


def _drop_key(text, key):
    return re.sub(rf"^{re.escape(key)}=.*$", "", text, flags=re.M)


def _sanitize_paths(text):
    text = re.sub(r"file:///home/[^/\s\"']+", "file://__HOME__", text)
    text = re.sub(r"/home/[^/\s\"']+", "__HOME__", text)
    return text


def _sanitize_appletsrc(text):
    # Drop the desktop (folder view) containment: it carries icon positions
    # and personal file names; panels and widgets are kept.
    text = re.sub(
        r"(?ms)^\[Containments\]\[1\].*?(?=^\[Containments\]\[2\])", "", text
    )
    for key in ("changedPositions", "positions", "screenMapping", "itemsOnDisabledScreens"):
        text = _drop_key(text, key)
    # Weather station location is personal.
    text = re.sub(
        r"(?ms)^\[Containments\]\[2\]\[Applets\]\[7\]\[Applets\]\[19\]\[Configuration\]\[WeatherStation\].*?(?=^\[)",
        "",
        text,
    )
    # Keep only launchers that do not point inside a home directory.
    def clean_launchers(match):
        items = [i for i in match.group(1).split(",") if "/home/" not in i]
        return "launchers=" + ",".join(items)
    return re.sub(r"^launchers=(.*)$", clean_launchers, text, flags=re.M)


KDE_EXPORTS = [
    (".config/kdeglobals", None),
    (".config/kwinrc", "kwinrc"),
    (".config/konsolerc", None),
    (".config/katerc", None),
    (".config/dolphinrc", None),
    (".config/arkrc", None),
    (".config/okularrc", "okularrc"),
    (".config/spectaclerc", "spectaclerc"),
    (".config/kiorc", None),
    (".config/kded5rc", None),
    (".config/baloofilerc", None),
    (".config/plasma-localerc", None),
    (".config/plasmashellrc", "plasmashellrc"),
    (".config/plasma-org.kde.plasma.desktop-appletsrc", "appletsrc"),
    (".config/kdedefaults/kcminputrc", None),
    (".config/kdedefaults/kdeglobals", None),
    (".config/kdedefaults/ksplashrc", None),
    (".config/kdedefaults/kwinrc", None),
    (".config/kdedefaults/package", None),
    (".config/kdedefaults/plasmarc", None),
    (".local/share/konsole/Profile 1.profile", None),
    (".local/share/konsole/Breeze.colorscheme", None),
    (".local/share/konsole/bookmarks.xml", "paths"),
]

KDE_ASSET_DIRS = [
    ".local/share/plasma/look-and-feel/Darkly",
    ".local/share/plasma/look-and-feel/Darkly-Light",
    ".local/share/plasma/plasmoids/com.github.gnumoksha.kde-eye-care",
]


def collect_kde_payload(home):
    """Return (files, asset_paths) for a sanitized KDE payload."""
    files = {}
    for rel, mode in KDE_EXPORTS:
        src = home / rel
        if not src.is_file():
            continue
        text = src.read_text(errors="replace")
        if mode == "kwinrc":
            text = re.sub(r"(?ms)^\[Tiling\]\[[^\]]*\].*?(?=^\[|\Z)", "", text)
            text = re.sub(r"^Id_\d+=.*$", "", text, flags=re.M)
            text = re.sub(r"\n{3,}", "\n\n", text)
        elif mode == "okularrc":
            text = _drop_section(text, "Recent Files")
        elif mode == "spectaclerc":
            text = _drop_key(text, "lastImageSaveLocation")
        elif mode == "plasmashellrc":
            text = _drop_section(text, "Updates")
        elif mode == "appletsrc":
            text = _sanitize_appletsrc(text)
        elif mode == "paths":
            text = _sanitize_paths(text)
        files[rel] = text

    assets = []
    for rel in KDE_ASSET_DIRS:
        directory = home / rel
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            inside = path.relative_to(directory).as_posix()
            # Skip preview thumbnails (weight) and layout files (they can
            # embed the personal desktop icon layout; the panel is restored
            # from the appletsrc config instead).
            if "contents/previews" in inside or "contents/layouts" in inside:
                continue
            assets.append(path)
    return files, assets


def pack_assets(assets, home):
    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz", compresslevel=9) as tar:
        for path in assets:
            tar.add(path, arcname=str(path.relative_to(home)))
    return buf.getvalue()


def export_payload(out_dir):
    home = Path.home()
    out = Path(out_dir).expanduser().resolve()
    kde_dir = out / "kde"
    files, assets = collect_kde_payload(home)

    for rel, text in files.items():
        dest = kde_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)

    blob = pack_assets(assets, home)
    (out / "kde-assets.tar.gz").write_bytes(blob)

    flatpaks = subprocess.run(
        ["flatpak", "list", "--app", "--columns=application,origin"],
        capture_output=True, text=True, check=False,
    ).stdout.strip()
    (out / "flatpaks.txt").write_text(flatpaks + "\n")

    rpms = subprocess.run(
        ["dnf", "repoquery", "--userinstalled", "--qf", "%{name}"],
        capture_output=True, text=True, check=False,
    ).stdout
    (out / "rpms-userinstalled.txt").write_text("\n".join(sorted(set(rpms.split()))) + "\n")

    print(f"  ok  sanitized KDE files : {len(files)} -> {kde_dir}")
    print(f"  ok  theme assets        : {len(assets)} files, {len(blob) / 1024:.0f} KiB (gzipped)")
    print(f"  ok  flatpaks.txt, rpms-userinstalled.txt")
    print("  ->  review, then rebuild the embedded payload with these files.")


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Personal Fedora/KDE restore")
    parser.add_argument("--dry-run", action="store_true", help="print commands only")
    parser.add_argument("--yes", action="store_true", help="skip the confirm prompt")
    parser.add_argument("--only", help=f"comma-separated subset of: {','.join(STEP_NAMES)}")
    parser.add_argument("--skip", help=f"comma-separated subset of: {','.join(STEP_NAMES)}")
    parser.add_argument("--export", metavar="DIR",
                        help="dump the sanitized KDE payload and package lists for review")
    args = parser.parse_args()

    if args.export:
        print(f"Exporting sanitized payload to {args.export}")
        export_payload(args.export)
        return

    if os.geteuid() == 0:
        print("ERROR: run this as your normal user, NOT with sudo.")
        print("The script will ask for your sudo password itself.")
        sys.exit(1)

    if not Path("/etc/fedora-release").exists() and not args.dry_run:
        print("ERROR: this script is for Fedora only (no /etc/fedora-release found).")
        sys.exit(1)

    steps = set(STEP_NAMES)
    if args.only:
        steps = {s.strip() for s in args.only.split(",")} & steps
    if args.skip:
        steps -= {s.strip() for s in args.skip.split(",")}

    print("=" * 60)
    print("  MSI Fedora / KDE setup")
    print("=" * 60)
    print(f"  Repos    : {len(REPOS)}")
    pkgs = sum(len(v) for v in RPM_PACKAGES.values())
    print(f"  RPMs     : {pkgs} packages")
    print(f"  Flatpaks : {len(FLATPAKS)} apps")
    print(f"  KDE      : {len(KDE_FILES)} configs, {'yes' if KDE_ASSETS_B64 else 'no'} theme payload")
    print(f"  Steps    : {', '.join(s for s in STEP_NAMES if s in steps)}")

    if not args.dry_run and not args.yes:
        try:
            answer = input("\nProceed? [y/N] ").strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Aborted.")
            return
    if not args.dry_run and steps & {"repos", "packages", "services"}:
        # Cache sudo credentials up front for the steps that need them.
        subprocess.run(["sudo", "-v"], check=False)

    for step in STEP_NAMES:
        if step not in steps:
            continue
        fn = {
            "repos": step_repos,
            "packages": step_packages,
            "flatpaks": step_flatpaks,
            "kde": step_kde,
            "scripts": step_scripts,
            "services": step_services,
        }[step]
        try:
            fn(args.dry_run)
        except KeyboardInterrupt:
            print("\nCancelled by user.")
            return

    print("\nDone. Re-login for the full KDE theme/layout, then check `listScripts`.")


if __name__ == "__main__":
    main()
