import logging
from pathlib import Path
from threading import Thread

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QFileDialog,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QPushButton, QRadioButton, QSlider, QTextEdit,
                               QVBoxLayout, QWidget)

from Code.GUI.backend.runner import run_command
from Code.GUI.logger_setup import logger
from Code.local_models.dataclass import RunConfig


class QtLogHandler(logging.Handler, QObject):
    log_signal = Signal(str)

    def __init__(self):
        QObject.__init__(self)
        logging.Handler.__init__(self)

    def emit(self, record):
        msg = self.format(record)
        self.log_signal.emit(msg)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Run miniGPTKB Command")
        self.setMinimumSize(500, 400)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # ---- Directory input ----
        self.dir_label = QLabel("Directory to save results:")
        self.dir_input = QLineEdit()
        self.dir_input.setReadOnly(True)
        self.dir_button = QPushButton("Browse…")
        self.dir_button.clicked.connect(self.select_directory)

        dir_layout = QVBoxLayout()
        dir_layout.addWidget(self.dir_label)
        dir_layout.addWidget(self.dir_input)
        dir_layout.addWidget(self.dir_button)

        # ---- LLM URL input ----
        self.url_label = QLabel("LLM URL:")
        self.url_input = QLineEdit("https://llm.scads.ai/v1")

        # ---- Model input ----
        self.model_label = QComboBox()
        self.model_label.addItems([
            "meta-llama/Llama-3.3-70B-Instruct",
            "meta-llama/Llama-4-Scout-17B-16E-Instruct",
            "openai/gpt-oss-120b",
            "openGPT-X/Teuken-7B-instruct-research-v0.4",
            "deepseek-ai/DeepSeek-R1",
        ])
        self.model_label.setCurrentText("meta-llama/Llama-3.3-70B-Instruct")
        self.model_label.setEditable(True)

        # ---- Topic input ----
        self.topic_label = QLabel("Topic")
        self.topic_input = QLineEdit("Ancient Babylon")
        self.topic_input.setPlaceholderText(
            "Enter a topic (e.g., 'Ancient Babylon')"
        )

        # ---- Seed entity input ----
        self.seed_label = QLabel("Seed Entity")
        self.seed_input = QLineEdit("Hammurabi")
        self.seed_input.setPlaceholderText(
            "Enter a seed entity (e.g., 'Hammurabi')"
        )

        # ---- Termination options ----
        self.options_label = QLabel("Termination Options:")
        self.options = {}

        termination_options = [
            ("Min Entities", "Enter number of entities"),
            ("Runtime (minutes)", "Enter runtime in minutes"),
        ]

        self.button_group = QButtonGroup(self)
        self.button_group.setExclusive(True)

        # ---- Triples slider ----
        self.slider_label = QLabel("Desired # of Triples:")
        # self.triples_label = QLabel()
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setMinimum(0)
        self.slider.setMaximum(2)
        self.slider.setTickInterval(1)
        self.slider.setTickPosition(QSlider.TicksBelow)

        tick_layout = QHBoxLayout()
        tick_layout.addWidget(QLabel("Few"), alignment=Qt.AlignLeft)
        tick_layout.addWidget(QLabel("Medium"), alignment=Qt.AlignCenter)
        tick_layout.addWidget(QLabel("Many"), alignment=Qt.AlignRight)

        # TODO: Update triples ranges (Luca)
        self.slider_options = {
            0: ("Few", 5, 10),
            1: ("Medium", 25, 50),
            2: ("Many", 50, 100),
        }

        self.slider.setValue(1)  # default medium

        # ---- Run button ----
        self.run_button = QPushButton("Run Command")
        self.run_button.clicked.connect(self.execute_command)

        # ---- Output box ----
        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)

        self.qt_handler = QtLogHandler()

        self.qt_handler.log_signal.connect(self.output_box.append)

        # Add widgets to main layout
        layout.addLayout(dir_layout)
        layout.addWidget(self.url_label)
        layout.addWidget(self.url_input)
        layout.addWidget(self.model_label)
        layout.addWidget(self.topic_label)
        layout.addWidget(self.topic_input)
        layout.addWidget(self.seed_label)
        layout.addWidget(self.seed_input)
        layout.addWidget(self.slider_label)
        layout.addWidget(self.slider)
        layout.addLayout(tick_layout)
        layout.addWidget(self.options_label)

        for i, (label, placeholder) in enumerate(termination_options):
            row = QHBoxLayout()

            radio = QRadioButton(label)
            input_field = QLineEdit()
            input_field.setPlaceholderText(placeholder)
            input_field.setEnabled(False)

            # Enable input only when this radio is checked
            radio.toggled.connect(input_field.setEnabled)

            # Add radio to exclusive group
            self.button_group.addButton(radio, id=i)

            row.addWidget(radio)
            row.addWidget(input_field)
            layout.addLayout(row)

            self.options[label] = (radio, input_field)

        layout.addWidget(self.run_button)
        layout.addWidget(self.output_box)

        # ---- Setup logging ----
        logger.addHandler(self.qt_handler)

    # def update_label(self, value):
    #     label, min_triples, max_triples = self.slider_options[value]
    #     self.triples_label.setText(
    #         f"{label} ({min_triples}-{max_triples} triples)"
    #     )

    def append_log(self, message):
        self.output_box.append(message)

    def select_directory(self):
        folder = QFileDialog.getExistingDirectory(
            self,
            "Select Directory to Save Results",
            str(Path.home())
        )
        if folder:
            self.dir_input.setText(folder)
            logger.info(f"Directory selected: {folder}")

    def execute_command(self):
        config = RunConfig()
        config.dir = self.dir_input.text().strip()
        config.url = self.url_input.text().strip()
        config.topic = self.topic_input.text().strip()
        config.seed_entity = self.seed_input.text().strip()
        config.model = self.model_label.currentText().strip()
        config.slider_value = self.slider.value()
        _, config.min_triples, config.max_triples = self.slider_options[config.slider_value]

        for label, (radio, input_field) in self.options.items():
            if radio.isChecked():
                config.termination_label = label
                config.termination = input_field.text().strip()

        if not config.dir:
            logger.warning("No directory provided!")
            return

        def run():
            logger.info(
                f"Running command with URL: {config.url}, "
                f"Topic: {config.topic}, Seed: {config.seed_entity}, "
                f"Triples: {config.min_triples}-{config.max_triples}"
            )

            try:
                result = run_command(config)
                logger.info("Command executed successfully.")

                self.output_box.append("\n=== Final Result ===")
                self.output_box.append(result)
            except Exception as e:
                logger.error(f"Error executing command: {e}")

        thread = Thread(target=run, daemon=True)
        thread.start()
