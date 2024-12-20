#!/usr/bin/python
# -*- coding:utf-8 -*-

import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QTabWidget, QWidget, QSpinBox,
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QSlider, QLineEdit, QFormLayout, QMessageBox
)
from PyQt5.QtCore import QThread, pyqtSignal, QTimer, Qt
from Automation.BDaq.InstantDoCtrl import InstantDoCtrl
from Automation.BDaq.InstantDiCtrl import InstantDiCtrl

from Automation.BDaq.BDaqApi import BioFailed
from threading import Lock

from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

deviceDescription = "USB-4704,BID#0"
profilePath = "../../profile/DemoDevice.xml"

import math
import time

class MainApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Digital IO Control with Frequency and Waveform Generation")
        self.setGeometry(100, 100, 600, 600)

        self.tabs = QTabWidget()
        self.do_tab = DO_Tab()
        self.di_tab = DI_Tab()

        self.tabs.addTab(self.do_tab, "DO")
        self.tabs.addTab(self.di_tab, "DI")

        self.setCentralWidget(self.tabs)
        self.tabs.currentChanged.connect(self.on_tab_change)

    def on_tab_change(self, index):
        if index == 0:  # DO Tab
            self.di_tab.stop_thread()
        elif index == 1:  # DI Tab
            self.di_tab.resume_thread()

