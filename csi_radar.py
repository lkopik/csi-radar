"""CSI-радар: обнаружение людей по Wi-Fi CSI (ESP32-S3, примеры esp-csi get-started).

Запуск:
    python csi_radar.py --port COM10        # живые данные с платы-приёмника
    python csi_radar.py --demo              # синтетические данные без плат

Индексы:
    движение    = средний коэффициент вариации амплитуд поднесущих за окно 1 с
                  (каждый пакет нормирован на своё среднее — убирает AGC);
    присутствие = 1 − корреляция текущего профиля канала с профилем пустой комнаты.
"""
import argparse
import csv
import json
import math
import queue
import re
import sys
import threading
import time
from collections import deque
from pathlib import Path

import numpy as np
import pyqtgraph as pg
from PyQt6 import QtCore, QtGui, QtWidgets

HERE = Path(__file__).resolve().parent
CALIB_FILE = HERE / "calibration.json"
LABELS = ["empty", "walk", "stand", "sit", "wave"]

RATE_HZ = 100            # ожидаемая частота пакетов
WINDOW_S = 1.0           # окно для индексов
BUFFER_PKTS = 1000       # ~10 с истории
WATERFALL_PKTS = 400     # строк в «водопаде»
HISTORY_S = 30           # длина графиков индексов
CALIB_COUNTDOWN_S = 5
CALIB_DURATION_S = 10
HOLD_S = 1.5             # гистерезис: сколько держать состояние после спада
OFF_RATIO = 0.6          # гистерезис: выключение при фон + 0.6 × (порог − фон)

# Пороги без калибровки (только для движения; присутствию нужна калибровка)
DEFAULT_MOTION_THR = 0.08
# Нижняя граница порога присутствия: в пустой комнате индекс 0.0001–0.006,
# человек на линии между платами даёт 0.07–0.17 (замер 28.10)
PRESENCE_MIN_THR = 0.01

CSI_RE = re.compile(r'"\[([-\d,\s]+)\]"')


# ---------------------------------------------------------------- источники данных

def parse_csi_line(line):
    """Возвращает (rssi, амплитуды) или None. Данные: [imag, real, imag, real, ...]."""
    if not line.startswith("CSI_DATA"):
        return None
    m = CSI_RE.search(line)
    if not m:
        return None
    try:
        raw = np.array([int(x) for x in m.group(1).split(",") if x.strip()], dtype=np.float32)
        rssi = int(line.split(",", 4)[3])
    except ValueError:
        return None
    if raw.size < 2 or raw.size % 2:
        return None
    imag, real = raw[0::2], raw[1::2]
    return rssi, np.hypot(real, imag)


class SerialSource(threading.Thread):
    def __init__(self, port, baud, out_q):
        super().__init__(daemon=True)
        self.port, self.baud, self.q = port, baud, out_q
        self.error = None
        self.stop_flag = threading.Event()

    def run(self):
        import serial
        try:
            ser = serial.Serial()
            ser.port, ser.baudrate, ser.timeout = self.port, self.baud, 1
            ser.dtr = False   # не дёргать RESET/BOOT платы при открытии
            ser.rts = False
            ser.open()
        except Exception as e:  # noqa: BLE001
            self.error = f"Не удалось открыть {self.port}: {e}"
            return
        buf = b""
        while not self.stop_flag.is_set():
            try:
                chunk = ser.read(ser.in_waiting or 1)
            except Exception as e:  # noqa: BLE001
                self.error = f"Ошибка порта {self.port}: {e}"
                break
            if not chunk:
                continue
            buf += chunk
            *lines, buf = buf.split(b"\n")
            for raw in lines:
                parsed = parse_csi_line(raw.decode("ascii", "ignore").strip())
                if parsed:
                    self.q.put((time.time(), *parsed))
        ser.close()


