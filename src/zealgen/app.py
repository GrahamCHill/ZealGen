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
    QListWidgetItem, QInputDialog, QComboBox, QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, QThread, Signal, QStandardPaths
from .core import generate, scan
from .utils.url import normalize_url, clean_domain

class ScanWorker(QThread):
    finished = Signal(list)
    error = Signal(str)
    progress = Signal(int, int)

    def __init__(self, urls, js, fetcher_type="playwright"):
        super().__init__()
        self.urls = urls
        self.js = js
        self.fetcher_type = fetcher_type

    def run(self):
        try:
            def report_progress(current, total):
                self.progress.emit(current, total)

            discovered = anyio.run(scan, self.urls, self.js, 20, report_progress, self.fetcher_type)
            self.finished.emit(discovered)
        except Exception as e:
            self.error.emit(str(e))

class MultiWorker(QThread):
    finished = Signal()
    error = Signal(str)
    log = Signal(str)
    progress = Signal(int, int)

    def __init__(self, url_names, output_base, js, allowed_urls=None, fetcher_type="playwright"):
        super().__init__()
        self.url_names = url_names
        self.output_base = output_base
        self.js = js
        self.allowed_urls = allowed_urls
        self.fetcher_type = fetcher_type

    def run(self):
        try:
            # Group URLs by docset name
            groups = {}
            for url, name in self.url_names:
                if name not in groups:
                    groups[name] = []
                groups[name].append(url)

            total_docsets = len(groups)
            for i, (name, urls) in enumerate(groups.items()):
                self.log.emit(f"Generating docset: {name} ({i+1}/{total_docsets})")
                
                docset_filename = name if name.endswith(".docset") else f"{name}.docset"
                output_path = os.path.join(self.output_base, docset_filename)
                
                # Filter allowed_urls for this docset based on domain if possible
                # or just pass them all and let core.py's heuristic/explicit check handle it.
                # Since core.py uses normalize_url for comparison, passing all is safe
                # but might be slightly inefficient if the list is huge.
                
                def report_progress(current, total):
                    # For now, just report the progress of the current docset
                    # We could try to aggregate, but that's complex without knowing total pages beforehand
                    self.progress.emit(current, total)

                anyio.run(generate, urls, output_path, self.js, 100, report_progress, self.allowed_urls, self.fetcher_type)
            
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
                    self.related_list.addItem(item)
                else:
                    # Optional subpage on the same domain
                    item.setCheckState(Qt.Checked)
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
            domain_item.setCheckState(0, Qt.Checked)
            domain_item.setFlags(domain_item.flags() | Qt.ItemIsAutoTristate | Qt.ItemIsUserCheckable)
            
            for url in sorted(other_urls_by_domain[domain]):
                url_item = QTreeWidgetItem(domain_item)
                url_item.setText(0, url)
                url_item.setCheckState(0, Qt.Checked)
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
        # Select all in the other tree
        for i in range(self.other_tree.topLevelItemCount()):
            item = self.other_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Checked)
            for j in range(item.childCount()):
                item.child(j).setCheckState(0, Qt.Checked)

    def deselect_all_optional(self):
        # Deselect all in the other tree
        for i in range(self.other_tree.topLevelItemCount()):
            item = self.other_tree.topLevelItem(i)
            item.setCheckState(0, Qt.Unchecked)
            for j in range(item.childCount()):
                item.child(j).setCheckState(0, Qt.Unchecked)

    def get_selected_urls(self):
        selected = []
        # Process related_list
        for i in range(self.related_list.count()):
            item = self.related_list.item(i)
            # If it has no checkbox, it's mandatory
            if item.checkState() is None:
                # Strip the mandatory marker if present
                text = item.text()
                if text.endswith(" *"):
                    text = text[:-2]
                selected.append(text)
            elif item.checkState() == Qt.Checked:
                selected.append(item.text())
        
        # Process other_tree (only children are actual URLs)
        for i in range(self.other_tree.topLevelItemCount()):
            parent = self.other_tree.topLevelItem(i)
            for j in range(parent.childCount()):
                child = parent.child(j)
                if child.checkState(0) == Qt.Checked:
                    selected.append(child.text(0))
                    
        return selected

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ZealGen")
        self.setMinimumSize(600, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # URL Table
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
        url_names = []
        for i in range(self.url_table.rowCount()):
            url = self.url_table.item(i, 0).text()
            name = self.url_table.item(i, 1).text()
            url_names.append((url, name))
            
        output_base = self.out_input.text().strip()
        js = self.js_checkbox.isChecked()
        engine = self.js_engine_combo.currentText()

        if not url_names:
            QMessageBox.warning(self, "Error", "Please add at least one URL.")
            return
        if not output_base:
            QMessageBox.warning(self, "Error", "Please specify an output base directory.")
            return

        self.generate_btn.setEnabled(False)
        self.log_output.append(f"Starting initial scan (Engine: {engine})...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        urls = [un[0] for un in url_names]
        self.scan_worker = ScanWorker(urls, js, engine)
        self.scan_worker.finished.connect(self.on_scan_finished)
        self.scan_worker.error.connect(self.on_error)
        self.scan_worker.progress.connect(self.update_progress)
        self.scan_worker.start()

    def on_scan_finished(self, discovered_urls):
        self.progress_bar.setVisible(False)
        url_names = []
        for i in range(self.url_table.rowCount()):
            url = self.url_table.item(i, 0).text()
            name = self.url_table.item(i, 1).text()
            url_names.append((url, name))
        
        urls = [un[0] for un in url_names]
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
        url_names = []
        for i in range(self.url_table.rowCount()):
            url = self.url_table.item(i, 0).text()
            name = self.url_table.item(i, 1).text()
            url_names.append((url, name))
            
        output_base = self.out_input.text().strip()
        js = self.js_checkbox.isChecked()
        engine = self.js_engine_combo.currentText()

        self.log_output.append(f"Starting generation for {len(url_names)} docsets (Total {len(selected_urls)} pages)...")
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(True)
        
        self.worker = MultiWorker(url_names, output_base, js, allowed_urls=selected_urls, fetcher_type=engine)
        self.worker.finished.connect(self.on_finished)
        self.worker.error.connect(self.on_error)
        self.worker.progress.connect(self.update_progress)
        self.worker.log.connect(lambda m: self.log_output.append(m))
        self.worker.start()

    def update_progress(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    def on_finished(self):
        self.progress_bar.setValue(self.progress_bar.maximum())
        self.generate_btn.setEnabled(True)
        QMessageBox.information(self, "Done", "Docset generated successfully.")

    def on_error(self, message):
        self.generate_btn.setEnabled(True)
        QMessageBox.critical(self, "Error", f"An error occurred: {message}")

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
