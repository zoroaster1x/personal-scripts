# personal-scripts
Some personal scripts I use to setup my system(s) on CachyOS. Included are some useful utility scripts for CLI usage.

## Scripts
| Script | Description |
|---|---|
| **compressvid** | Compress a local video file with smart-replace logic. Uses HEVC via NVENC or libx265. |
| **getAudio** | Extract audio from a video as MP3. Supports VBR quality and a mono/64 kbps lecture mode. |
| **viddl** | Download YouTube videos/playlists with yt-dlp, with optional post-download GPU/CPU compression. |
| **playmusic** | Search YouTube, stream audio through mpv, manage history & favourites, download MP3s. |
| **listScripts** | Print a summary of all scripts. Pass `-h` to display every script's full help panel. |

## Quick install
```bash
git clone https://github.com/zoroaster1x/personal-scripts.git
cd personal-scripts
python setupMSIArch.py        # installs all packages, copies scripts to ~/.local/bin
```

`setupMSIArch.py` installs everything through **paru** or **yay** (whichever is available), including:
- **ffmpeg** – required by compressvid, getAudio, and viddl
- **python-rich** – pretty terminal output used by every script
- **yt-dlp** – YouTube downloading (CLI + Python library)
- **mpv-mpris** / **playerctl** – audio playback for playmusic
It also copies every file in `scripts/` to `~/.local/bin` and makes them executable.


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

### getAudio
```bash
getAudio video.mp4                      # VBR quality 2 (~192 kbps)
getAudio lecture.mp4 -l                 # mono 64 kbps (great for speech)
getAudio video.mp4 -q 0 -o ~/Music/    # best quality, save to directory
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
