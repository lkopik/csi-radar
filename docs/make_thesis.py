"""Тезисы для конференции УрТИСИ СибГУТИ: оформление по «Требованиям к оформлению тезисов».

Запуск: python docs/make_thesis.py  ->  docs/Тезисы_Копотилов_ТЕ-51б.docx
"""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Cm, Pt

OUT = Path(__file__).with_name("Тезисы_Копотилов_ТЕ-51б.docx")

AUTHOR = "Копотилов Л. А., гр. ТЕ-51б"
SUPERVISOR = "Научный руководитель: доцент кафедры МЭС Кусайкин Д. В."
TITLE = "ОБНАРУЖЕНИЕ ЧЕЛОВЕКА ПО ПАРАМЕТРАМ РАДИОКАНАЛА WI-FI (CSI) НА МИКРОКОНТРОЛЛЕРАХ ESP32-S3"
UNIVERSITY = "УрТИСИ СибГУТИ, г. Екатеринбург, Россия"
KEYWORDS = ("Ключевые слова: Wi-Fi, CSI, OFDM, IEEE 802.11n, многолучевое распространение, "
            "интернет вещей, ESP32-S3.")

ANNOTATION = (
    "Аннотация. Рассмотрена возможность использования оценки состояния радиоканала (Channel State "
    "Information, CSI), которую приёмник Wi-Fi вычисляет для демодуляции OFDM-сигнала, в качестве "
    "датчика присутствия и движения человека. Собран макет из двух микроконтроллеров ESP32-S3: "
    "передатчик формирует 100 кадров ESP-NOW в секунду, приёмник выдаёт CSI по 166 поднесущим на "
    "компьютер. Предложены два статистических индекса и выполнен расчёт пропускной способности "
    "тракта передачи данных. Экспериментально показано, что система различает пустое помещение, "
    "движение и неподвижного человека."
)

BODY = [
    "В широкополосном радиоканале сигнал приходит к приёмнику по нескольким лучам с разными "
    "задержками, поэтому его частотная характеристика H(f) неравномерна. Стандарт IEEE 802.11n "
    "использует OFDM, и приёмник по обучающим символам преамбулы оценивает комплексный коэффициент "
    "передачи на каждой поднесущей [1]. Человек перекрывает часть лучей и создаёт новые отражения, "
    "поэтому изменения CSI можно использовать для обнаружения людей без камер [2, 3]. Задача работы — "
    "построить недорогую систему, различающую состояния «пусто», «движение» и «человек рядом».",

    "Макет работает в полосе 40 МГц с центральной частотой 2452 МГц (разнос поднесущих 312,5 кГц, "
    "λ ≈ 12,2 см). Мощность сигнала на входе приёмника −27…−38 дБм при уровне шума −91 дБм, т. е. "
    "отношение сигнал/шум составляет 53–64 дБ. Доплеровский сдвиг отражённого луча при скорости "
    "человека 1 м/с равен 2v/λ ≈ 16 Гц, поэтому по теореме Котельникова частота отсчётов канала "
    "должна быть не ниже 33 Гц.",

    "CSI передаётся на компьютер по UART в текстовом виде, строка занимает L ≈ 1260 байт. "
    "Максимальная частота пакетов при скорости C = 921 600 бит/с и формате 8N1 (10 бит на байт)",

    "FORMULA",

    "Измерения подтвердили расчёт: передатчик формирует 97,5 кадра/с, на компьютер поступает "
    "73–78 пакетов/с, а эфир занят лишь на 0,7 %. Узким местом системы является UART; переход на "
    "двоичный формат увеличит предел до 225 пакетов/с.",

    "Для обработки амплитуды каждого пакета нормируются на среднее, что устраняет действие АРУ. "
    "Индекс движения — средний коэффициент вариации амплитуд поднесущих за 1 с, индекс присутствия — "
    "1 − r, где r — коэффициент корреляции текущего профиля |H(f)| с профилем пустого помещения. "
    "Пороги задаются по медиане и медианному абсолютному отклонению за 10 с калибровки. "
    "В эксперименте индекс движения при ходьбе вырос с 0,08 до 0,35, а индекс присутствия "
    "неподвижного человека — с 0,0002 до 0,1 (в сотни раз выше фона).",

    "Таким образом, CSI стандартного приёмника Wi-Fi пригодна для построения датчиков присутствия "
    "в сетях интернета вещей. Дальнейшее развитие — двоичный протокол передачи и классификатор "
    "действий на записанном наборе данных.",
]

