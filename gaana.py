import os
import sys
import requests
import re
import base64
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad
import yt_dlp
from mutagen.mp4 import MP4, MP4Cover
from config import CONFIG


class GaanaDL:
    REGEX = re.compile(
        r"https://gaana\.com/(song|album|playlist|podcast)/(.+)")

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        # Characters that are invalid on Windows/Unix filesystems
        invalid_chars = r'[<>:"/\\|?*\x00-\x1f]'
        sanitized = re.sub(invalid_chars, '', filename)
        sanitized = sanitized.rstrip('. ')
        return sanitized

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'Accept': 'application/json, text/plain, */*',
            'Accept-Language': 'en-GB,en;q=0.9,en-US;q=0.8,it-IT;q=0.7,it;q=0.6',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'application/x-www-form-urlencoded',
            'DNT': '1',
            'Origin': 'https://gaana.com',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36 Edg/143.0.0.0',
            'sec-ch-ua': '"Microsoft Edge";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"Windows"',
        })

    def metadata_handler(self, identifier, metadata_type):
        return self.session.post('https://gaana.com/apiv2', params={
            'seokey': identifier,
            'type': metadata_type,
        }).json()

    def album_folder_handler(self, album_data):
        album_metadata = {
            'album_name': album_data['album']['title'],
            'artist_name': album_data['album']['artist'][0]['name'],
            "release_year": album_data['release_year'],
            'track_count': album_data['album']['trackcount'],
            'language': album_data['album']['language'],
            'records': album_data['album']['recordlevel'],
        }

        sanitized_metadata = {k: self.sanitize_filename(
            str(v)) for k, v in album_metadata.items()}
        album_metadata['album_path'] = os.path.join(
            CONFIG["download_path"], CONFIG["album_folder_format"].format(**sanitized_metadata))
        os.makedirs(album_metadata['album_path'], exist_ok=True)
        return album_metadata

    def playlist_folder_handler(self, playlist_data):
        playlist_metadata = {
            'album_name': playlist_data['playlist']['title'],
            'artist_name': playlist_data['playlist']['createdby'],
            'track_count': playlist_data['playlist']['trackcount'],
        }

        sanitized_metadata = {k: self.sanitize_filename(
            str(v)) for k, v in playlist_metadata.items()}
        playlist_metadata['album_path'] = os.path.join(
            CONFIG["download_path"], "{artist_name} - {album_name}".format(**sanitized_metadata))
        os.makedirs(playlist_metadata['album_path'], exist_ok=True)
        return playlist_metadata

    def download_handler(self, content_type, identifier):
        if content_type == "song":
            metadata_type = 'songDetail'
            data = self.metadata_handler(identifier, metadata_type)
            self.download_song(data['tracks'][0])
        elif content_type in ["album", "podcast"]:
            metadata_type = 'albumDetail'
            data = self.metadata_handler(identifier, metadata_type)
            self.download_album(data)
        elif content_type == "playlist":
            metadata_type = 'playlistDetail'
            data = self.metadata_handler(identifier, metadata_type)
            self.download_playlist(data)

    def download_album(self, album_data):
        album_metadata = self.album_folder_handler(album_data)

        print(
            """Album Info:
            Name    : {album_name}
            Artist  : {artist_name}
            Year    : {release_year}
            Tracks  : {track_count}
            Language: {language}
            Records : {records}
            """.format(**album_metadata)
        )

        for i, track in enumerate(album_data['tracks']):
            track_data = track
            track_data["track_number"] = str(i + 1).zfill(2)
            track_data['track_count'] = album_metadata['track_count']
            track_data['album_path'] = album_metadata['album_path']
            track_data['label_name'] = album_metadata.get('records', '')
            self.download_song(track_data, album_data_embedded=True)

    def download_playlist(self, playlist_data):
        playlist_metadata = self.playlist_folder_handler(playlist_data)
        print(
            """Playlist Info:
            Name    : {album_name}
            Created By : {artist_name}
            Tracks  : {track_count}
            """.format(**playlist_metadata)
        )
        for i, track in enumerate(playlist_data['tracks']):
            track_data = track
            track_data["track_number"] = str(i + 1).zfill(2)
            track_data['track_count'] = playlist_metadata['track_count']
            track_data['album_path'] = playlist_metadata['album_path']
            self.download_song(
                track_data, album_data_embedded=True, is_playlist=True)

    def download_song(self, data, album_data_embedded: bool = False, is_playlist: bool = False):
        if not album_data_embedded:
            album_data = self.metadata_handler(
                data['albumseokey'], 'albumDetail')
            album_metadata = self.album_folder_handler(album_data)
            for i, track in enumerate(album_data['tracks']):
                if track['track_id'] == data['track_id']:
                    data["track_number"] = str(i + 1).zfill(2)
                    break
            data["track_count"] = album_metadata['track_count']
            data['album_path'] = album_metadata['album_path']

        song_metadata = {
            'track_title': data['track_title'],
            'artist_name': data['artist'][0]['name'],
            'album_name': data['album_title']
        }

        print("""Song Info:
        Title : {track_title}
        Artist: {artist_name}
        Album : {album_name}
        """.format(**song_metadata))

        print(f"Downloading: {data['track_number']} {data['track_title']}...")

        artwork_path = os.path.join(data['album_path'], 'cover.jpg')
        artwork_url = data['artwork'].replace(
            'size_s', f"size_{CONFIG['artwork_quality']}")

        # Download if cover.jpg does not exists
        if not os.path.exists(artwork_path):
            artwork_response = self.session.get(artwork_url)
            with open(artwork_path, 'wb') as f:
                f.write(artwork_response.content)

        track_file_name = self.sanitize_filename(
            CONFIG["track_file_format"].format(**data))
        track_file_path = os.path.join(data['album_path'], track_file_name)

        stream_url = self.decrypt_stream_path(data['urls']['auto']['message']).replace(
            'f.mp4', f'{CONFIG["audio_quality"]}.mp4')

        if os.path.exists(track_file_path):
            print(f"File already exists: {track_file_path}")
            return

        self.download_stream(stream_url, track_file_path)
        self.tag_track(track_file_path, data, artwork_path)

        if is_playlist:
            os.remove(artwork_path)

    def download_stream(self, stream_url, file_path):
        ydl_opts = {
            'format': 'best',
            'outtmpl': file_path,
            'quiet': True,
            'no_warnings': True,
            'noprogress': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([stream_url])
        except Exception as e:
            print(f"Error: {e}")

    @staticmethod
    def decrypt_stream_path(encrypted_path) -> str:
        AES_KEY = b"".join(w.to_bytes(4, byteorder="big", signed=True)
                           for w in [1735995764, 593641578, 1814585892, 2004118885])
        offset = int(encrypted_path[0])
        iv = encrypted_path[offset: offset + 16].encode("utf-8")
        ciphertext = base64.b64decode(encrypted_path[offset + 16:])
        cipher = AES.new(AES_KEY, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ciphertext), AES.block_size).decode("utf-8")

    @staticmethod
    def tag_track(file_path, metadata, artwork_path):
        try:
            audio = MP4(file_path)
            audio.clear()

            audio["\xa9nam"] = metadata.get("track_title", "")  # Title
            audio["\xa9alb"] = metadata.get("album_title", "")  # Album

            # Artist(s)
            if metadata.get("artist"):
                artists = [artist["name"] for artist in metadata["artist"]]
                audio["\xa9ART"] = artists[0] if len(artists) == 1 else artists
                audio["aART"] = artists[0]  # Album Artist

            # Genre(s)
            if metadata.get("gener"):  # Note: typo in JSON key
                genres = [genre["name"] for genre in metadata["gener"]]
                audio["\xa9gen"] = genres[0] if len(genres) == 1 else genres

            if metadata.get("release_date"):
                audio["\xa9day"] = metadata["release_date"]

            if metadata.get("isrc"):
                audio["----:com.apple.iTunes:ISRC"] = metadata["isrc"].encode(
                    'utf-8')

            if metadata.get("language"):
                audio["----:com.apple.iTunes:LANGUAGE"] = metadata["language"].encode(
                    'utf-8')

            if metadata.get("label_name"):
                audio["cprt"] = metadata["label_name"]

            if metadata.get("track_number"):
                audio["trkn"] = [
                    (int(metadata["track_number"]), int(metadata.get("track_count", 0)))]

            if "parental_warning" in metadata:
                audio["rtng"] = [1 if metadata["parental_warning"] else 2]

            audio['stik'] = [1]  # Music

            # Loudness metadata (ReplayGain/iTunes Sound Check equivalent)
            if metadata.get("loudness"):
                loudness = metadata["loudness"]
                audio["----:com.apple.iTunes:REPLAYGAIN_TRACK_GAIN"] = f"{loudness.get('integrated', '')}".encode(
                    'utf-8')
                audio["----:com.apple.iTunes:REPLAYGAIN_TRACK_PEAK"] = f"{loudness.get('truePeak', '')}".encode(
                    'utf-8')
                audio["----:com.apple.iTunes:REPLAYGAIN_TRACK_RANGE"] = f"{loudness.get('lra', '')}".encode(
                    'utf-8')

            try:
                with open(artwork_path, 'rb') as f:
                    artwork_data = f.read()
                    audio["covr"] = [
                        MP4Cover(artwork_data, imageformat=MP4Cover.FORMAT_JPEG)]
            except Exception as e:
                print(f"Failed to embed artwork: {e}")

            # audio["\xa9cmt"] = "Gaana-dl"
            audio.save()

        except Exception as e:
            print(f"Error tagging file: {e}")
            raise


