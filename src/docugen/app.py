import sys
import anyio
import os
import platform
import subprocess
import plistlib
from urllib.parse import urlparse
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QFileDialog, QCheckBox,
    QLabel, QTextEdit, QMessageBox, QProgressBar, QDialog,
    QListWidgetItem, QInputDialog, QComboBox, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView, QTabWidget
)
from PySide6.QtCore import Qt, QThread, Signal, QStandardPaths
from .core import generate, scan, DEFAULT_MAX_PAGES
from .utils.url import normalize_url, clean_domain

class ScanWorker(QThread):
    finished = Signal(list)
    error = Signal(str)
    log = Signal(str)
    verbose_log = Signal(str)
    progress = Signal(int, int)

    def __init__(self, urls, js, fetcher_type="playwright", verbose=False):
        super().__init__()
        self.urls = urls
        self.js = js
        self.fetcher_type = fetcher_type
        self.verbose = verbose
        self.cancel_event = None

    def stop(self):
        if self.cancel_event:
            self.cancel_event.set()

    async def _run_scan(self):
        self.cancel_event = anyio.Event()
        
        def report_progress(current, total):
            self.progress.emit(current, total)

        def log_wrapper(message, verbose_only=False):
            if verbose_only:
                self.verbose_log.emit(message)
            else:
                self.log.emit(message)

        discovered = await scan(self.urls, self.js, DEFAULT_MAX_PAGES, report_progress, self.fetcher_type, log_wrapper, self.verbose, self.cancel_event)
        return discovered

    def run(self):
        try:
            discovered = anyio.run(self._run_scan)
            self.finished.emit(discovered)
        except Exception as e:
            self.error.emit(str(e))

class MultiWorker(QThread):
    finished = Signal()
    error = Signal(str)
    log = Signal(str)
    verbose_log = Signal(str)
    progress = Signal(int, int)

    def __init__(self, docsets_to_generate, output_base, js, fetcher_type="playwright", verbose=False, force=False):
        super().__init__()
        self.docsets_to_generate = docsets_to_generate
        self.output_base = output_base
        self.js = js
        self.fetcher_type = fetcher_type
        self.verbose = verbose
        self.force = force
        self.cancel_event = None

    def stop(self):
        if self.cancel_event:
            self.cancel_event.set()

    async def _run_generate(self):
        self.cancel_event = anyio.Event()
        total_docsets = len(self.docsets_to_generate)
        for i, (name, urls, allowed_urls) in enumerate(self.docsets_to_generate):
            if self.cancel_event.is_set():
                break
            
            self.log.emit(f"Generating docset: {name} ({i+1}/{total_docsets})")
            
            docset_filename = name if name.endswith(".docset") else f"{name}.docset"
            output_path = os.path.join(self.output_base, docset_filename)
            
            def report_progress(current, total):
                self.progress.emit(current, total)

            def log_wrapper(message, verbose_only=False):
                if verbose_only:
                    self.verbose_log.emit(message)
                else:
                    self.log.emit(message)

            await generate(urls, output_path, self.js, DEFAULT_MAX_PAGES, report_progress, allowed_urls, self.fetcher_type, log_wrapper, self.verbose, self.force, self.cancel_event)

    def run(self):
        try:
            anyio.run(self._run_generate)
            self.finished.emit()
        except Exception as e:
            self.error.emit(str(e))

