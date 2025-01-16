#!/usr/bin/env python3

import os
import struct
import binascii
import traceback
import hid

from PyQt6.QtWidgets import (
    QApplication,
    QWidget,
    QLabel,
    QPushButton,
    QMessageBox,
    QComboBox,
    QHBoxLayout,
    QVBoxLayout,
    QGridLayout,
    QSlider,
    QStyle,
    QSpacerItem,
    QSizePolicy
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap

# -----------------------------------------------------------------------------------
# Constants and data (same as original)
# -----------------------------------------------------------------------------------

VID = 0xCAFE
PID = 0xBAFA
CONFIG_SIZE = 22
REPORT_ID = 3
CONFIG_VERSION = 1
PICTURE_FILENAME = os.path.join(os.path.dirname(__file__), "trackball.png")

BALL_FUNCTIONS = (
    ("None", "0"),
    ("Cursor X", "1"),
    ("Cursor Y", "2"),
    ("V scroll", "3"),
    ("H scroll", "4"),
    ("Cursor X (inverted)", "-1"),
    ("Cursor Y (inverted)", "-2"),
    ("V scroll (inverted)", "-3"),
    ("H scroll (inverted)", "-4"),
)

BUTTON_FUNCTIONS = (
    ("None", "0"),
    ("Button 1 (left)", "1"),
    ("Button 2 (right)", "2"),
    ("Button 3 (middle)", "3"),
    ("Button 4 (back)", "4"),
    ("Button 5 (forward)", "5"),
    ("Button 6", "6"),
    ("Button 7", "7"),
    ("Button 8", "8"),
    ("Click-drag", "9"),
    ("Shift", "10"),
)

RING_FUNCTIONS = (
    ("None", "0"),
    ("V scroll", "1"),
    ("H scroll", "2"),
    ("V scroll (inverted)", "-1"),
    ("H scroll (inverted)", "-2"),
)


# -----------------------------------------------------------------------------------
# Helper functions to build widgets
# -----------------------------------------------------------------------------------

def make_dropdown(options):
    """
    Creates a QComboBox, populates it with (text, data) pairs.
    The displayed text is options[i][0], the underlying data is options[i][1].
    """
    combo = QComboBox()
    for (label, val) in options:
        combo.addItem(label, val)
    # Default to the first item, or the one with "0" if you prefer
    combo.setCurrentIndex(0)
    return combo


def make_slider():
    """
    Creates a QSlider from 1..120 with step=1.
    We'll pair it with a label that updates the
    displayed value × 100 (as in GTK's "format-value").
    """
    slider = QSlider(Qt.Orientation.Horizontal)
    slider.setRange(1, 120)
    slider.setValue(1)   # default
    return slider


# -----------------------------------------------------------------------------------
# Main Window
# -----------------------------------------------------------------------------------

class TrackballConfigWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Trackball Configuration")

        # Data models replaced by direct combo usage in PyQt
        self.devices_dropdown = QComboBox()
        
        # Buttons
        self.refresh_button = QPushButton()
        # You can load a standard icon for “Refresh” from the current style:
        self.refresh_button.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.refresh_button.setToolTip("Refresh device list")
        self.refresh_button.clicked.connect(self.refresh_device_list)

        self.load_button = QPushButton("Load from device")
        self.load_button.clicked.connect(self.load_button_clicked)

        self.save_button = QPushButton("Save to device")
        self.save_button.clicked.connect(self.save_button_clicked)


        # Make combos and sliders
        self.ball_x_dropdown = make_dropdown(BALL_FUNCTIONS)
        self.ball_x_shifted_dropdown = make_dropdown(BALL_FUNCTIONS)
        self.ball_y_dropdown = make_dropdown(BALL_FUNCTIONS)
        self.ball_y_shifted_dropdown = make_dropdown(BALL_FUNCTIONS)
        self.ring_dropdown = make_dropdown(RING_FUNCTIONS)
        self.ring_shifted_dropdown = make_dropdown(RING_FUNCTIONS)

        self.button1_dropdown = make_dropdown(BUTTON_FUNCTIONS)
        self.button1_shifted_dropdown = make_dropdown(BUTTON_FUNCTIONS)
        self.button2_dropdown = make_dropdown(BUTTON_FUNCTIONS)
        self.button2_shifted_dropdown = make_dropdown(BUTTON_FUNCTIONS)
        self.button3_dropdown = make_dropdown(BUTTON_FUNCTIONS)
        self.button3_shifted_dropdown = make_dropdown(BUTTON_FUNCTIONS)
        self.button4_dropdown = make_dropdown(BUTTON_FUNCTIONS)
        self.button4_shifted_dropdown = make_dropdown(BUTTON_FUNCTIONS)

        self.ball_cpi = make_slider()
        self.ball_cpi_shifted = make_slider()

        # We'll keep a label to show the slider's “value * 100” text
        # for each slider. We’ll update these when the slider moves.
        self.ball_cpi_label = QLabel("100")  # default for value=1
        self.ball_cpi_shifted_label = QLabel("100")

        self.ball_cpi.valueChanged.connect(self.on_cpi_changed)
        self.ball_cpi_shifted.valueChanged.connect(self.on_cpi_shifted_changed)

        # Build layouts
        # Main horizontal layout
        main_hbox = QHBoxLayout(self)

        # Left vertical layout (device controls, grid, etc.)
        left_vbox = QVBoxLayout()

        # Device row
        device_hbox = QHBoxLayout()
        device_hbox.addWidget(self.devices_dropdown)
        device_hbox.addWidget(self.refresh_button)
        left_vbox.addLayout(device_hbox)

        # Load / Save row
        actions_hbox = QHBoxLayout()
        actions_hbox.addWidget(self.load_button)
        actions_hbox.addWidget(self.save_button)
        left_vbox.addLayout(actions_hbox)

        # Grid for config
        grid = QGridLayout()
        row = 0
        # Row 0: "Normal" / "Shifted"
        grid.addWidget(QLabel(""), row, 0)
        normal_label = QLabel("Normal")
        normal_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(normal_label, row, 1)
        shifted_label = QLabel("Shifted")
        shifted_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(shifted_label, row, 2)
        row += 1

        # Row: Ball X
        grid.addWidget(QLabel("Ball X axis"), row, 0, alignment=Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.ball_x_dropdown, row, 1)
        grid.addWidget(self.ball_x_shifted_dropdown, row, 2)
        row += 1

        # Row: Ball Y
        grid.addWidget(QLabel("Ball Y axis"), row, 0, alignment=Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.ball_y_dropdown, row, 1)
        grid.addWidget(self.ball_y_shifted_dropdown, row, 2)
        row += 1

        # Row: Ball CPI
        grid.addWidget(QLabel("Ball CPI"), row, 0, alignment=Qt.AlignmentFlag.AlignRight)
        # For each slider, we’ll place the slider plus a small label side by side
        cpi_hbox = QHBoxLayout()
        cpi_hbox.addWidget(self.ball_cpi)
        cpi_hbox.addWidget(self.ball_cpi_label)
        grid.addLayout(cpi_hbox, row, 1)

        cpi_shifted_hbox = QHBoxLayout()
        cpi_shifted_hbox.addWidget(self.ball_cpi_shifted)
        cpi_shifted_hbox.addWidget(self.ball_cpi_shifted_label)
        grid.addLayout(cpi_shifted_hbox, row, 2)
        row += 1

        # Row: Ring
        grid.addWidget(QLabel("Ring"), row, 0, alignment=Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.ring_dropdown, row, 1)
        grid.addWidget(self.ring_shifted_dropdown, row, 2)
        row += 1

        # Rows: Buttons
        grid.addWidget(QLabel("Button 1"), row, 0, alignment=Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.button1_dropdown, row, 1)
        grid.addWidget(self.button1_shifted_dropdown, row, 2)
        row += 1

        grid.addWidget(QLabel("Button 2"), row, 0, alignment=Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.button2_dropdown, row, 1)
        grid.addWidget(self.button2_shifted_dropdown, row, 2)
        row += 1

        grid.addWidget(QLabel("Button 3"), row, 0, alignment=Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.button3_dropdown, row, 1)
        grid.addWidget(self.button3_shifted_dropdown, row, 2)
        row += 1

        grid.addWidget(QLabel("Button 4"), row, 0, alignment=Qt.AlignmentFlag.AlignRight)
        grid.addWidget(self.button4_dropdown, row, 1)
        grid.addWidget(self.button4_shifted_dropdown, row, 2)
        row += 1

        left_vbox.addLayout(grid)
        main_hbox.addLayout(left_vbox)

        # The image on the right
        try:
            pixmap = QPixmap(PICTURE_FILENAME)
        except Exception:
            pixmap = QPixmap()  # fallback if not found
        image_label = QLabel()
        image_label.setPixmap(pixmap.scaled(
            QSize(300, 300), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        ))
        main_hbox.addWidget(image_label)

        # Populate the device list
        self.refresh_device_list()

        self.setLayout(main_hbox)

    # ---------------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------------

    def show_exception_dialog(self, exc_str):
        """
        Show a modal error dialog with the given traceback string.
        """
        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Critical)
        msg.setWindowTitle("Error")
        msg.setText(exc_str)
        msg.setStandardButtons(QMessageBox.StandardButton.Ok)
        msg.exec()

    def on_cpi_changed(self):
        value = self.ball_cpi.value()
        self.ball_cpi_label.setText(str(value * 100))

    def on_cpi_shifted_changed(self):
        value = self.ball_cpi_shifted.value()
        self.ball_cpi_shifted_label.setText(str(value * 100))

    # ---------------------------------------------------------------------------------
    # Device handling
    # ---------------------------------------------------------------------------------

    def refresh_device_list(self):
        self.devices_dropdown.clear()

        devices = [
            d
            for d in hid.enumerate()
            if d["vendor_id"] == VID and d["product_id"] == PID
        ]
        #self.test = devices[0]
        if devices:
            for d in devices:
                # We store the path as itemData
                text = f"{d['manufacturer_string']} {d['product_string']}"
                path_str = d["path"] if isinstance(d["path"], str) else d["path"].decode("ascii", "ignore")
                self.devices_dropdown.addItem(text, path_str)

            self.load_button.setEnabled(True)
            self.save_button.setEnabled(True)
        else:
            self.devices_dropdown.addItem("No devices found", "NULL")
            self.load_button.setEnabled(False)
            self.save_button.setEnabled(False)

    def load_button_clicked(self):
        try:
            self.load_config_from_device()
        except Exception as e:
            self.show_exception_dialog(traceback.format_exc())

    def save_button_clicked(self):
        try:
            self.save_config_to_device()
        except Exception as e:
            self.show_exception_dialog(traceback.format_exc())

    def load_config_from_device(self):
        path = self.devices_dropdown.currentData()
        print(path)
        if path == "NULL":
            raise RuntimeError("No device selected.")

        #dev = hid.device(path=path.encode("ascii"))
        dev = hid.device()
        dev.open(VID,PID)
        #dev = hid.device(path=self.test["path"])
        #print(dev,self.test,sep="\n")
        data = dev.get_feature_report(REPORT_ID, CONFIG_SIZE + 1)
        dev.close()
        data_list = [
            "report_id",
            "version",
            "command",
            "ball_x",
            "ball_y",
            "ball_x_shifted",
            "ball_y_shifted",
            "ball_cpi",
            "ball_cpi_shifted",
            "ring",
            "ring_shifted",
            "button1",
            "button2",
            "button3",
            "button4",
            "button1_shifted",
            "button2_shifted",
            "button3_shifted",
            "button4_shifted",
            "crc32",
        ]
        #print(data)
        val = dict(zip(data_list,data))
        # for item in unpacked:
        #     print(item)
        # unpacked = struct.unpack("<BBb2b2bBBbb4b4bL", data)
        # (
        #     report_id,
        #     version,
        #     command,
        #     ball_x,
        #     ball_y,
        #     ball_x_shifted,
        #     ball_y_shifted,
        #     ball_cpi,
        #     ball_cpi_shifted,
        #     ring,
        #     ring_shifted,
        #     button1,
        #     button2,
        #     button3,
        #     button4,
        #     button1_shifted,
        #     button2_shifted,
        #     button3_shifted,
        #     button4_shifted,
        #     crc32,
        # ) = unpacked
        # BALL_FUNCTIONS = (
        #     ("None", "0"),
        #     ("Cursor X", "1"),
        #     ("Cursor Y", "2"),
        #     ("V scroll", "3"),
        #     ("H scroll", "4"),
        #     ("Cursor X (inverted)", "-1"),
        #     ("Cursor Y (inverted)", "-2"),
        #     ("V scroll (inverted)", "-3"),
        #     ("H scroll (inverted)", "-4"),
        # )
        load_ball = {
            "0":"None",
            "1":"Cursor X",
            "2":"Cursor Y",
            "3":"V scroll",
            "4":"H scroll",
            "255":"Cursor X (inverted)",
            "254":"Cursor Y (inverted)",
            "253":"V scroll (inverted)",
            "252":"H scroll (inverted)",
        }
        load_button = {
            "0":"None",
            "1":"Button 1 (left)",
            "2":"Button 2 (right)",
            "3":"Button 3 (middle)",
            "4":"Button 4 (back)",
            "5":"Button 5 (forward)",
            "6":"Button 6",
            "7":"Button 7",
            "8":"Button 8",
            "9":"Click-drag",
            "10":"Shift",
        }

        load_ring = {
            "0":"None",
            "1":"V scroll",
            "2":"H scroll",
            "255":"V scroll (inverted)",
            "254":"H scroll (inverted)",
        }
        # Set combos
        # self.set_combo_by_data(self.ball_x_dropdown, val["ball_x"])
        # self.set_combo_by_data(self.ball_x_shifted_dropdown, val["ball_x_shifted"])
        # self.set_combo_by_data(self.ball_y_dropdown, val["ball_y"])
        # self.set_combo_by_data(self.ball_y_shifted_dropdown, val["ball_y_shifted"])
        # self.set_combo_by_data(self.ring_dropdown, val["ring"])
        # self.set_combo_by_data(self.ring_shifted_dropdown, val["ring_shifted"])
        # self.set_combo_by_data(self.button1_dropdown, val["button1"])
        # self.set_combo_by_data(self.button1_shifted_dropdown, val["button1_shifted"])
        # self.set_combo_by_data(self.button2_dropdown, val["button2"])
        # self.set_combo_by_data(self.button2_shifted_dropdown, val["button2_shifted"])
        # self.set_combo_by_data(self.button3_dropdown, val["button3"])
        # self.set_combo_by_data(self.button3_shifted_dropdown, val["button3_shifted"])
        # self.set_combo_by_data(self.button4_dropdown, val["button4"])
        # self.set_combo_by_data(self.button4_shifted_dropdown, val["button4_shifted"])
        self.ball_x_dropdown.setCurrentText(load_ball[str(val["ball_x"])])
        self.ball_x_shifted_dropdown.setCurrentText(load_ball[str(val["ball_x_shifted"])])
        self.ball_y_dropdown.setCurrentText(load_ball[str(val["ball_x"])])
        self.ball_y_shifted_dropdown.setCurrentText(load_ball[str(val["ball_y_shifted"])])
        self.ring_dropdown.setCurrentText(load_ring[str(val["ring"])])
        self.ring_shifted_dropdown.setCurrentText(load_ring[str(val["ring_shifted"])])
        self.button1_dropdown.setCurrentText(load_button[str(val["button1"])])
        self.button1_shifted_dropdown.setCurrentText(load_button[str(val["button1_shifted"])])
        self.button2_dropdown.setCurrentText(load_button[str(val["button2"])])
        self.button2_shifted_dropdown.setCurrentText(load_button[str(val["button2_shifted"])])
        self.button3_dropdown.setCurrentText(load_button[str(val["button3"])])
        self.button3_shifted_dropdown.setCurrentText(load_button[str(val["button3_shifted"])])
        self.button4_dropdown.setCurrentText(load_button[str(val["button4"])])
        self.button4_shifted_dropdown.setCurrentText(load_button[str(val["button4_shifted"])])



        self.ball_cpi.setValue(val["ball_cpi"])
        self.ball_cpi_shifted.setValue(val["ball_cpi_shifted"])
        print(val)

    def save_config_to_device(self):
        path = self.devices_dropdown.currentData()
        if path == "NULL":
            raise RuntimeError("No device selected.")
        dev = hid.device()
        dev.open(VID,PID)

        command = 0
        ball_x = int(self.ball_x_dropdown.currentData())
        ball_x_shifted = int(self.ball_x_shifted_dropdown.currentData())
        ball_y = int(self.ball_y_dropdown.currentData())
        ball_y_shifted = int(self.ball_y_shifted_dropdown.currentData())
        ring = int(self.ring_dropdown.currentData())
        ring_shifted = int(self.ring_shifted_dropdown.currentData())
        button1 = int(self.button1_dropdown.currentData())
        button1_shifted = int(self.button1_shifted_dropdown.currentData())
        button2 = int(self.button2_dropdown.currentData())
        button2_shifted = int(self.button2_shifted_dropdown.currentData())
        button3 = int(self.button3_dropdown.currentData())
        button3_shifted = int(self.button3_shifted_dropdown.currentData())
        button4 = int(self.button4_dropdown.currentData())
        button4_shifted = int(self.button4_shifted_dropdown.currentData())
        ball_cpi_val = int(self.ball_cpi.value())
        ball_cpi_shifted_val = int(self.ball_cpi_shifted.value())

        # Pack
        data = struct.pack(
            "<BBb2b2bBBbb4b4b",
            REPORT_ID,
            CONFIG_VERSION,
            command,
            ball_x,
            ball_y,
            ball_x_shifted,
            ball_y_shifted,
            ball_cpi_val,
            ball_cpi_shifted_val,
            ring,
            ring_shifted,
            button1,
            button2,
            button3,
            button4,
            button1_shifted,
            button2_shifted,
            button3_shifted,
            button4_shifted,
        )
        crc32_val = binascii.crc32(data[1:])
        crc_bytes = struct.pack("<L", crc32_val)
        data += crc_bytes

        #dev = hid.device(path=path.encode("ascii"))
        #dev = hid.device(path=self.test['path'])
        dev.send_feature_report(data)
        dev.close()

    def set_combo_by_data(self, combo, data_value):
        """Helper to select a QComboBox item by its underlying data."""
        #print(data_value)
        for i in range(combo.count()):
            if combo.currentText() == data_value:
                combo.setCurrentIndex()
            # if combo.itemData(i) == data_value:
            #     combo.setCurrentIndex(i)
            #     return
        # if not found, fallback
        combo.setCurrentIndex(0)


# -----------------------------------------------------------------------------------
# main() function
# -----------------------------------------------------------------------------------

def main():
    import sys
    app = QApplication(sys.argv)
    window = TrackballConfigWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
