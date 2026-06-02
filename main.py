
import html
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional
import requests
from nicegui import app, ui

GLOBAL_STYLE = """
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
    body { 
        font-family: 'Plus Jakarta Sans', sans-serif; 
        background-color: #08090c; 
    }
    .premium-card { 
        transition: all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1);
        background: linear-gradient(145deg, #12141c, #0e1015);
    }
    .premium-card:hover {
        transform: translateY(-6px);
        box-shadow: 0 20px 40px rgba(139, 92, 246, 0.12), 0 1px 3px rgba(139, 92, 246, 0.2);
        border-color: #6d28d9 !important;
    }
    .skeleton-pulse { 
        animation: pulse 1.8s ease-in-out infinite; 
    }
    @keyframes pulse { 0%, 100% { opacity: .6; } 50% { opacity: .2; } }
    
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #08090c; }
    ::-webkit-scrollbar-thumb { background: #1f222f; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #2d3144; }
</style>
"""
ui.add_head_html(GLOBAL_STYLE)


class TrackCoverHunter:
    def __init__(self):
        self.api_url = "https://itunes.apple.com/search"
        self.items_per_page = 12
        
        self.current_query = ""
        self.all_results: List[Dict[str, str]] = []
        self.displayed_count = 0
        
        self.featured_tracks = [
            {"track": "Blinding Lights", "artist": "The Weeknd", "query": "The Weeknd Blinding Lights"},
            {"track": "Bohemian Rhapsody", "artist": "Queen", "query": "Queen Bohemian Rhapsody"},
            {"track": "Stay", "artist": "The Kid LAROI", "query": "The Kid LAROI Stay"},
            {"track": "Bad Guy", "artist": "Billie Eilish", "query": "Billie Eilish Bad Guy"},
            {"track": "As It Was", "artist": "Harry Styles", "query": "Harry Styles As It Was"},
            {"track": "Starboy", "artist": "The Weeknd", "query": "The Weeknd Starboy"},
            {"track": "Sweater Weather", "artist": "The Neighbourhood", "query": "The Neighbourhood Sweater Weather"},
            {"track": "Nightcall", "artist": "Kavinsky", "query": "Kavinsky Nightcall"}
        ]
        
        self.search_input: Optional[ui.input] = None
        self.grid_container: Optional[ui.column] = None
        self.skeleton_container: Optional[ui.row] = None
        self.load_more_btn: Optional[ui.button] = None
        
        self.build_ui()
        ui.timer(0.1, self.restore_session, once=True)

    @lru_cache(maxsize=128)
    def fetch_itunes_data(self, query: str) -> List[Dict[str, Any]]:
        try:
            params = {"term": query, "entity": "song", "limit": 48}
            response = requests.get(self.api_url, params=params, timeout=8)
            if response.status_code == 200:
                return response.json().get("results", [])
            ui.notify(f"Ошибка API: статус {response.status_code}", type="warning")
        except requests.RequestException:
            ui.notify("Ошибка сети: проверьте подключение", type="negative")
        return []

    def force_download(self, url: str, filename: str) -> None:
        """Скачивает файл как набор байт, предотвращая CORS-открытие в новой вкладке."""
        try:
            ui.notify("Подготовка файла...", type="info", position="bottom-right", duration=1)
            response = requests.get(url, timeout=15)
            if response.status_code == 200:
                # Передаем чистый контент в виде bytes напрямую в ui.download
                ui.download(response.content, filename=filename)
            else:
                ui.notify("Не удалось получить изображение с сервера", type="negative")
        except Exception as e:
            ui.notify(f"Ошибка при скачивании: {str(e)}", type="negative")

    def sanitize_filename(self, artist: str, track: str) -> str:
        filename = f"{artist} - {track}"
        filename = re.sub(r'[\\/*?:"<>|]', "", filename)
        return f"{filename.strip()}.jpg"

    def process_search(self, query: str, append_history: bool = True) -> None:
        self.current_query = query.strip()
        
        if not self.current_query:
            self.load_featured_gallery()
            return

        if append_history:
            app.storage.user['last_query'] = self.current_query

        self.toggle_loading(True)
        self.grid_container.clear()
        
        raw_items = self.fetch_itunes_data(self.current_query)
        self.all_results = []
        
        for item in raw_items:
            artwork_url = item.get("artworkUrl100", "")
            if not artwork_url:
                continue
            self.all_results.append({
                "track": item.get("trackName", "Unknown Track"),
                "artist": item.get("artistName", "Unknown Artist"),
                "preview": artwork_url.replace("100x100bb", "400x400bb"),
                "full": artwork_url.replace("100x100bb", "1400x1400bb")
            })

        self.toggle_loading(False)
        
        if not self.all_results:
            ui.notify("Обложки не найдены", type="info")
            self.load_more_btn.set_visibility(False)
            return

        self.displayed_count = 0
        self.render_next_page()

    def load_featured_gallery(self) -> None:
        self.grid_container.clear()
        self.all_results = []
        self.load_more_btn.set_visibility(False)
        self.toggle_loading(True)
        
        for seed in self.featured_tracks:
            items = self.fetch_itunes_data(seed["query"])
            if items:
                target = items[0]
                artwork = target.get("artworkUrl100", "")
                if artwork:
                    self.all_results.append({
                        "track": target.get("trackName", seed["track"]),
                        "artist": target.get("artistName", seed["artist"]),
                        "preview": artwork.replace("100x100bb", "400x400bb"),
                        "full": artwork.replace("100x100bb", "1400x1400bb")
                    })
        
        self.toggle_loading(False)
        self.displayed_count = len(self.all_results)
        self.render_grid_items(self.all_results)

    def render_next_page(self) -> None:
        start = self.displayed_count
        end = start + self.items_per_page
        slice_items = self.all_results[start:end]
        
        self.displayed_count = min(end, len(self.all_results))
        self.render_grid_items(slice_items)
        self.load_more_btn.set_visibility(self.displayed_count < len(self.all_results))

    def render_grid_items(self, items: List[Dict[str, str]]) -> None:
        with self.grid_container:
            with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"):
                for item in items:
                    filename = self.sanitize_filename(item["artist"], item["track"])
                    
                    with ui.card().classes("premium-card p-0 overflow-hidden rounded-2xl border border-zinc-800/60 flex flex-col justify-between shadow-lg"):
                        with ui.element("div").classes("w-full aspect-square overflow-hidden relative cursor-pointer") \
                                .on("click", lambda _, u=item["full"]: self.open_preview_modal(u)):
                            ui.image(item["preview"]).classes("w-full h-full object-cover")
                            with ui.element("div").classes("absolute inset-0 bg-black/60 opacity-0 hover:opacity-100 transition-all duration-300 flex items-center justify-center backdrop-blur-sm"):
                                ui.icon("zoom_in", size="36px").classes("text-white scale-90 hover:scale-110 transition-transform")

                        with ui.column().classes("p-5 w-full gap-1"):
                            ui.label(item["track"]).classes("font-bold text-zinc-100 truncate w-full text-base tracking-wide")
                            ui.label(item["artist"]).classes("text-xs font-medium text-zinc-400 truncate w-full mb-4")
                            
                            with ui.row().classes("w-full gap-2 items-center no-wrap"):
                                ui.button("Download", on_click=lambda _, u=item["full"], f=filename: self.force_download(u, f)) \
                                    .props("icon=file_download unelevated") \
                                    .classes("flex-grow rounded-xl bg-violet-600 hover:bg-violet-500 font-semibold text-white py-2 transition-all shadow-md shadow-violet-900/20 text-xs uppercase tracking-wider")
                                
                                with ui.button(on_click=lambda _, u=item["full"]: self.copy_link_to_clipboard(u)) \
                                        .props("icon=link unelevated dense") \
                                        .classes("rounded-xl bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300 h-9 w-9 min-w-9 transition-colors") \
                                        .style("padding: 0;"):
                                    ui.tooltip("Copy high-res link").classes("bg-zinc-900 text-zinc-200 text-xs")

    def open_preview_modal(self, url: str) -> None:
        with ui.dialog() as dialog, ui.card().classes("p-0 overflow-hidden rounded-3xl bg-[#0e1015] border border-zinc-800 max-w-2xl w-full shadow-2xl"):
            ui.image(url).classes("w-full h-auto")
        dialog.open()

    def copy_link_to_clipboard(self, url: str) -> None:
        ui.run_javascript(f"navigator.clipboard.writeText({repr(url)});")
        ui.notify("Ссылка скопирована в буфер!", type="positive", position="bottom-right")

    def clear_search(self) -> None:
        self.search_input.set_value("")
        if 'last_query' in app.storage.user:
            del app.storage.user['last_query']
        self.load_featured_gallery()

    def toggle_loading(self, active: bool) -> None:
        self.skeleton_container.set_visibility(active)

    def restore_session(self) -> None:
        try:
            saved_query = app.storage.user.get('last_query', '')
            if saved_query:
                self.search_input.set_value(saved_query)
                self.process_search(saved_query, append_history=False)
            else:
                self.load_featured_gallery()
        except RuntimeError:
            self.load_featured_gallery()

    def build_ui(self) -> None:
        with ui.column().classes("w-full min-h-screen items-center p-6 sm:p-12 bg-gradient-to-tr from-[#06070a] via-[#0a0b10] to-[#110f1a] text-zinc-100"):
            
            with ui.row().classes("w-full max-w-5xl justify-between items-center mb-16 border-b border-zinc-800/40 pb-6"):
                with ui.row().classes("items-center gap-3"):
                    ui.icon("album", size="36px").classes("text-violet-500 drop-shadow-[0_0_10px_rgba(139,92,246,0.5)]")
                    ui.label("TrackCoverHunter").classes("text-xl font-extrabold tracking-wider text-transparent bg-clip-text bg-gradient-to-r from-zinc-100 to-zinc-400")
                ui.label("PRODUCTION v1.1").classes("text-[10px] text-zinc-500 font-mono tracking-widest bg-zinc-900/60 px-2.5 py-1 rounded-md border border-zinc-800/50")

            with ui.row().classes("w-full max-w-xl bg-[#0f111a]/90 backdrop-blur-md rounded-2xl border border-zinc-800 p-2 items-center gap-2 mb-12 shadow-2xl focus-within:border-violet-500/50 transition-colors"):
                self.search_input = ui.input(placeholder="Поиск трека, альбома или артиста...") \
                    .props("borderless dense debounce=500") \
                    .classes("flex-grow text-zinc-100 px-3 text-sm bg-transparent placeholder-zinc-500")
                
                self.search_input.on("value-change", lambda e: self.process_search(e.value) if e.value else self.load_featured_gallery())
                self.search_input.on("keydown.enter", lambda: self.process_search(self.search_input.value))

                with ui.button(on_click=self.clear_search).props("icon=clear unelevated dense").classes("text-zinc-500 hover:text-zinc-300 bg-transparent h-9 w-9"):
                    ui.tooltip("Сбросить поиск")

                ui.button(on_click=lambda: self.process_search(self.search_input.value)) \
                    .props("icon=search unelevated") \
                    .classes("rounded-xl bg-violet-600 hover:bg-violet-500 text-white h-9 w-11 transition-all shadow-md shadow-violet-700/10")

            with ui.row().classes("w-full max-w-5xl justify-center mb-6") as self.skeleton_container:
                with ui.grid().classes("w-full grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-6"):
                    for _ in range(4):
                        with ui.card().classes("p-0 overflow-hidden rounded-2xl bg-[#11131c] border border-zinc-800/50 w-full aspect-[3/4] skeleton-pulse flex flex-col justify-between"):
                            ui.element("div").classes("w-full aspect-square bg-zinc-800/40")
                            with ui.column().classes("p-5 gap-3 w-full"):
                                ui.element("div").classes("h-4 bg-zinc-800/40 rounded w-3/4")
                                ui.element("div").classes("h-3 bg-zinc-800/40 rounded w-1/2")
            self.toggle_loading(False)

            self.grid_container = ui.column().classes("w-full max-w-5xl")

            with ui.row().classes("w-full justify-center mt-16 mb-8"):
                self.load_more_btn = ui.button("Загрузить еще обложки", on_click=self.render_next_page) \
                    .props("outline unelevated") \
                    .classes("text-xs font-bold px-8 py-2.5 rounded-xl border-zinc-800 hover:border-violet-500/50 text-zinc-300 hover:text-white transition-all bg-zinc-900/20 tracking-wider uppercase")
                self.load_more_btn.set_visibility(False)


app_instance = TrackCoverHunter()

ui.run(
    title="TrackCoverHunter", 
    port=8080, 
    reload=True, 
    storage_secret="HIGHLY_SECURE_PHRASE_FOR_APP_STORAGE_PROD_102"
)
