# Bambu Timelapse Downloader

A Python tool to automate downloading, upscaling, and making streamable timelapse videos from a Bambu 3D printer via FTPS.

---

## Features

- **Secure Download:** Downloads timelapse videos from your Bambu printer using FTPS.
- **Flexible Selection:** Download the latest or all available timelapse videos.
- **Watch Mode:** Continuously checks for new videos every 60 seconds and downloads them automatically.
- **Automatic Conversion:** By default, upscales videos to 1080p and makes them streamable using ffmpeg with NVIDIA GPU acceleration.
- **Clean-Up:** Deletes remote files after download and deletes original files after successful conversion.
- **Configurable:** Printer credentials are stored in a config file, not in the script.
- **Organized Output:** Stores videos in a `timelapse` subfolder by default.

---

## Requirements

- Python 3.7+
- tqdm
- ffmpeg (with NVIDIA GPU support and `hevc_nvenc`)
- Bambu printer with FTP access

---

## Installation

Install Python dependencies with pip:
```bash
pip install -r requirements.txt
```

You also need ffmpeg with NVIDIA GPU support (see [ffmpeg docs](https://ffmpeg.org/)).

---

## Setup

1. **Clone this repository.**

2. **Create a config file:**
   - Copy `config.json_template` to `config.json` and fill in your printer details:
     ```json
     {
       "printer_ip": "192.168.1.123",
       "access_code": "YOUR_ACCESS_CODE"
     }
     ```

3. **Ensure ffmpeg is installed with NVIDIA GPU support.**

---

## Usage

```bash
python get_timelapse.py [options]
```

### Options

- `--last`  
  Download only the latest timelapse video (default if no option given).

- `--all`  
  Download all available timelapse videos.

- `--out <folder>`  
  Output directory to save downloaded videos (default: ./timelapse).

- `--do_not_delete`  
  Do not delete remote file(s) after download (ignored in --watch mode).

- `--watch`  
  Continuously check for new timelapse files every 60 seconds and download them.

- `--no-make-streamable`  
  Do **not** convert videos to streamable 1080p using ffmpeg (by default, conversion is ON).

### Example Commands

Download the latest timelapse and make it streamable (default):
```bash
python get_timelapse.py
```

Download all timelapses and keep the originals on the printer:
```bash
python get_timelapse.py --all --do_not_delete
```

Download to a specific folder, convert to streamable, and run in watch mode:
```bash
python get_timelapse.py --all --watch --out /path/to/folder
```

Download without conversion:
```bash
python get_timelapse.py --no-make-streamable
```

---

## ffmpeg Conversion

By default, after download, each video is converted to a streamable 1080p MP4 using your NVIDIA GPU:

```bash
ffmpeg -y -hwaccel cuda -i input.mp4 -vf scale=1920:1080 -c:v hevc_nvenc -preset p7 -tune hq -b:v 15M -tag:v hvc1 -video_track_timescale 90000 output_streamable.mp4
```

The original file is deleted after successful conversion.

---

## Notes

- Ensure your printer’s FTP server is accessible and credentials are correct (set in `config.json`).
- ffmpeg with NVIDIA GPU support is required for conversion (see [ffmpeg docs](https://ffmpeg.org/)).
- The script creates a `timelapse` folder for output by default.

---

## License

MIT License

---