class URLSelectionDialog(QDialog):
    def __init__(self, urls, initial_urls, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select URLs to Include")
        self.setMinimumSize(700, 500)
        # Normalize initial URLs to avoid matching issues
        self.initial_urls = {normalize_url(u) for u in initial_urls}
        # Parse initial URLs to extract domains for partitioning
        self.initial_domains = {urlparse(u).netloc.lower().replace("www.", "") for u in initial_urls}
        
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(QLabel("Review the URLs to be included in the docset:"))

        lists_layout = QHBoxLayout()
        
        # Left side: Primary Domain URLs (Required + Subpages)
        related_layout = QVBoxLayout()
        related_layout.addWidget(QLabel("Primary Domain URLs (Mandatory marked with *):"))
        self.related_list = QListWidget()
        lists_layout.addLayout(related_layout)
        related_layout.addWidget(self.related_list)
        
        # Right side: Other URLs (Subdomains/External)
        other_layout = QVBoxLayout()
        other_layout.addWidget(QLabel("Other Discovered Links:"))
        self.other_tree = QTreeWidget()
        self.other_tree.setHeaderHidden(True)
        self.other_tree.itemChanged.connect(self.on_item_changed)
        other_layout.addWidget(self.other_tree)
        lists_layout.addLayout(other_layout)
        
        main_layout.addLayout(lists_layout)

        # Group other URLs by domain
        other_urls_by_domain = {}
        
        for url in urls:
            normalized = normalize_url(url)
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace("www.", "")
            
            # If the URL's domain matches any of the initial domains, it goes to the left
            if domain in self.initial_domains:
                item = QListWidgetItem(url)
                if normalized in self.initial_urls:
                    # Mandatory: Original input URLs
                    item.setText(f"{url} *")
                    item.setData(Qt.UserRole, True) # Mark as mandatory
                    self.related_list.addItem(item)
                else:
                    # Optional subpage on the same domain
                    item.setCheckState(Qt.Checked)
                    item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                    item.setData(Qt.UserRole, False)
                    self.related_list.addItem(item)
            else:
                # Other domains go to the right tree
                if domain not in other_urls_by_domain:
                    other_urls_by_domain[domain] = []
                other_urls_by_domain[domain].append(url)

        # Populate the other_tree
        for domain in sorted(other_urls_by_domain.keys()):
            domain_item = QTreeWidgetItem(self.other_tree)
            domain_item.setText(0, domain)
            domain_item.setCheckState(0, Qt.Unchecked)
            domain_item.setFlags(domain_item.flags() | Qt.ItemIsAutoTristate | Qt.ItemIsUserCheckable)
            
            for url in sorted(other_urls_by_domain[domain]):
                url_item = QTreeWidgetItem(domain_item)
                url_item.setText(0, url)
                url_item.setCheckState(0, Qt.Unchecked)
                url_item.setFlags(url_item.flags() | Qt.ItemIsUserCheckable)

        btns = QHBoxLayout()
        select_all = QPushButton("Select All Optional")
        select_all.clicked.connect(self.select_all_optional)
        btns.addWidget(select_all)
        
        deselect_all = QPushButton("Deselect All Optional")
        deselect_all.clicked.connect(self.deselect_all_optional)
        btns.addWidget(deselect_all)
        
        main_layout.addLayout(btns)

        ok_btn = QPushButton("Generate")
        ok_btn.clicked.connect(self.accept)
        main_layout.addWidget(ok_btn)

    def on_item_changed(self, item, column):
        """Handle parent/child checkbox synchronization."""
        self.other_tree.blockSignals(True)
        state = item.checkState(column)
        
        # If a parent is changed, update all children
        if item.childCount() > 0:
            for i in range(item.childCount()):
                item.child(i).setCheckState(column, state)
        
        # Qt.ItemIsAutoTristate handles parent update when children change 
        # but we might need to ensure it's set correctly.
        
        self.other_tree.blockSignals(False)

    def select_all_optional(self):
        # Select all in the other tree (right window)
        for i in range(self.other_tree.topLevelItemCount()):
            item = self.other_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Checked)
            for j in range(item.childCount()):
                item.child(j).setCheckState(0, Qt.Checked)

    def deselect_all_optional(self):
        # Deselect all in the other tree (right window)
        for i in range(self.other_tree.topLevelItemCount()):
            item = self.other_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)
            for j in range(item.childCount()):
                item.child(j).setCheckState(0, Qt.Unchecked)

    def get_selected_urls(self):
        selected = []
        roots = []
        # Process related_list
        for i in range(self.related_list.count()):
            item = self.related_list.item(i)
            is_mandatory = item.data(Qt.UserRole)
            
            if is_mandatory:
                # Strip the mandatory marker if present
                text = item.text()
                if text.endswith(" *"):
                    text = text[:-2]
                selected.append(text)
                roots.append(text)
            elif item.checkState() == Qt.Checked:
                selected.append(item.text())
        
        # Process other_tree (only children are actual URLs)
        for i in range(self.other_tree.topLevelItemCount()):
            parent = self.other_tree.topLevelItem(i)
            # If the domain (parent) is checked/partially checked, we might want to treat 
            # some of its children as new roots if they are "top-level" enough.
            # For now, let's just collect all selected URLs.
            
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.Checked:
                    url = child.text(0)
                    selected.append(url)
                    # If this URL was explicitly found as a different domain, it's likely a root
                    # of an optional domain. 
                    # We add it to roots if it's the first one for this domain or shorter than existing one.
                    # Actually, the user might want multiple roots on the same domain if they are in different paths.
                    # But for now, one per domain is a good start.
                    roots.append(url)
                    
        return selected, roots

class DocsetEditWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.docset_path = None
        self.plist_path = None
        self.documents_path = None

        layout = QVBoxLayout(self)

        # Docset selection
        load_layout = QHBoxLayout()
        self.path_input = QLineEdit()
        self.path_input.setPlaceholderText("Select a .docset folder...")
        self.path_input.setReadOnly(True)
        load_layout.addWidget(self.path_input)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_docset)
        load_layout.addWidget(browse_btn)
        layout.addLayout(load_layout)

        # Current frontpage
        self.current_fp_label = QLabel("Current Frontpage: None")
        layout.addWidget(self.current_fp_label)

        # Filter
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        self.filter_input = QLineEdit()
        self.filter_input.textChanged.connect(self.filter_list)
        filter_layout.addWidget(self.filter_input)
        layout.addLayout(filter_layout)

        # File list
        layout.addWidget(QLabel("Select New Frontpage:"))
        self.file_list = QListWidget()
        layout.addWidget(self.file_list)

        # Save button
        self.save_btn = QPushButton("Update Info.plist")
        self.save_btn.clicked.connect(self.save_changes)
        self.save_btn.setEnabled(False)
        layout.addWidget(self.save_btn)

    def browse_docset(self):
        if platform.system() == "Darwin":
            # On macOS, .docset is a package/bundle. getOpenFileName can select it.
            path, _ = QFileDialog.getOpenFileName(self, "Select Docset", "", "Docset (*.docset)")
        else:
            path = QFileDialog.getExistingDirectory(self, "Select Docset Folder", "", QFileDialog.ShowDirsOnly)
        
        if path:
            if not path.endswith(".docset"):
                QMessageBox.warning(self, "Invalid Folder", "Please select a folder ending in .docset")
                return
            self.load_docset(path)

    def load_docset(self, path):
        self.docset_path = path
        self.plist_path = os.path.join(path, "Contents", "Info.plist")
        self.documents_path = os.path.join(path, "Contents", "Resources", "Documents")

        if not os.path.exists(self.plist_path):
            QMessageBox.critical(self, "Error", f"Could not find Info.plist at {self.plist_path}")
            return

        if not os.path.exists(self.documents_path):
            QMessageBox.critical(self, "Error", f"Could not find Documents folder at {self.documents_path}")
            return

        self.path_input.setText(path)
        
        try:
            with open(self.plist_path, "rb") as f:
                plist = plistlib.load(f)
                current_fp = plist.get("dashIndexFilePath", "")
                self.current_fp_label.setText(f"Current Frontpage: {current_fp if current_fp else 'Not set'}")
                self.refresh_file_list(current_fp)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to read Info.plist: {e}")
            return

        self.save_btn.setEnabled(True)

    def refresh_file_list(self, current_fp=None):
        self.file_list.clear()
        if not self.documents_path:
            return

        html_files = []
        for root, dirs, files in os.walk(self.documents_path):
            for file in files:
                if file.endswith(".html") or file.endswith(".htm"):
                    rel_path = os.path.relpath(os.path.join(root, file), self.documents_path)
                    html_files.append(rel_path)
        
        html_files.sort()
        self.file_list.addItems(html_files)

        if current_fp:
            items = self.file_list.findItems(current_fp, Qt.MatchExactly)
            if items:
                items[0].setSelected(True)
                self.file_list.scrollToItem(items[0])

    def filter_list(self, text):
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())

    def save_changes(self):
        selected = self.file_list.selectedItems()
        if not selected:
            QMessageBox.warning(self, "No Selection", "Please select a file from the list.")
            return

        new_fp = selected[0].text()
        
        try:
            with open(self.plist_path, "rb") as f:
                plist = plistlib.load(f)
            
            plist["dashIndexFilePath"] = new_fp
            
            with open(self.plist_path, "wb") as f:
                plistlib.dump(plist, f)
            
            self.current_fp_label.setText(f"Current Frontpage: {new_fp}")
            QMessageBox.information(self, "Success", f"Updated Info.plist with frontpage: {new_fp}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to update Info.plist: {e}")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DocuGen")
        self.setMinimumSize(600, 400)

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        # Tab 1: Generator
        generator_widget = QWidget()
        self.tabs.addTab(generator_widget, "Generator")
        layout = QVBoxLayout(generator_widget)

        # Tab 2: Edit Docset
        self.edit_widget = DocsetEditWidget()
        self.tabs.addTab(self.edit_widget, "Edit Docset")

        # URL Table (rest of the original UI goes into layout)
        layout.addWidget(QLabel("URLs and Docset Names:"))
        self.url_table = QTableWidget(0, 2)
        self.url_table.setHorizontalHeaderLabels(["URL", "Docset Name"])
        self.url_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.url_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        layout.addWidget(self.url_table)

        url_input_layout = QHBoxLayout()
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter documentation URL...")
        self.url_input.returnPressed.connect(self.add_url)
        url_input_layout.addWidget(self.url_input)
        
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self.add_url)
        url_input_layout.addWidget(add_btn)
        
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self.remove_url)
        url_input_layout.addWidget(remove_btn)
        layout.addLayout(url_input_layout)

        # Output directory
        layout.addWidget(QLabel("Output Base Directory:"))
        out_layout = QHBoxLayout()
        self.out_input = QLineEdit()
        out_layout.addWidget(self.out_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_output)
        out_layout.addWidget(browse_btn)
        layout.addLayout(out_layout)

        # Options
        options_layout = QHBoxLayout()
        self.js_checkbox = QCheckBox("Enable JavaScript", checked=True)
        options_layout.addWidget(self.js_checkbox)

        self.ignore_optional_checkbox = QCheckBox("Ignore Optional (Auto-generate)", checked=False)
        options_layout.addWidget(self.ignore_optional_checkbox)

        self.force_checkbox = QCheckBox("Force Build", checked=False)
        options_layout.addWidget(self.force_checkbox)
        
        options_layout.addWidget(QLabel("JS Engine:"))
        self.js_engine_combo = QComboBox()
        self.js_engine_combo.addItems(["playwright", "qt"])
        options_layout.addWidget(self.js_engine_combo)
        layout.addLayout(options_layout)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Logs
        layout.addWidget(QLabel("Logs:"))
        self.log_tabs = QTabWidget()
        
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_tabs.addTab(self.log_output, "General")
        
        self.verbose_log_output = QTextEdit()
        self.verbose_log_output.setReadOnly(True)
        self.log_tabs.addTab(self.verbose_log_output, "Verbose")
        
        layout.addWidget(self.log_tabs)

        # Generate button
        self.generate_btn = QPushButton("Generate Docset")
        self.generate_btn.clicked.connect(self.start_generation)
        layout.addWidget(self.generate_btn)

        # Stop button
        self.stop_btn = QPushButton("Stop Processing")
        self.stop_btn.clicked.connect(self.stop_processing)
        self.stop_btn.setEnabled(False)
        layout.addWidget(self.stop_btn)

        # Open Zeal Folder button
        self.open_zeal_btn = QPushButton("Open Zeal Docsets Folder")
        self.open_zeal_btn.clicked.connect(self.open_zeal_folder)
        layout.addWidget(self.open_zeal_btn)

    def open_zeal_folder(self):
        system = platform.system()
        path = None
        
        if system == "Windows":
            path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Zeal", "Zeal", "docsets")
        elif system == "Darwin":  # macOS
            path = os.path.expanduser("~/Library/Application Support/Zeal/Zeal/docsets")
        elif system == "Linux":
            path = os.path.expanduser("~/.local/share/Zeal/Zeal/docsets")

        if path and os.path.exists(path):
            if system == "Windows":
                os.startfile(path)
            elif system == "Darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        else:
            QMessageBox.warning(self, "Folder Not Found", f"Could not find Zeal docsets folder at:\n{path}\n\nPlease make sure Zeal is installed and has been run at least once.")

    def add_url(self):
        url = self.url_input.text().strip()
        if url:
            suggested_name = clean_domain(urlparse(url).netloc)
            name, ok = QInputDialog.getText(
                self, "Docset Name", f"Enter name for {url}:",
                text=suggested_name
            )
            if ok and name:
                row = self.url_table.rowCount()
                self.url_table.insertRow(row)
                self.url_table.setItem(row, 0, QTableWidgetItem(url))
                self.url_table.setItem(row, 1, QTableWidgetItem(name))
                self.url_input.clear()

    def remove_url(self):
        selected = self.url_table.selectionModel().selectedRows()
        for index in sorted(selected, reverse=True):
            self.url_table.removeRow(index.row())

    def browse_output(self):
        parent_dir = QFileDialog.getExistingDirectory(self, "Select Output Base Directory")
        if parent_dir:
            self.out_input.setText(parent_dir)

    def start_generation(self):
        self.docsets_queue = []
        for i in range(self.url_table.rowCount()):
            url = self.url_table.item(i, 0).text()
            name = self.url_table.item(i, 1).text()
            self.docsets_queue.append({"url": url, "name": name})
            
        self.output_base = self.out_input.text().strip()
        self.js = self.js_checkbox.isChecked()
        self.ignore_optional = self.ignore_optional_checkbox.isChecked()
        self.verbose = True # Always enable verbose logging since we have a tab for it
        self.force = self.force_checkbox.isChecked()
        self.engine = self.js_engine_combo.currentText()

        if not self.docsets_queue:
            QMessageBox.warning(self, "Error", "Please add at least one URL.")
            return
        if not self.output_base:
            QMessageBox.warning(self, "Error", "Please specify an output base directory.")
            return

        self.generate_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.process_next_docset()

    def stop_processing(self):
        if hasattr(self, 'scan_worker') and self.scan_worker.isRunning():
            self.scan_worker.stop()
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.stop()
        
        self.docsets_queue = []
        self.stop_btn.setEnabled(False)
        self.log_output.append('<br><font color="orange"><b>Stopping...</b></font>')

    def process_next_docset(self):
        if not self.docsets_queue:
            # All docsets processed message is now handled in on_generation_finished
            self.generate_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.progress_bar.setVisible(False)
            return

        self.current_docset = self.docsets_queue.pop(0)
        self.log_output.append(f"Scanning for {self.current_docset['name']} ({self.current_docset['url']})...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        self.scan_worker = ScanWorker([self.current_docset['url']], self.js, self.engine, self.verbose)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.error.connect(self.on_error)
        self.scan_worker.progress.connect(self.update_progress)
        self.scan_worker.log.connect(lambda m: self.log_output.append(m))
        self.scan_worker.verbose_log.connect(lambda m: self.verbose_log_output.append(m))
        self.scan_worker.start()

    def on_scan_finished(self, discovered_urls):
        self.progress_bar.setVisible(False)
        
        # Check if it was cancelled
        if hasattr(self, 'scan_worker') and self.scan_worker.cancel_event and self.scan_worker.cancel_event.is_set():
            self.log_output.append('<br><font color="orange"><b>Scan stopped.</b></font>')
            self.generate_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            return
        
        selected_urls = []
        root_urls = []
        if self.ignore_optional:
            # If ignore optional, we only take the URLs that match the initial domains
            initial_domains = {clean_domain(urlparse(u).netloc) for u in [self.current_docset['url']]}
            
            selected_urls = []
            for u in discovered_urls:
                if clean_domain(urlparse(u).netloc) in initial_domains:
                    selected_urls.append(u)
            
            main_url = self.current_docset['url']
            root_urls = [main_url]
            
            self.log_output.append(f"Automatically selected {len(selected_urls)} URLs for {self.current_docset['name']} (ignored {len(discovered_urls) - len(selected_urls)} out-of-domain URLs).")
        else:
            dialog = URLSelectionDialog(discovered_urls, [self.current_docset['url']], self)
            dialog.setWindowTitle(f"Select URLs for {self.current_docset['name']}")
            if dialog.exec() == QDialog.Accepted:
                selected_urls, root_urls = dialog.get_selected_urls()
            else:
                self.log_output.append(f"Generation for {self.current_docset['name']} cancelled by user.")
                self.process_next_docset()
                return

        if not selected_urls:
            self.log_output.append(f"No URLs selected for {self.current_docset['name']}. Skipping.")
            self.process_next_docset()
        else:
            self.run_single_generation(
                self.current_docset['name'],
                root_urls,
                selected_urls
            )

    def run_single_generation(self, name, urls, selected_urls):
        self.log_output.append(f"Starting generation for {name}...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)

        # We use MultiWorker even for a single docset to keep it simple
        self.worker = MultiWorker([(name, urls, selected_urls)], self.output_base, self.js, self.engine, self.verbose, self.force)
        self.worker.finished.connect(self.on_generation_finished)
        self.worker.error.connect(self.on_error)
        self.worker.progress.connect(self.update_progress)
        self.worker.log.connect(lambda m: self.log_output.append(m))
        self.worker.verbose_log.connect(lambda m: self.verbose_log_output.append(m))
        self.worker.start()

    def on_generation_finished(self):
        # Check if it was cancelled
        if hasattr(self, 'worker') and self.worker.cancel_event and self.worker.cancel_event.is_set():
            self.log_output.append('<br><font color="orange"><b>Generation stopped.</b></font>')
            self.generate_btn.setEnabled(True)
            self.stop_btn.setEnabled(False)
            self.progress_bar.setVisible(False)
            return

        self.log_output.append(f"Finished generating {self.current_docset['name']}.")
        if not self.docsets_queue:
            self.log_output.append('<br><font color="green"><b>Done: Docset(s) generated successfully.</b></font>')
            self.stop_btn.setEnabled(False)
        self.process_next_docset()

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def on_error(self, message):
        self.generate_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.log_output.append(f'<br><font color="red"><b>Error: {message}</b></font>')

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