LITERATURE = [
    "IEEE Std 802.11-2020. Wireless LAN Medium Access Control (MAC) and Physical Layer (PHY) "
    "Specifications. — New York: IEEE, 2021. — 4379 p.",
    "Ma Y., Zhou G., Wang S. WiFi Sensing with Channel State Information: A Survey // ACM Computing "
    "Surveys. — 2019. — Vol. 52, No. 3. — P. 1–36.",
    "Espressif Systems. ESP-CSI [Электронный ресурс]. — Режим доступа: "
    "https://github.com/espressif/esp-csi (дата обращения: 28.10.2026).",
]


def set_font(run, size=12, bold=False):
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")


def para(doc, text="", align=WD_ALIGN_PARAGRAPH.JUSTIFY, indent=True, bold=False, size=12):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.alignment = align
    pf.first_line_indent = Cm(1.0) if indent else Cm(0)
    pf.space_before = pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    if text:
        set_font(p.add_run(text), size=size, bold=bold)
    return p


def omml_run(text, italic=True):
    sty = "" if italic else '<m:rPr><m:sty m:val="p"/></m:rPr>'
    return (f'<m:r>{sty}<w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/>'
            f'<w:sz w:val="24"/></w:rPr><m:t xml:space="preserve">{text}</m:t></m:r>')


def add_formula(doc):
    """N_max = C / (10·L) = 921600 / (10·1260) ≈ 73 пакет/с   (1) — номер по правому краю."""
    p = para(doc, indent=False)
    section = doc.sections[0]
    width = section.page_width - section.left_margin - section.right_margin
    p.paragraph_format.tab_stops.add_tab_stop(int(width / 2), WD_TAB_ALIGNMENT.CENTER)
    p.paragraph_format.tab_stops.add_tab_stop(width, WD_TAB_ALIGNMENT.RIGHT)
    set_font(p.add_run("\t"))
    frac = ("<m:f><m:num>{num}</m:num><m:den>{den}</m:den></m:f>")
    math = (
        f'<m:oMath {nsdecls("m", "w")}>'
        + "<m:sSub><m:e>" + omml_run("N") + "</m:e><m:sub>" + omml_run("max", italic=False) + "</m:sub></m:sSub>"
        + omml_run("=")
        + frac.format(num=omml_run("C"), den=omml_run("10") + omml_run("·") + omml_run("L"))
        + omml_run("=")
        + frac.format(num=omml_run("921600", italic=False),
                      den=omml_run("10·1260", italic=False))
        + omml_run("≈73", italic=False)
        + omml_run(" пакет/с", italic=False)
        + "</m:oMath>"
    )
    p._p.append(parse_xml(math))
    set_font(p.add_run("\t(1)"))


def enable_hyphenation(doc):
    settings = doc.settings.element
    for tag, val in (("w:autoHyphenation", "true"), ("w:consecutiveHyphenLimit", "3"),
                     ("w:hyphenationZone", "142")):  # 0,25 см = 142 twip
        el = OxmlElement(tag)
        el.set(qn("w:val"), val)
        settings.append(el)


def main():
    doc = Document()
    s = doc.sections[0]
    s.page_width, s.page_height = Cm(21), Cm(29.7)
    s.top_margin, s.bottom_margin = Cm(1), Cm(1)
    s.left_margin, s.right_margin = Cm(2.5), Cm(1)
    enable_hyphenation(doc)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size = "Times New Roman", Pt(12)

    doc.paragraphs[0]._element.getparent().remove(doc.paragraphs[0]._element) if doc.paragraphs else None
    para(doc, AUTHOR, align=WD_ALIGN_PARAGRAPH.RIGHT, indent=False)
    para(doc, SUPERVISOR, align=WD_ALIGN_PARAGRAPH.RIGHT, indent=False)
    para(doc, "", indent=False)
    para(doc, TITLE, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False, bold=True)
    para(doc, UNIVERSITY, align=WD_ALIGN_PARAGRAPH.CENTER, indent=False)
    para(doc, "", indent=False)
    para(doc, KEYWORDS)
    para(doc, ANNOTATION)
    for text in BODY:
        if text == "FORMULA":
            add_formula(doc)
        else:
            para(doc, text)
    para(doc, "Литература", align=WD_ALIGN_PARAGRAPH.LEFT, indent=False, bold=True)
    for i, ref in enumerate(LITERATURE, 1):
        para(doc, f"{i}. {ref}")
    doc.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
