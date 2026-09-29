# personal-scripts

Some personal scripts I use to set up my system(s). Included are useful utility scripts for CLI usage.

## Scripts
| Script | Description |
|---|---|
| **compressvid** | Compress a local video file with smart-replace logic. Uses HEVC via NVENC or libx265. |
| **compresspdf** | Strip embedded videos/audio/attachments from PDFs and losslessly compress them. |
| **getAudio** | Extract audio from a video as MP3. Supports VBR quality and a mono/64 kbps lecture mode. |
| **viddl** | Download YouTube videos/playlists with yt-dlp, with optional post-download GPU/CPU compression. |
| **playmusic** | Search YouTube, stream audio through mpv, manage history & favourites, download MP3s. |
| **listScripts** | Print a summary of all scripts. Pass `-h` to display every script's full help panel. |

## Quick install

### Fedora (KDE)
```bash
git clone https://github.com/zoroaster1x/personal-scripts.git
cd personal-scripts
./setupMSIFedora.py        # repos + RPMs + Flatpaks + KDE theme + scripts
```
`setupMSIFedora.py` recreates my Fedora setup on a fresh install:
- **Repos** – RPM Fusion, MSI-EC COPRs (msi-ec + acpi_ec akmods), Darkly theme COPR,
  GitHub CLI repo, Mullvad VPN repo.
- **RPMs** – the user-installed apps/tools (not the OS defaults) plus everything the
  scripts need: `ffmpeg`, `python3-rich`, `python3-pikepdf`, `qpdf`, `poppler-utils`,
  `ghostscript`, `yt-dlp`, `mpv`, `tesseract`, `ocrmypdf`, `kate`, `darkly`,
  `papirus-icon-theme`, `mcontrolcenter`, akmods for the MSI laptop, ...
- **Flatpaks** – every user-installed app (runtimes come as dependencies).
- **KDE** – Plasma configs, Darkly global themes and the eye-care widget from a
  sanitized payload embedded in the script (no personal paths or names; `$HOME`
  is templated and substituted on install).
- **Scripts** – copies `scripts/` to `~/.local/bin`.

It supports `--dry-run`, `--only <steps>`, `--skip <steps>` and `--export <dir>`
(dump the sanitized KDE payload for review/refresh).

### CachyOS / Arch (legacy)
```bash
python setupMSIArch.py        # installs packages via paru/yay, copies scripts to ~/.local/bin
```

## Usage

### compressvid
```bash
compressvid video.mp4                   # medium HEVC compression (NVENC or CPU)
compressvid video.mp4 -c high           # high compression
compressvid video.mp4 -r                # smart-replace (keeps original if savings < 1 MB)
compressvid video.mp4 -r -a             # smart-replace + extract MP3
compressvid video.mp4 -o out.mp4        # custom output path
```

Compression levels map to CQ/CRF values: **light** = 24, **medium** = 29, **high** = 34.

### compresspdf
```bash
compresspdf lecture.pdf                 # -> "lecture-fixed.pdf" (lossless, media stripped)
compresspdf lecture.pdf -r              # smart-replace the original if smaller
compresspdf lecture.pdf -i              # also re-encode embedded JPEGs at q95
compresspdf lecture.pdf -L -M           # also strip links and metadata
```

It removes embedded videos/audio/attachments (the usual reason presentation PDFs
are hundreds of MB), recompresses every lossless stream and packs objects into
object streams. Page rendering is untouched by default, so visual quality is kept.

### getAudio
```bash
getAudio video.mp4                      # VBR quality 2 (~192 kbps)
getAudio lecture.mp4 -l                 # mono 64 kbps (great for speech)
getAudio video.mp4 -q 0 -o ~/Music/     # best quality, save to directory
```

### viddl
```bash
viddl "https://youtube.com/watch?v=..." # 720p, saved to ~/Downloads
viddl "URL1" "URL2" -q high             # batch 1080p+
viddl "https://..." -a                  # audio-only MP3
viddl "https://..." -c high -p ~/Vids   # download + max compression
```

### playmusic
```bash
playmusic "artist - song"               # search & pick from results
playmusic "rotary park" -f              # auto-play first result
playmusic "Hawaii Part II" -a -b -l     # album, background, loop
playmusic -H                            # show playback history
playmusic -F                            # show favourites
playmusic -k                            # kill background player
```

Config lives in `~/.config/playmusic/config.json` (timeout, volume, result count).
History and favourites are stored under `~/.local/state/playmusic/`.

### listScripts
```bash
listScripts                             # summary table
listScripts -h                          # full help for every script
```

## GPU vs CPU encoding
Both **compressvid** and **viddl** probe `ffmpeg -encoders` at runtime:

- **NVENC available** → `hevc_nvenc` with CUDA hardware decode and preset `p5`.
- **NVENC unavailable** → `libx265` with preset `medium` (works on any machine with ffmpeg).

No flags are needed; the fastest available encoder is selected automatically.

## License

[MIT](LICENSE)
