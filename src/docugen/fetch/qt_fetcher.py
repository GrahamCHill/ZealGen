import anyio
from PySide6.QtCore import QObject, Signal, Slot, Qt, QUrl, QTimer
from PySide6.QtWebEngineCore import QWebEnginePage
from PySide6.QtWidgets import QApplication
from .base import Fetcher, FetchResult

class QtFetchWorker(QObject):
    """
    A worker that must live on the main (GUI) thread to interact with QWebEnginePage.
    Communication is handled via signals to remain thread-safe.
    """
    # Signals to communicate with the worker from other threads
    do_fetch = Signal(str)
    # Signal to return the result (html, url)
    fetch_finished = Signal(str, str)

    def __init__(self):
        super().__init__()
        self._page = None
        # Connect the trigger signal to the handler
        self.do_fetch.connect(self._handle_fetch)

    @Slot(str)
    def _handle_fetch(self, url):
        if not self._page:
            self._page = QWebEnginePage()
        
        # Internal state to track the current fetch
        self._current_url = url
        self._last_html_len = 0
        self._stable_count = 0
        self._total_wait_time = 0
        
        def on_load_finished(ok):
            # Disconnect to avoid multiple calls if multiple loads happen
            self._page.loadFinished.disconnect(on_load_finished)
            if ok:
                # Wait a bit more for any JS to finish rendering content
                QTimer.singleShot(5000, self._start_scrolling)
            else:
                self.fetch_finished.emit("", self._current_url)
        
        self._page.loadFinished.connect(on_load_finished)
        self._page.load(QUrl(url))

    def _start_scrolling(self):
        # Scroll from top to bottom
        self._page.runJavaScript("""
            (async () => {
                await new Promise((resolve) => {
                    let totalHeight = 0;
                    let distance = 100;
                    let timer = setInterval(() => {
                        let scrollHeight = document.body.scrollHeight;
                        window.scrollBy(0, distance);
                        totalHeight += distance;

                        if(totalHeight >= scrollHeight){
                            clearInterval(timer);
                            resolve();
                        }
                    }, 100);
                });
                window.scrollTo(0, 0);
            })();
        """)
        # Start polling for content stability
        QTimer.singleShot(2000, self._poll_content) # Give it some time to start scrolling

    def _poll_content(self):
        self._page.toHtml(self._check_stability)

    def _check_stability(self, html):
        current_len = len(html)
        if current_len > 0 and current_len == self._last_html_len:
            self._stable_count += 1
        else:
            self._stable_count = 0
            self._last_html_len = current_len

        self._total_wait_time += 500
        
        # If stable for 3 checks (1.5s) or reached max timeout (10s)
        if (self._stable_count >= 3 and self._total_wait_time >= 2000) or self._total_wait_time >= 10000:
            self.fetch_finished.emit(html, self._current_url)
        else:
            QTimer.singleShot(500, self._poll_content)

    def _on_html(self, html):
        self.fetch_finished.emit(html, self._current_url)

class QtFetcher(Fetcher):
    def __init__(self):
        self.worker = QtFetchWorker()
        # Move worker to the main GUI thread
        main_thread = QApplication.instance().thread()
        self.worker.moveToThread(main_thread)
    
    async def fetch(self, url: str) -> FetchResult:
        event = anyio.Event()
        result = {"html": None}
        
        from anyio.from_thread import start_blocking_portal
        
        with start_blocking_portal() as portal:
            # This callback will be called in the main thread by Qt
            def on_finished(html, finished_url):
                # Only process if it matches the URL we're waiting for
                if finished_url == url:
                    result["html"] = html
                    # anyio.Event.set() is NOT thread-safe, so we use the portal
                    portal.call(event.set)
                
            self.worker.fetch_finished.connect(on_finished)
            
            try:
                # Emit the signal to start the fetch on the main thread
                self.worker.do_fetch.emit(url)
                
                # Wait for the event to be set from the main thread
                await event.wait()
                
                if not result["html"]:
                    raise Exception(f"Failed to fetch {url} using QtWebEngine (load error or empty result)")
                    
                return FetchResult(url, result["html"])
            finally:
                # Always disconnect to clean up
                self.worker.fetch_finished.disconnect(on_finished)