class DOThread(QThread):
    log_signal = pyqtSignal(str)
    error_signal = pyqtSignal(str)
    value_changed_signal = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.running = False
        self.current_value = 0
        self.frequency = 0
        self.amplitude = 0
        self.offset = 0
        self.waveform_running = False
        self.lock = Lock()

    def set_value(self, value):
        self.current_value = value

    def set_frequency(self, frequency):
        """Update the frequency and adjust output accordingly."""
        self.frequency = frequency
        if self.running:
            self.stop_output()  # Stop the current output if frequency is updated
            self.start_output()  # Restart output with the new frequency

    def set_waveform(self, running, offset=0, amplitude=1, frequency=0):
        self.waveform_running = running
        if running:
            # Ensure amplitude, offset, and frequency are valid
            self.amplitude = max(0, min(3, amplitude))
            self.offset = max(0, min(3, offset))
            self.frequency = max(1, min(31, round(frequency)))  # Frequency between 1 and 31 Hz
        else:
            self.amplitude = 0
            self.offset = 0
            self.frequency = 0

    def start_output(self):
        if self.frequency == 0:
            self.error_signal.emit("Frequency cannot be 0 Hz when starting DO output!")
            return
        self.running = True

    def stop_output(self):
        self.running = False

    def run(self):
        instantDoCtrl = InstantDoCtrl(deviceDescription)
        instantDoCtrl.loadProfile = profilePath
        try:
            while True:
                if self.running:
                    if self.waveform_running:

                        current_value_amp = self.offset + self.amplitude * math.sin(2 * math.pi * self.frequency * time.time())
                        current_value_amp = max(min(round(current_value_amp), 3), 0)

                        self.current_value = (
                                0b10000000 +  # 启动位，总是1
                                (current_value_amp << 5) +  # 电压值
                                self.frequency  # 频率值
                        )
                        self.value_changed_signal.emit(self.current_value)  # 发出信号
                        # 数据写入逻辑保持不变
                        dataBuffer = [self.current_value]

                        ret = instantDoCtrl.writeAny(0, 1, dataBuffer)


                        if BioFailed(ret):
                            self.log_signal.emit("Error: DO output failed!")
                        else:
                            self.log_signal.emit(
                                f"DO output: {self.current_value:08b} (Amp: {self.amplitude}V, Wave_Freq: {self.frequency}Hz, Send_Freq: {16 * self.frequency}Hz)"
                            )

                        self.msleep(int(1000 / max(self.frequency, 1)) // 16)

                    else:
                        # Normal DO output
                        dataBuffer = [self.current_value]
                        ret = instantDoCtrl.writeAny(0, 1, dataBuffer)
                        if BioFailed(ret):
                            self.log_signal.emit("Error: DO output failed!")
                        else:
                            self.log_signal.emit(
                                f"DO output: {self.current_value:08b} (Amplitude: {self.amplitude}V, Frequency: {self.frequency}Hz)"
                            )
                        self.msleep(int(1000 / max(self.frequency, 1)))  # Adjust sleep based on frequency


                if not self.running:
                    self.msleep(50)  # Wait a little to reduce resource usage
                    continue
        finally:
            instantDoCtrl.dispose()


class DO_Tab(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()

        # 标志是否在自动输出模式
        self.auto_output_mode = False

        # Button layout
        button_layout = QHBoxLayout()
        self.buttons = []
        for i in range(8):
            btn = QPushButton()
            btn.setCheckable(True)
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(self.get_button_style(False))
            btn.clicked.connect(self.update_value)
            self.buttons.append(btn)
            button_layout.addWidget(btn)

        # Frequency slider
        slider_layout = QHBoxLayout()
        self.freq_slider = QSlider(Qt.Horizontal)
        self.freq_slider.setRange(0, 31)  # Frequency range: 0 to 31 Hz
        self.freq_slider.setValue(0)
        self.freq_slider.valueChanged.connect(self.update_frequency)

        slider_label = QLabel("Frequency:")
        self.freq_display = QLabel("0 Hz")
        slider_layout.addWidget(slider_label)
        slider_layout.addWidget(self.freq_slider)
        slider_layout.addWidget(self.freq_display)

        # 方波配置
        waveform_layout = QFormLayout()
        self.wave_offset = QLineEdit("1")  # 默认偏移量
        self.wave_amplitude = QLineEdit("1")  # 默认幅值
        self.wave_period = QLineEdit("1")  # 默认周期
        self.wave_button = QPushButton("Generate Square Wave")
        self.wave_button.setCheckable(True)
        self.wave_button.clicked.connect(self.toggle_waveform)
        self.wave_period.textChanged.connect(self.update_period)


        waveform_layout.addRow("Offset (0-3V):", self.wave_offset)
        waveform_layout.addRow("Amplitude (0-3V):", self.wave_amplitude)
        waveform_layout.addRow("Period (s):", self.wave_period)
        waveform_layout.addRow(self.wave_button)

        # Output log
        self.log = QTextEdit()
        self.log.setReadOnly(True)

        # Add layouts to the main layout
        self.layout.addLayout(button_layout)
        self.layout.addLayout(slider_layout)
        self.layout.addLayout(waveform_layout)
        self.layout.addWidget(self.log)

        self.setLayout(self.layout)

        # Thread for continuous output
        self.thread = DOThread()
        self.thread.log_signal.connect(self.log.append)
        self.thread.error_signal.connect(self.show_error)
        self.thread.value_changed_signal.connect(self.update_buttons_from_thread_value)  # 连接新信号
        self.thread.start()  # Start thread immediately to keep it running


    def update_buttons_from_thread_value(self, value):
        """根据线程的 current_value 更新按钮状态"""
        # Bit 7 表示开始/结束
        start_bit = (value & 0b10000000) >> 7
        self.buttons[0].setChecked(bool(start_bit))
        self.buttons[0].setStyleSheet(self.get_button_style(bool(start_bit)))

        # Bit 5 和 Bit 6 表示电压值
        amplitude_bits = (value & 0b01100000) >> 5
        self.buttons[1].setChecked(bool(amplitude_bits & 0b10))
        self.buttons[2].setChecked(bool(amplitude_bits & 0b01))
        self.buttons[1].setStyleSheet(self.get_button_style(bool(amplitude_bits & 0b10)))
        self.buttons[2].setStyleSheet(self.get_button_style(bool(amplitude_bits & 0b01)))

        # Bit 0-4 表示频率值
        frequency_bits = value & 0b00011111
        for i in range(5):
            bit_value = (frequency_bits >> (4 - i)) & 1
            self.buttons[i + 3].setChecked(bool(bit_value))
            self.buttons[i + 3].setStyleSheet(self.get_button_style(bool(bit_value)))

    def toggle_waveform(self):
        """切换方波输出状态"""
        if self.wave_button.isChecked():

            try:
                offset = float(self.wave_offset.text())
                amplitude = float(self.wave_amplitude.text())
                period = float(self.wave_period.text())
                if period <= 0:
                    raise ValueError("Period must be greater than 0!")

                if not (0 <= offset <= 3 and 0 <= amplitude <= 3):
                    raise ValueError("Offset and Amplitude must be between 0 and 3V!")

                frequency = 1 / period
                if not (1 <= frequency <= 31):
                    raise ValueError("Frequency must be between 1 and 31 Hz!")

                self.freq_slider.setValue(int(round(frequency)))  # 设置滑条同步
                self.freq_display.setText(f"{int(round(frequency))} Hz")

                # 设置方波参数并启动
                self.thread.set_waveform(True, offset=offset, amplitude=amplitude, frequency=frequency)
                self.thread.running = True  # 确保线程运行状态为True
                self.auto_output_mode = True
                self.update_buttons_enabled(False)  # 禁用手动控制按钮
                self.wave_offset.setEnabled(False)
                self.wave_amplitude.setEnabled(False)
                self.wave_period.setEnabled(True)  # 启用周期输入框

                self.log.append("Square wave output started.")
            except ValueError as e:
                QMessageBox.warning(self, "Invalid Input", str(e))
                self.wave_button.setChecked(False)
        else:
            # 停止方波输出
            self.thread.set_waveform(False)
            self.thread.running = False  # 停止线程运行
            self.auto_output_mode = False
            self.update_buttons_enabled(True)  # 启用手动控制按钮
            self.wave_offset.setEnabled(True)
            self.wave_amplitude.setEnabled(True)
            self.wave_period.setEnabled(True)

            self.log.append("Square wave output stopped.")

    def update_value(self):
        """Update the current value based on button states (manual control)"""
        if self.auto_output_mode:
            return  # 自动输出模式下禁用手动调整

        current_value = 0
        for i, btn in enumerate(self.buttons):
            if btn.isChecked():
                current_value |= (1 << (7 - i))

        for btn in self.buttons:
            btn.setStyleSheet(self.get_button_style(btn.isChecked()))

        self.thread.set_value(current_value)

        # Update frequency bits
        frequency = current_value & 0b11111
        self.freq_slider.setValue(frequency)
        self.thread.set_frequency(frequency)

        # Start or stop output based on Bit 7
        if current_value & 0b10000000:
            self.thread.start_output()
        else:
            self.thread.stop_output()

    def update_frequency(self):
        """Update frequency using the slider (manual control)"""
        frequency = self.freq_slider.value()
        self.freq_display.setText(f"{frequency} Hz")

        # 如果在自动输出模式下，调整波形频率
        if self.auto_output_mode:
            if frequency > 0:  # 频率必须为正值
                period = 1 / frequency
                self.wave_period.setText(f"{period:.2f}")  # 更新周期显示
                self.thread.set_frequency(frequency)  # 更新线程中的频率

            return  # 自动输出模式下不需要进一步手动控制

        # 手动控制模式：更新线程值和频率
        current_value = self.thread.current_value & 0b10000000
        new_value = current_value | (frequency & 0b11111)
        self.thread.set_value(new_value)

        for i in range(5):
            bit_value = (frequency >> (4 - i)) & 1
            self.buttons[i + 3].setChecked(bit_value)
            self.buttons[i + 3].setStyleSheet(self.get_button_style(bit_value))

        self.thread.set_frequency(frequency)

    def update_period(self):
        """Update period when the wave period input box is changed"""
        try:
            period = self.wave_period.text()
            if period != '':
                period = float(period)


                if period != 0 :

                    frequency = int(round(1 / period))  # 根据周期计算频率
                    if 0 <= frequency <= 31:
                        self.freq_slider.setValue(frequency)  # 更新滑条值
                        self.freq_display.setText(f"{frequency} Hz")
                        self.thread.set_frequency(frequency)  # 更新线程中的频率

                        # 自动模式下，立即应用新的频率值
                        if self.auto_output_mode:
                            self.thread.set_frequency(frequency)
                    else:
                        raise ValueError("Calculated frequency is out of range!")

        except ValueError as e:
            QMessageBox.warning(self, "Invalid Input", str(e))

    def update_buttons_enabled(self, enabled):
        """Enable or disable manual buttons"""
        for btn in self.buttons:
            btn.setEnabled(enabled)

    def show_error(self, message):
        QMessageBox.critical(self, "Error", message)

    def stop_thread(self):
        self.thread.stop_output()

    def resume_thread(self):
        if not self.thread.running:
            self.thread.start_output()

    def get_button_style(self, active):
        if active:
            return "background-color: green; border-radius: 20px; border: 2px solid black;"
        else:
            return "background-color: lightgray; border-radius: 20px; border: 2px solid black;"

class DIThread(QThread):
    data_signal = pyqtSignal(int)

    def __init__(self):
        super().__init__()
        self.running = False

    def start_reading(self):
        self.running = True

    def stop_reading(self):
        self.running = False

    def run(self):
        instantDiCtrl = InstantDiCtrl(deviceDescription)
        instantDiCtrl.loadProfile = profilePath
        try:
            while True:
                if self.running:
                    ret, data = instantDiCtrl.readAny(0, 1)
                    if BioFailed(ret):
                        continue
                    self.data_signal.emit(data[0])  # 发射接收到的值
                    self.msleep(10)
                else:

                    self.msleep(50)  # Wait a little to reduce resource usage
                    continue

        finally:
            instantDiCtrl.dispose()


class DI_Tab(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()

        # 状态显示区
        self.status_label = QLabel("DI Port Status:")
        self.status_log = QTextEdit()
        self.status_log.setReadOnly(True)

        # 图形显示区
        self.plot_label = QLabel("Voltage vs Time Plot:")
        self.figure = Figure(figsize=(5, 3))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title("Voltage vs Time")
        self.ax.set_xlabel("Time (s)")
        self.ax.set_ylabel("Voltage (V)")
        self.ax.set_ylim(0, 3)
        self.ax.grid(True)

        # 创建用于动态更新的Line2D对象
        self.line, = self.ax.plot([], [], label="Voltage", color="blue")
        self.ax.legend()

        # 滑条控制区
        self.slider_label = QLabel("X-Axis Range (s):")
        self.x_axis_slider = QSlider(Qt.Horizontal)
        self.x_axis_slider.setMinimum(5)  # 对应0.5秒，乘10
        self.x_axis_slider.setMaximum(100)  # 对应10秒，乘10
        self.x_axis_slider.setValue(100)  # 默认10秒
        self.x_axis_slider.setTickInterval(5)
        self.x_axis_slider.setTickPosition(QSlider.TicksBelow)

        self.x_axis_spinbox = QSpinBox()
        self.x_axis_spinbox.setMinimum(1)  # 显示最小值为0.5秒
        self.x_axis_spinbox.setMaximum(10)
        self.x_axis_spinbox.setValue(10)  # 初始值
        self.x_axis_spinbox.setSingleStep(1)

        # 滑条和数值框联动
        self.x_axis_slider.valueChanged.connect(self.update_x_axis_range)
        self.x_axis_slider.valueChanged.connect(lambda v: self.x_axis_spinbox.setValue(v // 10))
        self.x_axis_spinbox.valueChanged.connect(lambda v: self.x_axis_slider.setValue(v * 10))

        # 方形按钮区
        button_layout = QHBoxLayout()
        self.buttons = []
        for i in range(8):
            btn = QPushButton(f"{i}")
            btn.setCheckable(True)
            btn.setFixedSize(40, 40)
            btn.setStyleSheet(self.get_button_style(False))
            self.buttons.append(btn)
            button_layout.addWidget(btn)

        # 布局排列
        self.layout.addWidget(self.status_label)
        self.layout.addWidget(self.status_log)
        self.layout.addWidget(self.plot_label)
        self.layout.addWidget(self.canvas)

        # 滑条布局
        slider_layout = QHBoxLayout()
        slider_layout.addWidget(self.slider_label)
        slider_layout.addWidget(self.x_axis_slider)
        slider_layout.addWidget(self.x_axis_spinbox)
        self.layout.addLayout(slider_layout)

        self.layout.addLayout(button_layout)
        self.setLayout(self.layout)

        # 数据存储
        self.time_data = []
        self.voltage_data = []

        # 线程处理
        self.thread = DIThread()
        self.thread.data_signal.connect(self.handle_thread_data)
        self.thread.start()  # 启动线程

        # 定时器定期刷新绘图
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_plot)
        self.timer.start(10)  # 每 10 毫秒刷新一次

    def handle_thread_data(self, value):
        """处理线程信号，仅在线程运行时调用process_data"""
        if self.thread.running:
            self.process_data(value)

    def process_data(self, value):
        """处理接收到的数据"""
        # 更新方形按钮状态
        start_bit = (value & 0b10000000) >> 7
        self.buttons[0].setChecked(bool(start_bit))
        self.buttons[0].setStyleSheet(self.get_button_style(bool(start_bit)))

        voltage_bits = (value & 0b01100000) >> 5
        self.buttons[1].setChecked(bool(voltage_bits & 0b10))
        self.buttons[2].setChecked(bool(voltage_bits & 0b01))
        self.buttons[1].setStyleSheet(self.get_button_style(bool(voltage_bits & 0b10)))
        self.buttons[2].setStyleSheet(self.get_button_style(bool(voltage_bits & 0b01)))

        frequency_bits = value & 0b00011111
        for i in range(5):
            bit_value = (frequency_bits >> (4 - i)) & 1
            self.buttons[i + 3].setChecked(bool(bit_value))
            self.buttons[i + 3].setStyleSheet(self.get_button_style(bool(bit_value)))

        # 记录电压值和时间
        voltage = voltage_bits
        current_time = time.time()
        if len(self.time_data) > 0:
            current_time -= self.time_data[0]  # 时间归一化到从0开始

        self.time_data.append(current_time)
        self.voltage_data.append(voltage)

        # 更新日志
        self.status_log.append(f"Data: {value:08b} | Voltage: {voltage} V | Time: {current_time:.2f} s")

    def update_plot(self):
        """高效更新绘图"""
        if len(self.time_data) > 0:
            x_range = self.x_axis_slider.value() / 10  # 获取滑条设定的范围
            x_min = max(0, self.time_data[-1] - x_range)
            x_max = self.time_data[-1]

            self.line.set_data(self.time_data, self.voltage_data)
            self.ax.set_xlim(x_min, x_max)

        self.canvas.draw()

    def update_x_axis_range(self, value):
        """更新横轴显示范围"""
        self.update_plot()

    def get_button_style(self, active):
        if active:
            return "background-color: green; border-radius: 20px; border: 2px solid black;"
        else:
            return "background-color: lightgray; border-radius: 20px; border: 2px solid black;"

    def stop_thread(self):
        self.thread.stop_reading()

    def resume_thread(self):
        self.thread.start_reading()



if __name__ == "__main__":
    app = QApplication(sys.argv)
    main_window = MainApp()
    main_window.show()
    sys.exit(app.exec_())
