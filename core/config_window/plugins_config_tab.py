from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QCheckBox

class PluginsConfigWidget(QWidget):
    def __init__(self, data_router, parent=None):
        super().__init__(parent)
        self.data_router = data_router
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        plugin_manager = self.data_router.plugin_manager
        plugins = plugin_manager.list_plugins()
        if not plugins:
            layout.addWidget(QLabel("No plugins loaded."))
        else:
            for plugin_name in plugins:
                h_layout = QHBoxLayout()
                checkbox = QCheckBox(plugin_name)
                checkbox.setChecked(True)
                mode_label = QLabel("Mode: [enhance/replace?]")
                h_layout.addWidget(checkbox)
                h_layout.addWidget(mode_label)
                layout.addLayout(h_layout)
        self.setLayout(layout)