class DemoSource(threading.Thread):
    """Синтетический CSI: пусто → ходьба → стоит → машет → пусто ..."""
    SCRIPT = [("empty", 10), ("walk", 8), ("stand", 8), ("wave", 6), ("empty", 8)]

    def __init__(self, out_q, n_sub=114):
        super().__init__(daemon=True)
        self.q, self.n = out_q, n_sub
        self.stop_flag = threading.Event()
        rng = np.random.default_rng(1)
        k = np.arange(n_sub)
        self.base = 20 + 6 * np.sin(k / 9) + 4 * np.cos(k / 23 + 1) + rng.normal(0, 1, n_sub)
        self.body = 1 + 0.25 * np.sin(k / 6 + 2) * np.exp(-((k - 70) / 30) ** 2)
        self.rng = rng
        self.scene = "empty"
        self.force_empty = False    # во время калибровки — пустая комната

    def run(self):
        t0 = time.time()
        total = sum(d for _, d in self.SCRIPT)
        k = np.arange(self.n)
        while not self.stop_flag.is_set():
            t = time.time() - t0
            pos = t % total
            for scene, dur in self.SCRIPT:
                if pos < dur:
                    break
                pos -= dur
            if self.force_empty:
                scene = "empty"
            self.scene = scene
            amp = self.base.copy()
            if scene in ("stand", "wave", "walk"):
                amp *= self.body
            if scene == "walk":
                amp *= 1 + 0.18 * np.sin(k / 4 + 7 * t) * np.sin(2.1 * t)
            elif scene == "wave":
                amp *= 1 + 0.08 * np.sin(k / 5 + 11 * t)
            elif scene == "stand":
                amp *= 1 + 0.01 * np.sin(k / 5 + 1.5 * t)   # дыхание
            agc = 1 + 0.15 * math.sin(t / 3)               # имитация AGC
            amp = amp * agc * (1 + self.rng.normal(0, 0.015, self.n))
            self.q.put((time.time(), -45 + int(self.rng.normal(0, 1)), amp.astype(np.float32)))
            time.sleep(1 / RATE_HZ)


# ---------------------------------------------------------------- обработка

