import streamlit as st
import yt_dlp
import os
import re
import tempfile


# --- HELPER FUNCTIONS ---
def sanitize_filename(filename: str) -> str:
    """Removes invalid characters from a filename."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)


def sanitize_for_display(text: str) -> str:
    """Removes ANSI escape codes for clean display in Streamlit."""
    if not isinstance(text, str):
        return ""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def get_video_info(url: str) -> dict | None:
    """Fetches full video metadata."""
    ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(url, download=False)
    except yt_dlp.utils.DownloadError:
        return None


# --- CORRECTED QUALITY EXTRACTION ---
def extract_available_qualities(info_dict: dict) -> list[str]:
    """
    Parses the info dict to find available MP4 video resolutions,
    ensuring correct 'p' notation (e.g., 1080p from height).
    """
    qualities = set()
    for f in info_dict.get('formats', []):
        # We ensure 'height' is present and it's a video stream
        if f.get('vcodec') != 'none' and f.get('ext') == 'mp4' and isinstance(f.get('height'), int):
            qualities.add(f.get('height'))

    if not qualities:
        return ['720p', '360p']  # Fallback

    # Create the 'p' notation and sort numerically from highest to lowest
    sorted_qualities = sorted(list(qualities), reverse=True)
    return [f"{q}p" for q in sorted_qualities]


def progress_hook(d, status_box, progress_state):
    """Updates the status box with the current download progress and step."""
    if d['status'] == 'downloading':
        percent_str = sanitize_for_display(d.get('_percent_str', '0.0%'))
        speed_str = sanitize_for_display(d.get('_speed_str', 'N/A'))
        eta_str = sanitize_for_display(d.get('_eta_str', 'N/A'))
        step_info = f"Étape {progress_state['step']}/{progress_state['total_steps']}:"
        status_box.update(label=f"{step_info} Téléchargement... {percent_str} ({speed_str} - ETA: {eta_str})")
    elif d['status'] == 'finished':
        progress_state['step'] += 1
        step_info = f"Étape {progress_state['step'] - 1}/{progress_state['total_steps']}:"
        status_box.update(label=f"{step_info} Téléchargement terminé. Lancement de la conversion...")


def handle_download(url: str, title: str, format_type: str, quality_setting: str):
    """Handles the download with a step counter and temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        safe_title = sanitize_filename(title)
        output_template = os.path.join(temp_dir, f"{safe_title}.%(ext)s")

        progress_state = {'step': 1, 'total_steps': 1}
        format_string = ""

        if format_type == 'mp3':
            format_string = 'bestaudio/best'
            postprocessors = [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': quality_setting}]
        else:
            height = quality_setting[:-1]
            format_string = f'bestvideo[ext=mp4][height<={height}]+bestaudio[ext=m4a]/best[ext=mp4][height<={height}]'
            postprocessors = []
            if '+' in format_string:
                progress_state['total_steps'] = 2

        ydl_opts = {
            'outtmpl': output_template,
            'quiet': True,
            'no_warnings': True,
            'format': format_string,
            'postprocessors': postprocessors,
            'progress_hooks': [lambda d: progress_hook(d, st.session_state.status_box, progress_state)],
        }

        actual_filepath = None
        try:
            with st.status("Démarrage...", expanded=True) as status:
                st.session_state.status_box = status

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    status.update(label=f"Étape 1/{progress_state['total_steps']}: Initialisation...")
                    st.write("⚙️ Lancement du téléchargement...")
                    info_dict = ydl.extract_info(url, download=True)
                    actual_filepath = info_dict.get('requested_downloads', [{}])[0].get('filepath')

                if not actual_filepath or not os.path.exists(actual_filepath):
                    status.update(label="Échec du téléchargement", state="error", expanded=False)
                    st.error("Impossible de récupérer le fichier final.")
                    return

                st.write(f"✅ Fichier sauvegardé : {os.path.basename(actual_filepath)}")
                status.update(label="Téléchargement terminé !", state="complete", expanded=False)

            with open(actual_filepath, 'rb') as f:
                file_bytes = f.read()

            st.download_button(
                label=f"📥 Télécharger {os.path.basename(actual_filepath)}",
                data=file_bytes,
                file_name=os.path.basename(actual_filepath),
                mime="audio/mpeg" if format_type == "mp3" else "video/mp4",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Une erreur inattendue est survenue : {e}")
        finally:
            if 'status_box' in st.session_state:
                del st.session_state.status_box


def main():
    st.set_page_config(page_title="YT Downloader", page_icon="🚀", layout="centered")

    for key in ['video_info', 'available_qualities', 'last_url', 'status_box']:
        if key not in st.session_state:
            st.session_state[key] = None if key != 'available_qualities' else []

    st.title("🚀 Open Source YouTube Downloader")

    with st.container(border=True):
        url = st.text_input("🔗 Entrez l'URL YouTube", placeholder="https://www.youtube.com/watch?v=...")
        if url and url != st.session_state.last_url:
            st.session_state.video_info = None
            st.session_state.available_qualities = []
            st.session_state.last_url = url

        if st.button("Analyser la vidéo", use_container_width=True, type="primary"):
            if url:
                with st.spinner("Analyse en cours..."):
                    info = get_video_info(url)
                    if info:
                        st.session_state.video_info = info
                        st.session_state.available_qualities = extract_available_qualities(info)
                    else:
                        st.session_state.video_info = None
                        st.error("Vidéo introuvable. Vérifiez l'URL.")
            else:
                st.warning("Veuillez entrer une URL.")

    if st.session_state.video_info:
        with st.container(border=True):
            info = st.session_state.video_info
            title = info.get('title', 'Untitled')
            thumbnail_url = info.get('thumbnail')

            col1, col2 = st.columns([1, 2], gap="large")
            with col1:
                if thumbnail_url:
                    st.image(thumbnail_url, use_container_width=True)
            with col2:
                st.subheader(title)
                format_choice = st.radio(
                    "**1. Choisissez le format**", ('🎶 MP3 (Audio)', '🎬 MP4 (Vidéo)'), horizontal=True
                )
                format_type = 'mp3' if 'MP3' in format_choice else 'mp4'

                st.write("**2. Choisissez la qualité**")
                quality_setting = None

                if format_type == 'mp3':
                    mp3_bitrate = st.selectbox(
                        "Débit Audio (plus bas = plus rapide)",
                        options=['128', '192', '256', '320'], index=0, format_func=lambda x: f"{x} kbps"
                    )
                    quality_setting = mp3_bitrate
                else:
                    mp4_resolution = st.selectbox(
                        "Résolution Vidéo (plus haut = plus lent)",
                        options=st.session_state.available_qualities
                    )
                    quality_setting = mp4_resolution

                if st.button(f"Lancer le téléchargement", use_container_width=True):
                    if quality_setting:
                        handle_download(url, title, format_type, quality_setting)


if __name__ == "__main__":
    main()