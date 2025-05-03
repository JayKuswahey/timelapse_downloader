import ftplib
import ssl
import os
import json
from datetime import datetime
from tqdm import tqdm
import argparse
import time
import subprocess
from telegram import Bot
from telegram.error import TelegramError
import asyncio
import re

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'config.json')
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)
PRINTER_IP = config.get('printer_ip')
ACCESS_CODE = config.get('access_code')

class ImplicitFTP_TLS(ftplib.FTP_TLS):
    """FTP_TLS subclass that automatically wraps sockets in SSL to support implicit FTPS."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):
        """Return the socket."""
        return self._sock

    @sock.setter
    def sock(self, value):
        """When modifying the socket, ensure that it is ssl wrapped."""
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value)
        self._sock = value

from ftplib import all_errors

def parse_ftp_listing(line):
    """Parse a line from an FTP LIST command."""
    parts = line.split(maxsplit=8)
    if len(parts) < 9:
        return None
    return {
        'permissions': parts[0],
        'links': int(parts[1]),
        'owner': parts[2],
        'group': parts[3],
        'size': int(parts[4]),
        'month': parts[5],
        'day': int(parts[6]),
        'time_or_year': parts[7],
        'name': parts[8]
    }

def get_base_name(filename):
    return filename.rsplit('.', 1)[0]

def parse_date(item):
    """Parse the date and time from the FTP listing item."""
    try:
        date_str = f"{item['month']} {item['day']} {item['time_or_year']}"
        return datetime.strptime(date_str, "%b %d %H:%M")
    except ValueError:
        return None

def extract_datetime_from_filename(filename):
    # Matches video_YYYY-MM-DD_HH-MM-SS.*
    m = re.search(r'video_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', filename)
    if m:
        date_str = m.group(1)
        time_str = m.group(2).replace('-', ':')
        return f"Timelapse: {date_str} {time_str}"
    return "Timelapse"

async def try_telegram_upload(config, file_path, caption=None):
    bot_token = config.get('telegram_bot_token')
    channel_id = config.get('telegram_channel_id')
    if not bot_token or not channel_id:
        return False
    try:
        bot = Bot(token=bot_token)
        with open(file_path, 'rb') as vid:
            await bot.send_video(chat_id=channel_id, video=vid, supports_streaming=True, caption=caption)
        print(f'Successfully uploaded to Telegram: {channel_id}')
        return True
    except TelegramError as e:
        print(f'Failed to upload to Telegram: {e}')
        return False

def main():
    parser = argparse.ArgumentParser(description="Download timelapse videos via FTP.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--last', action='store_true', help='Download the latest timelapse video (default)')
    group.add_argument('--all', action='store_true', help='Download all matching timelapse videos')
    parser.add_argument('--do-not-delete', action='store_true', help="Do not delete remote file(s) after download")
    default_timelapse_dir = os.path.join(os.path.dirname(__file__), 'timelapse')
    parser.add_argument('--out', default=default_timelapse_dir, help='Output folder to save videos (default: ./timelapse)')
    parser.add_argument('--watch', action='store_true', help='Continuously check every 60s and download new files')
    parser.add_argument('--no-make-streamable', action='store_true', help='Do NOT use ffmpeg+NVIDIA to upscale to 1080p and make streamable (default is ON)')
    parser.add_argument('--keep-after-upload', action='store_true', help='Keep streamable file after Telegram upload (default: delete after upload)')
    parser.add_argument('--no-gpu', action='store_true', help='Force CPU-only processing (no NVIDIA GPU required)')
    args = parser.parse_args()

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    def download_and_process():
        ftp = ImplicitFTP_TLS()
        ftp.set_pasv(True)
        print('Connecting...')
        ftp.connect(host=PRINTER_IP, port=990, timeout=5, source_address=None)
        ftp.login('bblp', ACCESS_CODE)
        ftp.prot_p()
        try:
            tldirlist = []
            tltndirlist = []
            ftp.cwd('/timelapse')
            ftp.retrlines('LIST', tldirlist.append)
            tldirlist = [parse_ftp_listing(line) for line in tldirlist if parse_ftp_listing(line)]
            ftp.cwd('/timelapse/thumbnail')
            ftp.retrlines('LIST', tltndirlist.append)
            tltndirlist = [parse_ftp_listing(line) for line in tltndirlist if parse_ftp_listing(line)]
            tldirlist_dict = {get_base_name(item['name']): item for item in tldirlist}
            tltndirlist_set = {get_base_name(item['name']) for item in tltndirlist}
            matching_files = [tldirlist_dict[base_name] for base_name in tldirlist_dict if base_name in tltndirlist_set]

            if not matching_files:
                print('No matching files found.')
                return

            matching_files.sort(key=lambda x: parse_date(x) or datetime.min, reverse=True)
            files_to_download = [matching_files[0]] if not args.all else matching_files

            total_size = sum(item["size"] for item in files_to_download)
            if args.all and len(files_to_download) > 1:
                total_pbar = tqdm(total=total_size, unit='B', unit_scale=True, desc='Total Progress')
            else:
                total_pbar = None

            for item in files_to_download:
                print(f'Processing: {item["name"]}')
                local_filename = os.path.join(out_dir, item["name"])
                file_size = item["size"]
                with open(local_filename, 'wb') as f:
                    with tqdm(total=file_size, unit='B', unit_scale=True, desc=f"Downloading {item['name']}") as pbar:
                        def callback(data):
                            f.write(data)
                            pbar.update(len(data))
                            if total_pbar:
                                total_pbar.update(len(data))
                        ftp.retrbinary(f'RETR /timelapse/{item["name"]}', callback)
                print(f'File downloaded: {local_filename}')
                # Always delete remote file in watch mode, or respect arg otherwise
                if args.watch or not args.do_not_delete:
                    ftp.delete(f'/timelapse/{item["name"]}')
                    print(f'Remote file deleted: /timelapse/{item["name"]}\n')
                else:
                    print(f'Remote file retained: /timelapse/{item["name"]}\n')
                # Optionally process with ffmpeg (default ON)
                if not args.no_make_streamable:
                    streamable_filename = os.path.splitext(local_filename)[0] + '_streamable.mp4'
                    if args.no_gpu:
                        ffmpeg_cmd = [
                            'ffmpeg', '-y', '-i', local_filename,
                            '-vf', 'scale=1920:1080',
                            '-c:v', 'libx265', '-preset', 'slow', '-b:v', '15M',
                            '-tag:v', 'hvc1', '-video_track_timescale', '90000',
                            streamable_filename
                        ]
                    else:
                        ffmpeg_cmd = [
                            'ffmpeg', '-y', '-hwaccel', 'cuda', '-i', local_filename,
                            '-vf', 'scale=1920:1080',
                            '-c:v', 'hevc_nvenc', '-preset', 'p7', '-tune', 'hq', '-b:v', '15M',
                            '-tag:v', 'hvc1', '-video_track_timescale', '90000',
                            streamable_filename
                        ]
                    print(f'Running ffmpeg to create streamable: {streamable_filename}')
                    try:
                        subprocess.run(ffmpeg_cmd, check=True)
                        print(f'Streamable file created: {streamable_filename}')
                        # Telegram upload if config present
                        caption = extract_datetime_from_filename(os.path.basename(local_filename))
                        tg_success = asyncio.run(try_telegram_upload(config, streamable_filename, caption=caption))
                        if tg_success and not args.keep_after_upload:
                            os.remove(streamable_filename)
                            print(f'Streamable file deleted after Telegram upload: {streamable_filename}')
                        # Delete original file if conversion succeeded
                        os.remove(local_filename)
                        print(f'Original file deleted: {local_filename}')
                    except subprocess.CalledProcessError as e:
                        print(f'ffmpeg failed for {local_filename}: {e}')
            if total_pbar:
                total_pbar.close()

        except all_errors as ex:
            print(ex)
        finally:
            ftp.quit()
            print('Disconnected. Enjoy =D')

    if args.watch:
        print('Entering watch mode. Checking for new files every 60 seconds...')
        while True:
            download_and_process()
            time.sleep(60)
    else:
        while True:
            try:
                download_and_process()
                break  # Exit loop if successful
            except Exception as e:
                print(f"Error occurred: {e}")
                print("Retrying in 60 seconds...")
                time.sleep(60)

if __name__ == "__main__":
    main()