class Detector:
    def __init__(self):
        self.times = deque(maxlen=BUFFER_PKTS)
        self.amps = deque(maxlen=BUFFER_PKTS)
        self.n_sub = None
        self.mask = None
        self.calib = None           # dict: profile, motion_mu/sd, presence_mu/sd
        self.sensitivity = 5
        self.motion_on = False
        self.presence_on = False
        self._motion_last_high = 0.0
        self._presence_last_high = 0.0
        self.load_calibration()

    # --- данные
    def add(self, t, amp):
        if amp.size != self.n_sub:
            # редкие пакеты другой длины пропускаем; если новая длина держится
            # 50 пакетов подряд (перепрошивка и т.п.) — начинаем буфер заново
            self._odd = self._odd + 1 if getattr(self, "_odd_size", None) == amp.size else 1
            self._odd_size = amp.size
            if self.n_sub is not None and self._odd < 50:
                return
            self.n_sub = amp.size
            self.times.clear()
            self.amps.clear()
            self.mask = None
        self._odd = 0
        self.times.append(t)
        self.amps.append(amp)

    def matrix(self, last_n=None):
        if not self.amps:
            return None
        arr = np.array(list(self.amps)[-last_n:] if last_n else list(self.amps))
        return arr

    def update_mask(self):
        """Отбрасываем нулевые/защитные поднесущие (почти нулевая амплитуда)."""
        arr = self.matrix(300)
        if arr is None or len(arr) < 20:
            return
        mean = arr.mean(axis=0)
        med = np.median(mean[mean > 0]) if np.any(mean > 0) else 0
        self.mask = mean > 0.15 * med

    def window(self):
        """Нормированные амплитуды последней секунды (только валидные поднесущие)."""
        if self.mask is None or len(self.times) < 10:
            return None
        t_end = self.times[-1]
        n = 0
        for t in reversed(self.times):
            if t_end - t > WINDOW_S:
                break
            n += 1
        if n < 10:
            return None
        arr = self.matrix(n)[:, self.mask]
        arr = arr / np.maximum(arr.mean(axis=1, keepdims=True), 1e-6)   # убираем AGC
        return arr

    @staticmethod
    def motion_index(win):
        mu = win.mean(axis=0)
        sd = win.std(axis=0)
        return float(np.mean(sd / np.maximum(mu, 1e-6)))

    @staticmethod
    def presence_index(win, ref):
        prof = win.mean(axis=0)
        if ref is None or len(ref) != len(prof):
            return None
        c = np.corrcoef(prof, ref)[0, 1]
        return float(1 - c) if np.isfinite(c) else None

    # --- пороги
    def k(self):
        # чувствительность 1..10 → множитель σ: 10 → 1.5σ, 1 → 9.6σ
        return 1.5 + (10 - self.sensitivity) * 0.9

    def thresholds(self):
        scale = 1.6 - self.sensitivity * 0.1    # для режима без калибровки
        if not self.calib:
            return DEFAULT_MOTION_THR * scale, None
        c, k = self.calib, self.k()
        m_thr = max(c["motion_mu"] + k * c["motion_sd"], c["motion_mu"] * 1.3)
        p_thr = max(c["presence_mu"] + k * c["presence_sd"], c["presence_mu"] * 1.5, PRESENCE_MIN_THR)
        return m_thr, p_thr

    def step(self, now):
        """Возвращает (motion, presence, m_thr, p_thr) и обновляет состояния с гистерезисом."""
        win = self.window()
        if win is None:
            return None
        ref = np.array(self.calib["profile"]) if self.calib else None
        motion = self.motion_index(win)
        presence = self.presence_index(win, ref)
        m_thr, p_thr = self.thresholds()

        m_base = self.calib["motion_mu"] if self.calib else 0.0
        self.motion_on, self._motion_last_high = self._hyst(
            motion, m_thr, m_base, self.motion_on, self._motion_last_high, now)
        if presence is not None and p_thr is not None:
            self.presence_on, self._presence_last_high = self._hyst(
                presence, p_thr, self.calib["presence_mu"], self.presence_on,
                self._presence_last_high, now)
        else:
            self.presence_on = False
        return motion, presence, m_thr, p_thr

    @staticmethod
    def _hyst(value, thr, base, state, last_high, now):
        if value >= thr:
            return True, now
        off_thr = base + OFF_RATIO * (thr - base)
        if state and (value >= off_thr or now - last_high < HOLD_S):
            return True, last_high
        return False, last_high

    # --- калибровка
    def finish_calibration(self, samples):
        """samples: список окон (нормированные матрицы) за 10 с пустой комнаты."""
        # медиана и MAD вместо среднего и σ: случайный проход человека или
        # всплеск в начале калибровки не раздувают пороги
        profile = np.median(np.vstack(samples), axis=0)
        motions = np.array([self.motion_index(w) for w in samples])
        presences = np.array([self.presence_index(w, profile) for w in samples])

        def robust(x):
            med = float(np.median(x))
            return med, float(1.4826 * np.median(np.abs(x - med)))
        m_mu, m_sd = robust(motions)
        p_mu, p_sd = robust(presences)
        self.calib = {
            "n_sub": int(self.n_sub),
            "mask": self.mask.astype(int).tolist(),
            "profile": profile.tolist(),
            "motion_mu": m_mu,
            "motion_sd": m_sd,
            "presence_mu": p_mu,
            "presence_sd": p_sd,
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        CALIB_FILE.write_text(json.dumps(self.calib, indent=1), encoding="utf-8")

    def load_calibration(self):
        try:
            self.calib = json.loads(CALIB_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.calib = None

    def calibration_fits(self):
        """Калибровка подходит к текущему потоку (то же число поднесущих и маска)."""
        if not self.calib or self.n_sub != self.calib.get("n_sub"):
            return False
        mask = np.array(self.calib["mask"], dtype=bool)
        if mask.size != self.n_sub:
            return False
        self.mask = mask
        return True


# ---------------------------------------------------------------- интерфейс

STATUS_STYLE = {
    "ПУСТО": "#2e7d32",
    "ДВИЖЕНИЕ": "#c62828",
    "ЧЕЛОВЕК РЯДОМ": "#ef6c00",
    "НЕТ ДАННЫХ": "#616161",
}


class RadarWindow(QtWidgets.QMainWindow):
    def __init__(self, source, q, port_label, demo):
        super().__init__()
        self.source, self.q, self.demo = source, q, demo
        self.det = Detector()
        self.calib_fitted = False
        self.calib_phase = None      # None | ("countdown", t_end) | ("collect", t_end)
        self.calib_samples = []
        self.rec_file = None
        self.rec_writer = None
        self.rec_count = 0
        self.pkt_times = deque(maxlen=500)
        self.last_rssi = None
        self.hist = deque(maxlen=HISTORY_S * 20)   # (t, motion, presence, m_thr, p_thr)
        self.t0 = time.time()
        # лог индексов (2 раза в секунду) — для разбора после демонстрации
        self.log = open(HERE / "radar_log.csv", "w", newline="", encoding="utf-8")
        self.log_w = csv.writer(self.log)
        self.log_w.writerow(["time", "motion", "presence", "motion_thr", "presence_thr", "status", "pkt_rate"])
        self._last_log = 0.0

        self.setWindowTitle(f"CSI-радар — {port_label}")
        self.resize(1400, 900)
        pg.setConfigOptions(antialias=True, background="w", foreground="k")

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)

        # статус
        self.status = QtWidgets.QLabel("НЕТ ДАННЫХ")
        self.status.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        f = QtGui.QFont()
        f.setPointSize(48)
        f.setBold(True)
        self.status.setFont(f)
        self.status.setMinimumHeight(120)
        root.addWidget(self.status)

        # панель управления
        bar = QtWidgets.QHBoxLayout()
        self.btn_calib = QtWidgets.QPushButton("Калибровка (пустая комната)")
        self.btn_calib.clicked.connect(self.start_calibration)
        bar.addWidget(self.btn_calib)

        bar.addWidget(QtWidgets.QLabel("Чувствительность:"))
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.slider.setRange(1, 10)
        self.slider.setValue(5)
        self.slider.setFixedWidth(180)
        self.slider.valueChanged.connect(self.on_sens)
        bar.addWidget(self.slider)
        self.sens_label = QtWidgets.QLabel("5")
        bar.addWidget(self.sens_label)

        bar.addSpacing(30)
        bar.addWidget(QtWidgets.QLabel("Метка:"))
        self.label_box = QtWidgets.QComboBox()
        self.label_box.addItems(LABELS)
        bar.addWidget(self.label_box)
        self.btn_rec = QtWidgets.QPushButton("● Запись CSV")
        self.btn_rec.setCheckable(True)
        self.btn_rec.toggled.connect(self.toggle_record)
        bar.addWidget(self.btn_rec)

        bar.addStretch(1)
        self.info = QtWidgets.QLabel("")
        bar.addWidget(self.info)
        root.addLayout(bar)

        # графики
        grid = pg.GraphicsLayoutWidget()
        root.addWidget(grid, 1)

        self.p_wf = grid.addPlot(row=0, col=0, title="Водопад амплитуд поднесущих")
        self.p_wf.setLabel("bottom", "поднесущая")
        self.p_wf.setLabel("left", "пакеты (новые сверху)")
        self.wf_img = pg.ImageItem(axisOrder="row-major")
        self.wf_img.setColorMap(pg.colormap.get("viridis"))
        self.p_wf.addItem(self.wf_img)
        self.p_wf.invertY(True)

        self.p_prof = grid.addPlot(row=0, col=1, title="Профиль канала (нормированный)")
        self.p_prof.setLabel("bottom", "поднесущая")
        self.p_prof.addLegend()
        self.c_prof = self.p_prof.plot(pen=pg.mkPen("#1565c0", width=2), name="сейчас")
        self.c_ref = self.p_prof.plot(pen=pg.mkPen("#9e9e9e", width=2, style=QtCore.Qt.PenStyle.DashLine),
                                      name="пустая комната")

        self.p_mot = grid.addPlot(row=1, col=0, title="Индекс движения (CV за 1 с)")
        self.p_mot.setLabel("bottom", "с")
        self.c_mot = self.p_mot.plot(pen=pg.mkPen("#c62828", width=2))
        self.c_mot_thr = self.p_mot.plot(pen=pg.mkPen("k", width=1, style=QtCore.Qt.PenStyle.DashLine))

        self.p_pres = grid.addPlot(row=1, col=1, title="Индекс присутствия (1 − корреляция с пустой комнатой)")
        self.p_pres.setLabel("bottom", "с")
        self.c_pres = self.p_pres.plot(pen=pg.mkPen("#ef6c00", width=2))
        self.c_pres_thr = self.p_pres.plot(pen=pg.mkPen("k", width=1, style=QtCore.Qt.PenStyle.DashLine))

        self.timer = QtCore.QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(50)
        self.set_status("НЕТ ДАННЫХ")

    # --- элементы управления
    def on_sens(self, v):
        self.det.sensitivity = v
        self.sens_label.setText(str(v))

    def start_calibration(self):
        if self.det.mask is None:
            QtWidgets.QMessageBox.warning(self, "Калибровка", "Пока нет данных с приёмника.")
            return
        self.calib_phase = ("countdown", time.time() + CALIB_COUNTDOWN_S)
        self.calib_samples = []
        self.btn_calib.setEnabled(False)

    def toggle_record(self, on):
        if on:
            name = HERE / f"csi_{time.strftime('%Y%m%d_%H%M%S')}.csv"
            self.rec_file = open(name, "w", newline="", encoding="utf-8")
            self.rec_writer = csv.writer(self.rec_file)
            self.rec_header_done = False
            self.rec_count = 0
            self.rec_name = name.name
            self.btn_rec.setText("■ Стоп записи")
        else:
            if self.rec_file:
                self.rec_file.close()
            self.rec_file = self.rec_writer = None
            self.btn_rec.setText("● Запись CSV")

    def set_status(self, text, sub=""):
        color = STATUS_STYLE.get(text, "#424242")
        self.status.setText(text if not sub else f"{text}\n{sub}")
        self.status.setStyleSheet(f"color: white; background: {color}; border-radius: 12px;")

    # --- главный цикл
    def tick(self):
        now = time.time()
        got = 0
        while True:
            try:
                t, rssi, amp = self.q.get_nowait()
            except queue.Empty:
                break
            got += 1
            prev_n = self.det.n_sub
            self.det.add(t, amp)
            if self.det.n_sub != prev_n:
                self.calib_fitted = False
            self.pkt_times.append(t)
            self.last_rssi = rssi
            if self.rec_writer:
                if not self.rec_header_done:
                    self.rec_writer.writerow(["time", "label", "rssi"] + [f"a{i}" for i in range(amp.size)])
                    self.rec_header_done = True
                self.rec_writer.writerow([f"{t:.3f}", self.label_box.currentText(), rssi]
                                         + [f"{x:.1f}" for x in amp])
                self.rec_count += 1

        err = getattr(self.source, "error", None)
        if err:
            self.set_status("НЕТ ДАННЫХ", err)
            return
        if not self.det.amps:
            return

        if not self.calib_fitted:
            if self.det.calibration_fits():
                self.calib_fitted = True
            elif self.det.mask is None or len(self.det.amps) % 100 == 0:
                self.det.update_mask()
                if self.det.calib and self.det.n_sub != self.det.calib.get("n_sub"):
                    self.det.calib = None   # калибровка от другого формата пакетов

        res = self.det.step(now)
        self.update_plots(res, now)
        self.update_calibration(now)
        self.update_status(res, now)

    def update_calibration(self, now):
        if self.demo:
            self.source.force_empty = self.calib_phase is not None
        if not self.calib_phase:
            return
        phase, t_end = self.calib_phase
        if phase == "countdown":
            if now >= t_end:
                self.calib_phase = ("collect", now + CALIB_DURATION_S)
                # первое окно 1 с ещё содержит пакеты отсчёта — пропускаем
                self._last_sample = now + WINDOW_S - 0.5
        else:
            if now - self._last_sample >= 0.5:      # окно 1 с каждые 0.5 с
                w = self.det.window()
                if w is not None:
                    self.calib_samples.append(w)
                self._last_sample = now
            if now >= t_end:
                self.calib_phase = None
                self.btn_calib.setEnabled(True)
                if len(self.calib_samples) >= 5:
                    self.det.finish_calibration(self.calib_samples)
                    self.calib_fitted = True
                else:
                    QtWidgets.QMessageBox.warning(self, "Калибровка", "Мало данных, повторите.")

    def update_status(self, res, now):
        if self.calib_phase:
            phase, t_end = self.calib_phase
            left = math.ceil(t_end - now)
            if phase == "countdown":
                self.set_status(f"КАЛИБРОВКА через {left}", "выйдите из зоны между платами")
            else:
                self.status.setText(f"КАЛИБРОВКА… {left} с\nне двигайтесь, в зоне никого")
                self.status.setStyleSheet("color: white; background: #1565c0; border-radius: 12px;")
            return
        if res is None:
            self.set_status("НЕТ ДАННЫХ", "ожидание пакетов…")
            return
        if self.det.motion_on:
            self.set_status("ДВИЖЕНИЕ")
        elif self.det.presence_on:
            self.set_status("ЧЕЛОВЕК РЯДОМ")
        else:
            self.set_status("ПУСТО", "" if self.det.calib else "нажмите «Калибровка» для детекции присутствия")

    def update_plots(self, res, now):
        # водопад
        arr = self.det.matrix(WATERFALL_PKTS)
        if arr is not None and self.det.mask is not None:
            arr = arr[:, self.det.mask]
            norm = arr / np.maximum(arr.mean(axis=1, keepdims=True), 1e-6)
            self.wf_img.setImage(norm[::-1], autoLevels=False, levels=(0.2, 2.0))
            # профиль
            win = self.det.window()
            if win is not None:
                self.c_prof.setData(win.mean(axis=0))
            if self.det.calib and self.calib_fitted:
                self.c_ref.setData(np.array(self.det.calib["profile"]))
            else:
                self.c_ref.setData([])

        if res is not None:
            motion, presence, m_thr, p_thr = res
            self.hist.append((now - self.t0, motion,
                              np.nan if presence is None else presence,
                              m_thr, np.nan if p_thr is None else p_thr))
        if self.hist:
            h = np.array(self.hist)
            self.c_mot.setData(h[:, 0], h[:, 1])
            self.c_mot_thr.setData(h[:, 0], h[:, 3])
            ok = np.isfinite(h[:, 2])
            self.c_pres.setData(h[ok, 0], h[ok, 2])
            ok = np.isfinite(h[:, 4])
            self.c_pres_thr.setData(h[ok, 0], h[ok, 4])

        # строка состояния
        rate = 0.0
        if len(self.pkt_times) > 1:
            span = self.pkt_times[-1] - self.pkt_times[0]
            rate = (len(self.pkt_times) - 1) / span if span > 0 else 0
        n_valid = int(self.det.mask.sum()) if self.det.mask is not None else 0
        parts = [f"{rate:5.0f} пак/с", f"RSSI {self.last_rssi} дБм",
                 f"поднесущих {n_valid}/{self.det.n_sub}",
                 "калибровка: " + (self.det.calib["created"] if self.det.calib and self.calib_fitted else "нет")]
        if self.demo:
            parts.append(f"ДЕМО: сцена «{self.source.scene}»")
        if self.rec_writer:
            parts.append(f"запись {self.rec_name}: {self.rec_count}")
        self.info.setText("   |   ".join(parts))
        if res is not None and now - self._last_log >= 0.5:
            self._last_log = now
            motion, presence, m_thr, p_thr = res
            self.log_w.writerow([f"{now:.2f}", f"{motion:.4f}",
                                 "" if presence is None else f"{presence:.4f}",
                                 f"{m_thr:.4f}", "" if p_thr is None else f"{p_thr:.4f}",
                                 self.status.text().split("\n")[0], f"{rate:.0f}"])
            self.log.flush()

    def closeEvent(self, e):
        self.source.stop_flag.set()
        if self.rec_file:
            self.rec_file.close()
        self.log.close()
        super().closeEvent(e)


def main():
    ap = argparse.ArgumentParser(description="CSI-радар на ESP32-S3")
    ap.add_argument("--port", default="COM10", help="порт платы-приёмника (csi_recv)")
    ap.add_argument("--baud", type=int, default=921600)
    ap.add_argument("--demo", action="store_true", help="синтетические данные без плат")
    args = ap.parse_args()

    q = queue.Queue(maxsize=5000)
    if args.demo:
        src, label = DemoSource(q), "ДЕМО"
    else:
        src, label = SerialSource(args.port, args.baud, q), f"{args.port} @ {args.baud}"
    src.start()

    app = QtWidgets.QApplication(sys.argv)
    w = RadarWindow(src, q, label, args.demo)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