LOGO = "  /$$$$$$                                                        /$$ /$$\r\n /$$__  $$                                                      | $$| $$\r\n| $$  \\__/  /$$$$$$   /$$$$$$  /$$$$$$$   /$$$$$$           /$$$$$$$| $$\r\n| $$ /$$$$ |____  $$ |____  $$| $$__  $$ |____  $$ /$$$$$$ /$$__  $$| $$\r\n| $$|_  $$  /$$$$$$$  /$$$$$$$| $$  \\ $$  /$$$$$$$|______/| $$  | $$| $$\r\n| $$  \\ $$ /$$__  $$ /$$__  $$| $$  | $$ /$$__  $$        | $$  | $$| $$\r\n|  $$$$$$/|  $$$$$$$|  $$$$$$$| $$  | $$|  $$$$$$$        |  $$$$$$$| $$\r\n \\______/  \\_______/ \\_______/|__/  |__/ \\_______/         \\_______/|__/\n\n"

if __name__ == "__main__":
    print(LOGO)
    urls_list = sys.argv[1:]
    gaana_dl = GaanaDL()
    for url in urls_list:
        result = GaanaDL.REGEX.match(url)
        if not result:
            print(f"Invalid URL: {url}")
            continue
        content_type, identifier = result.groups()
        gaana_dl.download_handler(content_type, identifier)
