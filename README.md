# CSI-радар на ESP32-S3

Обнаружение людей по Wi-Fi CSI (Channel State Information) на двух платах ESP32-S3.
Одна плата передаёт 100 пакетов ESP-NOW в секунду, вторая принимает их и выдаёт CSI по UART.
Программа на ПК показывает статус **ПУСТО / ДВИЖЕНИЕ / ЧЕЛОВЕК РЯДОМ**, «водопад» поднесущих,
профиль канала и графики индексов.

## Состав

| Путь | Что это |
|---|---|
| `csi_radar.py` | программа на ПК (PyQt5 + pyqtgraph; Qt 5 работает и на Windows 7) |
| `run_radar.bat`, `run_demo.bat` | запуск двойным щелчком. `run_demo.bat` — демо без плат. `run_radar.bat` — с платой-приёмником: если плата одна, порт берётся сам; если портов несколько, спрашивает (Enter — последний использованный, запоминается в `com_port.txt`); или `run_radar.bat --port COM5`. Сами находят Python и ставят зависимости, при ошибке окно не закрывается |
| `python\` | переносимый Python 3.8 с библиотеками (не в git, см. ниже) |
| `firmware/csi_send`, `firmware/csi_recv` | прошивки: передатчик и приёмник |
| `firmware/build.ps1` | сборка и прошивка через ESP-IDF |
| `packaging/build_exe.ps1` | сборка `dist\CSI_radar.exe` и `dist\CSI_radar_demo.exe` |
| `ВЫСТУПЛЕНИЕ.md` | как расставить платы и что показывать |

## Прошивки

Основаны на примерах [espressif/esp-csi](https://github.com/espressif/esp-csi)
`examples/get-started` (коммит `8633d67`, лицензия Apache-2.0, см. `firmware/LICENSE-esp-csi`).
Адаптированы под **ESP-IDF v6.1**:

- `WIFI_BW_HT20/HT40` → `WIFI_BW20/BW40` (переименовано в IDF 6);
- в приёмнике отключена компенсация усиления `esp_csi_gain_ctrl` — у компонента нет готовой
  библиотеки под IDF 6.1. AGC программа на ПК убирает сама, нормируя каждый пакет.

Сборка и прошивка (target esp32s3):

```powershell
powershell -ExecutionPolicy Bypass -File firmware\build.ps1 csi_send COM9
powershell -ExecutionPolicy Bypass -File firmware\build.ps1 csi_recv COM10
```

Приёмник печатает строки `CSI_DATA,...,len,first_word,"[imag,real,...]"` на 921600 бод
(канал 11, HT40, 192 поднесущие).

## Программа на ПК

### Быстрый запуск (в том числе на Windows 7)

Скопировать папку проекта целиком (вместе с `python\` — переносимый Python 3.8 x64 с PyQt5, numpy,
pyserial, pyqtgraph) и запустить `run_radar.bat` или `run_demo.bat`. Ничего устанавливать не нужно;
нужна 64-битная Windows 7 SP1 или новее.

Если папки `python\` нет, .bat ищет окружение `.venv`, затем Python 3.8–3.13 в системе
(`py -3.8` … `py -3.13`, потом `python` в PATH), создаёт `.venv` и ставит зависимости из
`requirements.txt` (при первом запуске нужен интернет). Если `pypi.org` недоступен, передайте зеркало:
добавьте `-i https://mirrors.aliyun.com/pypi/simple` в строку `pip install -r requirements.txt` внутри .bat.
При любой ошибке окно остаётся открытым с описанием.

### Готовые .exe (один файл, без Python и .bat)

`dist\CSI_radar.exe` — с платой: если плата одна, порт берётся сам, иначе программа спрашивает в окне
(или `CSI_radar.exe --port COM5`). `dist\CSI_radar_demo.exe` — демо без платы.
Каждый — один файл ~47 МБ, скопировать на любой ПК с 64-битной Windows 7 SP1 или новее.
Собраны из `python\` (Python 3.8), поэтому совместимы с Windows 7; пересборка:

```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
```

`calibration.json` и `radar_log.csv` пишутся рядом с .exe. В git `dist\` не входит.

### Вручную

```powershell
py -3.8 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python csi_radar.py --port COM10   # живые данные
.venv\Scripts\python csi_radar.py --demo         # синтетические данные
```

- **Движение** — средний коэффициент вариации амплитуд поднесущих за окно 1 с;
  каждый пакет нормирован на своё среднее, чтобы убрать AGC.
- **Присутствие** — 1 − корреляция текущего профиля канала с профилем пустой комнаты.
- **Калибровка** — 5 с отсчёт и 10 с пустой комнаты; пороги считаются по медиане и MAD
  и сохраняются в `calibration.json`. Ползунок чувствительности, гистерезис.
- **Запись CSV** с метками `empty / walk / stand / sit / wave` — для датасета.
- Индексы пишутся в `radar_log.csv` (2 раза в секунду).

## Замер (28.10.2026, платы ~2 м, 74 пак/с)

| Ситуация | Индекс движения | Индекс присутствия |
|---|---|---|
| Пустая зона | ~0,08 | 0,0001–0,006 |
| Ходьба между платами | 0,10–0,35 | — |
| Человек стоит на линии между платами | 0,04–0,06 | 0,07–0,17 |

Пороги после калибровки: движение 0,105, присутствие 0,01.
