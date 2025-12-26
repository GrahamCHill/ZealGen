import sys
import anyio
import os
import platform
import subprocess
from urllib.parse import urlparse
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLineEdit, QPushButton, QListWidget, QFileDialog, QCheckBox,
    QLabel, QTextEdit, QMessageBox, QProgressBar, QDialog,
    QListWidgetItem, QInputDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QStandardPaths
from .core import generate, scan
from .utils.url import normalize_url, clean_domain

class ScanWorker(QThread):
    finished = Signal(list)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, urls, js):
        super().__init__()
        self.urls = urls
        self.js = js

    def run(self):
        try:
            def report_progress(current, total):
                self.progress.emit(current, total)

            discovered = anyio.run(scan, self.urls, self.js, 20, report_progress)
            self.finished.emit(discovered)
        except Exception as e:
            self.error.emit(str(e))

class Worker(QThread):
    finished = Signal()
    error = Signal(str)
    log = Signal(str)
    progress = Signal(int, int)

    def __init__(self, urls, output, js, allowed_urls=None):
        super().__init__()
        self.urls = urls
        self.output = output
        self.js = js
        self.allowed_urls = allowed_urls

    def run(self):
        try:
            def report_progress(current, total):
                self.progress.emit(current, total)

            anyio.run(generate, self.urls, self.output, self.js, 100, report_progress, self.allowed_urls)
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
        self.other_list = QListWidget()
        other_layout.addWidget(self.other_list)
        lists_layout.addLayout(other_layout)
        
        main_layout.addLayout(lists_layout)

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
                    # No checkbox or disabled checkbox? User said "not have a tickbox"
                    # But if I use QListWidgetItem without setting check state, it doesn't have one.
                    self.related_list.addItem(item)
                else:
                    # Optional subpage on the same domain
                    item.setCheckState(Qt.Checked)
                    self.related_list.addItem(item)
            else:
                # Other domains go to the right
                item = QListWidgetItem(url)
                item.setCheckState(Qt.Checked)
                self.other_list.addItem(item)

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

    def select_all_optional(self):
        # Select all in the other list (right pane) that have checkboxes
        for i in range(self.other_list.count()):
            item = self.other_list.item(i)
            if item.checkState() is not None:
                item.setCheckState(Qt.Checked)

    def deselect_all_optional(self):
        # Deselect all in the other list (right pane) that have checkboxes
        for i in range(self.other_list.count()):
            item = self.other_list.item(i)
            if item.checkState() is not None:
                item.setCheckState(Qt.Unchecked)

    def get_selected_urls(self):
        selected = []
        # Process both lists
        for list_widget in [self.related_list, self.other_list]:
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                # If it has no checkbox, it's mandatory
                if item.checkState() is None:
                    # Strip the mandatory marker if present
                    text = item.text()
                    if text.endswith(" *"):
                        text = text[:-2]
                    selected.append(text)
                elif item.checkState() == Qt.Checked:
                    selected.append(item.text())
        return selected

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Zeal Docset Generator")
        self.setMinimumSize(600, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # URL list
        layout.addWidget(QLabel("URLs to fetch:"))
        self.url_list = QListWidget()
        layout.addWidget(self.url_list)

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
        layout.addWidget(QLabel("Output Docset Path:"))
        out_layout = QHBoxLayout()
        self.out_input = QLineEdit()
        out_layout.addWidget(self.out_input)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self.browse_output)
        out_layout.addWidget(browse_btn)
        layout.addLayout(out_layout)

        # Options
        self.js_checkbox = QCheckBox("Enable JavaScript (Playwright)")
        layout.addWidget(self.js_checkbox)

        # Progress
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Logs
        layout.addWidget(QLabel("Logs:"))
        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        layout.addWidget(self.log_output)

        # Generate button
        self.generate_btn = QPushButton("Generate Docset")
        self.generate_btn.clicked.connect(self.start_generation)
        layout.addWidget(self.generate_btn)

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
            self.url_list.addItem(url)
            self.url_input.clear()

    def remove_url(self):
        for item in self.url_list.selectedItems():
            self.url_list.takeItem(self.url_list.row(item))

    def browse_output(self):
        parent_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory")
        if parent_dir:
            # If they have URLs, suggest a name based on the first URL
            urls = [self.url_list.item(i).text() for i in range(self.url_list.count())]
            suggested_name = "Custom"
            if urls:
                suggested_name = clean_domain(urlparse(urls[0]).netloc)
            
            # Prompt the user for the docset name
            name, ok = QInputDialog.getText(
                self, "Docset Name", "Enter the name for your docset:",
                text=suggested_name
            )
            
            if ok and name:
                if not name.endswith(".docset"):
                    name += ".docset"
                path = os.path.join(parent_dir, name)
                self.out_input.setText(path)

    def start_generation(self):
        urls = [self.url_list.item(i).text() for i in range(self.url_list.count())]
        output = self.out_input.text().strip()
        if output and not output.endswith(".docset"):
            output += ".docset"
            self.out_input.setText(output)
        js = self.js_checkbox.isChecked()

        if not urls:
            QMessageBox.warning(self, "Error", "Please add at least one URL.")
            return
        if not output:
            QMessageBox.warning(self, "Error", "Please specify an output path.")
            return

        self.generate_btn.setEnabled(False)
        self.log_output.append("Starting initial scan...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        self.scan_worker = ScanWorker(urls, js)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.error.connect(self.on_error)
        self.scan_worker.progress.connect(self.update_progress)
        self.scan_worker.start()

    def on_scan_finished(self, discovered_urls):
        self.progress_bar.setVisible(False)
        urls = [self.url_list.item(i).text() for i in range(self.url_list.count())]
        dialog = URLSelectionDialog(discovered_urls, urls, self)
        if dialog.exec() == QDialog.Accepted:
            selected_urls = dialog.get_selected_urls()
            if not selected_urls:
                QMessageBox.warning(self, "Error", "No URLs selected. Generation cancelled.")
                self.generate_btn.setEnabled(True)
                return
            
            self.run_generation(selected_urls)
        else:
            self.log_output.append("Generation cancelled by user.")
            self.generate_btn.setEnabled(True)

    def run_generation(self, selected_urls):
        urls = [self.url_list.item(i).text() for i in range(self.url_list.count())]
        output = self.out_input.text().strip()
        if not output.endswith(".docset"):
            output += ".docset"
        js = self.js_checkbox.isChecked()

        self.log_output.append(f"Starting generation with {len(selected_urls)} pages...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        self.worker = Worker(urls, output, js, allowed_urls=selected_urls)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.progress.connect(self.update_progress)
        self.worker.start()

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def on_finished(self):
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.log_output.append("Generation completed successfully!")
        self.generate_btn.setEnabled(True)
        QMessageBox.information(self, "Done", "Docset generated successfully.")

    def on_error(self, message):
        self.log_output.append(f"Error: {message}")
        self.generate_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"An error occurred: {message}")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
