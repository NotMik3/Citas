# app.py
# -*- coding: utf-8 -*-
# Ejecutar con:  python -m streamlit run app.py
# Requiere:      pip install --upgrade streamlit tzdata pillow

import base64
import calendar as pycal
import inspect
import io
import json
import os
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, datetime, timedelta
from functools import lru_cache
from html import escape
from urllib.parse import quote

import streamlit as st

# ══════════════════════════════════════════════════════════════
# CONFIGURACIÓN TÉCNICA
# (todo lo demás se edita desde la pestaña 🔐 Administración)
# ══════════════════════════════════════════════════════════════
DB_PATH = "citas.db"
ZONA_HORARIA = "America/Monterrey"
CODIGO_PAIS = "52"  # Código de país para teléfonos de 10 dígitos (México)

CFG = {}
CFG_DEFECTO = {
    "nombre": "Rosé Nails Studio",
    "slogan": "Agenda tu cita en 3 pasos sencillos y luce unas uñas de ensueño",
    "whatsapp": "528441234567",
    "direccion": "",
    "maps": "",
    "instagram": "",
    "facebook": "",
    "tiktok": "",
    "web": "",
    "horario": {str(i): {"abierto": i != 6, "ini": "10:00", "fin": "18:00" if i == 5 else "19:00"} for i in range(7)},
    "intervalo": 30,
    "dias_adelante": 60,
    "anticipacion_min": 30,
    "anticipo_modo": "porcentaje",  # ninguno | porcentaje | fijo
    "anticipo_valor": 30,
    "anticipo_obligatorio": True,
    "horas_pago": 24,  # 0 = nunca liberar horarios sin anticipo
    "datos_pago": "Banco: ________\nTitular: ________\nCLABE: ________\nConcepto: tu nombre y fecha de cita",
    "tema": "auto",
    "animacion": True,
}

SERVICIOS_INICIALES = [
    ("Manicure Clásico", "Limpieza, forma, cutícula y esmalte tradicional.", 200, 45, "💅"),
    ("Manicure en Gel", "Esmalte semipermanente de larga duración y brillo.", 320, 60, "✨"),
    ("Uñas Acrílicas", "Extensiones personalizadas con el largo y forma que amas.", 450, 90, "💎"),
    ("Pedicure Spa", "Exfoliación, hidratación y masaje relajante de pies.", 380, 75, "🌸"),
    ("Nail Art Deluxe", "Diseños a mano, cristales y detalles. Se suma a tu servicio.", 150, 30, "🎀"),
    ("Combo Mani + Pedi", "Manicure en gel + pedicure spa a precio especial.", 600, 120, "👑"),
]

DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
DIAS_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
         "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
METODOS_PAGO = ["Transferencia", "Depósito", "Efectivo", "Tarjeta / link de pago", "Otro"]
OPCIONES_HORA = [f"{m // 60:02d}:{m % 60:02d}" for m in range(6 * 60, 23 * 60 + 1, 30)]

# Colores del calendario: (fondo, texto, borde)
COLORES_ESTADO = {
    "baja": ("#E9F7EE", "#2F8F5B", "#CDEBD9"),
    "media": ("#FFF4DB", "#A9741A", "#F5E1AE"),
    "alta": ("#FFE3D8", "#C2502E", "#F8C6B3"),
    "lleno": ("#F8DDE6", "#A33A5C", "#EEBBCB"),
    "cerrado": ("#EFEBED", "#8E8389", "#E3DDE0"),
    "bloqueado": ("#EFEBED", "#8E8389", "#E3DDE0"),
    "pasado": ("#FFFFFF", "#C5BCC1", "#F4EEF1"),
}
ETIQUETA_DIA = {"baja": "Libre", "media": "Se llena", "alta": "🔥 Alta", "lleno": "Lleno"}


# ══════════════════════════════════════════════════════════════
# TEMAS DE TEMPORADA
# ══════════════════════════════════════════════════════════════
def _tema(nombre, etiqueta, emojis, bg, hero, soft, pastel, medio, fuerte, oscuro, titulo, borde, rgb):
    return {
        "nombre": nombre, "etiqueta": etiqueta, "emojis": emojis,
        "c": {"bg1": bg[0], "bg2": bg[1], "bg3": bg[2],
              "hero1": hero[0], "hero2": hero[1], "hero3": hero[2],
              "soft": soft, "pastel": pastel, "medio": medio, "fuerte": fuerte,
              "oscuro": oscuro, "titulo": titulo, "borde": borde, "rgb": rgb},
    }


TEMAS = {
    "rosa": _tema("Rosa clásico", "", ["🌸", "💅", "✨", "🎀"],
                  ("#FFF7FA", "#FFFFFF", "#FFF4F8"), ("#FCE4EC", "#F8D7E3", "#F3C6D8"),
                  "#FFF1F6", "#F8D7E3", "#E58AAE", "#D9719A", "#B8527A", "#8F3A5C", "#F3D3E0", "217,113,154"),
    "primavera": _tema("Primavera", "🌷 Temporada de primavera", ["🌷", "🌸", "🦋", "🌼"],
                       ("#F8FFF9", "#FFFFFF", "#FFF6FA"), ("#E8F6E4", "#F9DDE9", "#F8C8DC"),
                       "#FFF3F8", "#F9D9E8", "#E88FB5", "#D4709F", "#A8507C", "#8A3C63", "#F3D5E3", "212,112,159"),
    "madres": _tema("Día de las Madres", "💐 Especial Día de las Madres", ["💐", "🌹", "💖", "🎀"],
                    ("#FFF8F5", "#FFFFFF", "#FFF3F0"), ("#FFE6E0", "#FDD2CA", "#F9BFB6"),
                    "#FFF1EE", "#FDD6CE", "#F0907F", "#E0685A", "#B2463B", "#8F3329", "#F8D3CC", "224,104,90"),
    "verano": _tema("Verano", "🌴 Especial de verano", ["🌴", "☀️", "🍉", "🐚"],
                    ("#FFFAF4", "#FFFFFF", "#F2FCFB"), ("#FFE9D6", "#FFD9C7", "#BFEDE9"),
                    "#FFF3EA", "#FFDCCB", "#FF9A82", "#F2705A", "#C24A38", "#9A3A2C", "#FADCCF", "242,112,90"),
    "independencia": _tema("Fiestas patrias", "🎉 ¡Viva México!", ["🌵", "🎉", "🌶️", "🎊"],
                           ("#F7FFF8", "#FFFFFF", "#FFF7F6"), ("#DDF1DE", "#FFFFFF", "#F9D4D6"),
                           "#F1FAF2", "#D7EEDA", "#58AE70", "#2E8B57", "#1F6B42", "#17543A", "#D3E9D6", "46,139,87"),
    "otono": _tema("Otoño", "🍂 Temporada de otoño", ["🍂", "🍁", "🌰", "☕"],
                   ("#FFF9F3", "#FFFFFF", "#FFF5EA"), ("#FBE8D6", "#F6D5B8", "#EBBE97"),
                   "#FFF3E7", "#F9DDC3", "#E39B5E", "#CF7A3C", "#A05A25", "#7F451B", "#F2D9C2", "207,122,60"),
    "muertos": _tema("Halloween y Día de Muertos", "🎃 Halloween y Día de Muertos", ["🎃", "🌼", "🕯️", "💀", "🦋"],
                     ("#FFF9F0", "#FFFFFF", "#FBF3FA"), ("#FDE5C2", "#F9D1E8", "#DCCBF3"),
                     "#FFF4E4", "#FCE0B8", "#F29A38", "#DB6A1C", "#9E3F12", "#5E2A5A", "#F5DCB8", "219,106,28"),
    "navidad": _tema("Navidad", "🎄 Especial de Navidad", ["🎄", "❄️", "🎁", "⭐"],
                     ("#FFF8F6", "#FFFFFF", "#F4FBF6"), ("#FBE0DC", "#FFFFFF", "#D9EEDC"),
                     "#FFF2F0", "#F8D3CF", "#D8605A", "#C0392B", "#8E2A2A", "#7A1F2B", "#F1D0CC", "192,57,43"),
    "anio_nuevo": _tema("Año Nuevo", "🥂 ¡Feliz Año Nuevo!", ["🥂", "✨", "🎆", "🎉"],
                        ("#FFFCF3", "#FFFFFF", "#FFF9E8"), ("#FAF0D2", "#F5E3B0", "#EBD08A"),
                        "#FFF8E6", "#F6E8C3", "#D9B44A", "#BE962E", "#8A6B1F", "#5F4A16", "#EFE0B8", "190,150,46"),
    "reyes": _tema("Día de Reyes", "👑 Día de Reyes", ["👑", "🎁", "⭐", "✨"],
                   ("#FBF8FF", "#FFFFFF", "#FFF9EC"), ("#EADDF8", "#E1CFF3", "#F6E3B5"),
                   "#F6F0FD", "#E6D6F6", "#A97FD3", "#8E5BC0", "#6B3FA0", "#512F7A", "#E5D8F3", "142,91,192"),
    "invierno": _tema("Invierno", "❄️ Temporada de invierno", ["❄️", "⛄", "✨", "💙"],
                      ("#F6FAFF", "#FFFFFF", "#FFF7FA"), ("#E3EFFB", "#D3E5F7", "#F9DCE8"),
                      "#EFF6FD", "#D6E7F7", "#7FB2E0", "#4F94D0", "#2F6FA8", "#254F7A", "#D3E4F4", "79,148,208"),
    "valentin": _tema("San Valentín", "💘 San Valentín", ["💖", "💘", "🌹", "💕"],
                      ("#FFF5F8", "#FFFFFF", "#FFEFF4"), ("#FFD9E4", "#FBC1D3", "#F7A8C2"),
                      "#FFEBF1", "#FCCBDA", "#EA5C86", "#D63A68", "#A8244D", "#8A1C40", "#F8C9D8", "214,58,104"),
}

# (mes, día) inicio, (mes, día) fin, tema — el primero que coincida gana
REGLAS_TEMA = [
    ((12, 1), (12, 25), "navidad"),
    ((12, 26), (12, 31), "anio_nuevo"),
    ((1, 1), (1, 1), "anio_nuevo"),
    ((1, 2), (1, 6), "reyes"),
    ((1, 7), (1, 31), "invierno"),
    ((2, 1), (2, 14), "valentin"),
    ((2, 15), (3, 19), "invierno"),
    ((3, 20), (4, 30), "primavera"),
    ((5, 1), (5, 10), "madres"),
    ((5, 11), (6, 20), "primavera"),
    ((6, 21), (8, 31), "verano"),
    ((9, 1), (9, 16), "independencia"),
    ((9, 17), (10, 14), "otono"),
    ((10, 15), (11, 2), "muertos"),
    ((11, 3), (11, 30), "otono"),
]


def tema_para(d: date) -> str:
    md = (d.month, d.day)
    for ini, fin, clave in REGLAS_TEMA:
        if ini <= md <= fin:
            return clave
    return "rosa"


# ══════════════════════════════════════════════════════════════
# ESTILOS (CSS)
# ══════════════════════════════════════════════════════════════
BASE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;600;700&family=Poppins:wght@300;400;500;600&display=swap');
:root{--gris:#8E8389;--texto:#4A4046;--sombra:0 8px 24px rgba(var(--rgb),.12);color-scheme:light;}
.stApp, .stApp p, .stApp label, .stApp input, .stApp textarea, .stApp button, .stApp li, .stApp td, .stApp th{font-family:'Poppins',sans-serif;}
.stApp{background:linear-gradient(180deg,var(--bg1) 0%,var(--bg2) 55%,var(--bg3) 100%);color:var(--texto);}
header[data-testid="stHeader"], #MainMenu, footer{visibility:hidden;height:0;}
.block-container{max-width:980px;padding-top:1.2rem;padding-bottom:3rem;position:relative;z-index:1;}
label, label p, [data-testid="stWidgetLabel"] p{color:var(--texto)!important;font-weight:500;}
p, li{color:var(--texto);}
[data-testid="stCaptionContainer"]{color:var(--gris);}

.fall{position:fixed;inset:0;pointer-events:none;overflow:hidden;z-index:0;}
.fall span{position:absolute;top:-8%;opacity:.45;animation-name:caer;animation-timing-function:linear;animation-iteration-count:infinite;}
@keyframes caer{0%{transform:translateY(-10vh) rotate(0deg);}100%{transform:translateY(112vh) rotate(360deg);}}
@media (prefers-reduced-motion: reduce){.fall{display:none;}}

.hero{background:linear-gradient(135deg,var(--hero1) 0%,var(--hero2) 50%,var(--hero3) 100%);border-radius:28px;padding:2rem 1.5rem;text-align:center;box-shadow:var(--sombra);margin-bottom:1.2rem;border:1px solid #fff;}
.hero-tag{display:inline-block;background:rgba(255,255,255,.75);border-radius:999px;padding:.2rem 1rem;font-size:.78rem;color:var(--oscuro);font-weight:600;margin-bottom:.5rem;}
.hero-sub{letter-spacing:.3em;text-transform:uppercase;font-size:.72rem;color:var(--oscuro);font-weight:500;}
.hero-title{font-family:'Playfair Display',serif;font-size:2.6rem;font-weight:700;color:var(--titulo);line-height:1.15;margin:.3rem 0;}
.hero-text{color:var(--titulo);opacity:.8;font-weight:300;font-size:.98rem;margin:0;}
.hero-deco{font-size:1.4rem;letter-spacing:.5rem;margin-top:.7rem;}
.pills{display:flex;gap:.5rem;justify-content:center;flex-wrap:wrap;margin-top:.9rem;}
.pill, .pill:visited{background:rgba(255,255,255,.8);border:1px solid #fff;border-radius:999px;padding:.3rem .95rem;font-size:.8rem;color:var(--oscuro)!important;text-decoration:none!important;font-weight:500;box-shadow:0 2px 8px rgba(var(--rgb),.12);}
.pill:hover{background:#fff;}

.stTabs [data-baseweb="tab-list"]{gap:.4rem;background:#fff;border-radius:999px;padding:.3rem;border:1px solid var(--borde);box-shadow:var(--sombra);overflow-x:auto;}
.stTabs [data-baseweb="tab"]{border-radius:999px;padding:.45rem 1.2rem;color:var(--gris);font-weight:500;height:auto;white-space:nowrap;}
.stTabs [data-baseweb="tab"]:first-of-type{margin-left:auto;}
.stTabs [data-baseweb="tab"]:last-of-type{margin-right:auto;}
.stTabs [data-baseweb="tab"] p{color:inherit!important;}
.stTabs [aria-selected="true"]{background:var(--pastel);color:var(--oscuro)!important;}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"]{display:none;}

.stepper{display:flex;align-items:flex-start;justify-content:center;margin:1.2rem auto 1.4rem;max-width:520px;}
.step{display:flex;flex-direction:column;align-items:center;gap:.35rem;min-width:70px;}
.dot{width:38px;height:38px;border-radius:50%;background:#fff;border:2px solid var(--borde);color:var(--gris);display:flex;align-items:center;justify-content:center;font-weight:600;}
.lbl{font-size:.74rem;color:var(--gris);font-weight:500;text-align:center;}
.step.active .dot{background:linear-gradient(135deg,var(--medio),var(--fuerte));border-color:transparent;color:#fff;box-shadow:0 4px 14px rgba(var(--rgb),.4);}
.step.active .lbl{color:var(--oscuro);font-weight:600;}
.step.done .dot{background:var(--pastel);border-color:var(--medio);color:var(--oscuro);}
.line{flex:1;height:2px;background:var(--borde);margin-top:19px;min-width:30px;}
.line.done{background:var(--medio);}

.section-title{font-family:'Playfair Display',serif;font-size:1.6rem;color:var(--oscuro);font-weight:600;margin:.2rem 0 .1rem;}
.section-sub{color:var(--gris);font-size:.9rem;margin-bottom:1rem;font-weight:300;}
.mini-title{font-family:'Playfair Display',serif;font-size:1.15rem;color:var(--titulo);font-weight:600;margin:1.2rem 0 .4rem;}

.service-card{background:#fff;border:1.5px solid var(--borde);border-radius:22px;padding:1rem;box-shadow:var(--sombra);margin-bottom:.6rem;transition:all .2s;}
.service-card:hover{transform:translateY(-3px);border-color:var(--medio);}
.service-card.selected{border-color:var(--fuerte);background:var(--soft);}
.svc-img{width:100%;height:150px;object-fit:cover;border-radius:16px;margin-bottom:.6rem;display:block;}
.svc-name{font-family:'Playfair Display',serif;font-size:1.15rem;font-weight:600;color:var(--titulo);margin:.1rem 0 .25rem;}
.svc-desc{font-size:.82rem;color:var(--gris);line-height:1.4;min-height:46px;font-weight:300;}
.svc-meta{display:flex;justify-content:space-between;align-items:center;margin-top:.6rem;}
.svc-price{font-weight:600;font-size:1.15rem;color:var(--oscuro);}
.svc-time{font-size:.78rem;background:var(--pastel);color:var(--oscuro);padding:.15rem .65rem;border-radius:999px;font-weight:500;}

.chip{display:inline-block;background:#fff;border:1.5px solid var(--borde);border-radius:999px;padding:.45rem 1.1rem;font-size:.88rem;box-shadow:var(--sombra);margin-bottom:1rem;}
.summary{background:#fff;border:1.5px dashed var(--medio);border-radius:22px;padding:1.2rem 1.4rem;margin-bottom:1rem;}
.summary-row{display:flex;justify-content:space-between;gap:1rem;padding:.35rem 0;border-bottom:1px solid var(--soft);font-size:.92rem;}
.summary-row:last-child{border-bottom:none;}
.summary-row span:first-child{color:var(--gris);}
.summary-row span:last-child{font-weight:500;text-align:right;}
.success{background:linear-gradient(135deg,var(--soft),var(--pastel));border-radius:26px;padding:1.8rem 1.2rem;text-align:center;border:1px solid #fff;box-shadow:var(--sombra);margin-bottom:1rem;}
.success .big{font-size:2.6rem;}
.success h3{font-family:'Playfair Display',serif;color:var(--titulo);margin:.3rem 0;}
.pay-box{background:#fff;border:1.5px solid var(--medio);border-radius:22px;padding:1.1rem 1.3rem;margin-bottom:1rem;box-shadow:var(--sombra);}
.pay-title{font-weight:600;color:var(--oscuro);}
.pay-monto{font-family:'Playfair Display',serif;font-size:2rem;font-weight:700;color:var(--fuerte);line-height:1.2;}
.pay-datos{background:var(--soft);border-radius:14px;padding:.7rem .9rem;font-size:.88rem;margin:.5rem 0;}
.pay-nota{font-size:.8rem;color:var(--gris);}
.legend{font-size:.8rem;color:var(--gris);margin:.2rem 0 .8rem;}

.mes-titulo{font-family:'Playfair Display',serif;text-align:center;font-size:1.3rem;color:var(--titulo);font-weight:600;padding:.45rem 0;}
.cal-dowrow{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));text-align:center;font-size:.7rem;font-weight:600;color:var(--gris);text-transform:uppercase;margin:.2rem 0 .3rem;}
.cal{background:#fff;border:1px solid var(--borde);border-radius:22px;padding:.9rem;box-shadow:var(--sombra);}
.cal-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:.35rem;}
.cal-dow{text-align:center;font-size:.7rem;font-weight:600;color:var(--gris);text-transform:uppercase;padding:.2rem 0;}
.cal-d{border:1px solid transparent;border-radius:14px;padding:.35rem .2rem;min-height:68px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:.08rem;text-align:center;}
.cal-d b{font-size:.95rem;}
.cal-d small{font-size:.62rem;line-height:1.15;font-weight:500;}
.cal-d.fuera{visibility:hidden;}
.cal-d.hoy{outline:2px solid var(--fuerte);}
.legend-row{display:flex;flex-wrap:wrap;gap:.4rem;margin:.7rem 0 1rem;}
.lg{padding:.15rem .75rem;border-radius:999px;font-size:.74rem;font-weight:500;border:1px solid transparent;}

.bar-row{display:flex;align-items:center;gap:.6rem;margin:.35rem 0;font-size:.85rem;}
.bar-l{flex:0 0 38%;color:var(--texto);}
.bar{flex:1;background:var(--soft);border-radius:999px;height:12px;overflow:hidden;}
.bar div{height:100%;background:linear-gradient(90deg,var(--medio),var(--fuerte));border-radius:999px;}
.bar-n{flex:0 0 28px;text-align:right;font-weight:600;color:var(--oscuro);}
.panel{background:#fff;border:1px solid var(--borde);border-radius:22px;padding:1rem 1.2rem;box-shadow:var(--sombra);margin-bottom:1rem;}
.panel h4{font-family:'Playfair Display',serif;color:var(--titulo);margin:0 0 .4rem;font-size:1.05rem;}

.metric{background:#fff;border:1px solid var(--borde);border-radius:22px;padding:1rem .8rem;text-align:center;box-shadow:var(--sombra);}
.metric .ico{font-size:1.3rem;}
.metric .num{font-family:'Playfair Display',serif;font-size:1.8rem;font-weight:700;color:var(--oscuro);line-height:1.2;}
.metric .txt{font-size:.74rem;color:var(--gris);font-weight:500;text-transform:uppercase;letter-spacing:.05em;}

.cita{background:#fff;border:1px solid var(--borde);border-left:6px solid var(--medio);border-radius:20px;padding:1rem 1.2rem;margin-top:1rem;box-shadow:var(--sombra);}
.cita.confirmada{border-left-color:#5FBF8A;}
.cita.cancelada{border-left-color:#C9C2C6;opacity:.75;}
.cita-top{display:flex;justify-content:space-between;align-items:flex-start;gap:.6rem;flex-wrap:wrap;}
.cita-hora{font-family:'Playfair Display',serif;font-size:1.25rem;font-weight:600;color:var(--titulo);}
.cita-fecha{font-size:.8rem;color:var(--gris);}
.cita-nombre{font-weight:600;font-size:1rem;}
.cita-det{font-size:.85rem;color:var(--gris);margin-top:.2rem;}
.badges{display:flex;gap:.4rem;flex-wrap:wrap;}
.badge{padding:.2rem .8rem;border-radius:999px;font-size:.74rem;font-weight:600;}
.b-pend{background:#FFF0D9;color:#B7791F;}
.b-ok{background:#DDF5E8;color:#2F8F5B;}
.b-no{background:#EEE9EB;color:#7C7378;}
.b-pay-p{background:#FFE6DC;color:#C2502E;}
.b-pay-ok{background:#DDF5E8;color:#2F8F5B;}
.b-pay-no{background:#EEE9EB;color:#7C7378;}
.blq{background:#fff;border:1px solid var(--borde);border-left:6px solid var(--medio);border-radius:18px;padding:.7rem 1rem;}
.blq b{color:var(--titulo);}
.blq small{color:var(--gris);}

.theme-prev{border-radius:20px;padding:1rem;text-align:center;border:1px solid #fff;box-shadow:var(--sombra);margin:.4rem 0 1rem;}
.theme-name{font-family:'Playfair Display',serif;font-size:1.3rem;font-weight:600;margin:.2rem 0 .5rem;}
.swatch{display:inline-block;width:26px;height:26px;border-radius:50%;margin:0 3px;border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.15);}
.footer{text-align:center;color:var(--gris);font-size:.8rem;margin-top:2rem;}

.stButton>button, .stFormSubmitButton>button, .stLinkButton a, [data-testid="stPopover"] button{
border-radius:999px!important;border:1.5px solid var(--fuerte)!important;background:#fff!important;color:var(--oscuro)!important;
font-weight:500!important;padding:.5rem 1.1rem!important;transition:all .2s;box-shadow:0 2px 8px rgba(var(--rgb),.12);}
.stButton>button p, .stFormSubmitButton>button p, [data-testid="stPopover"] button p{color:inherit!important;}
.stButton>button:hover, .stFormSubmitButton>button:hover, [data-testid="stPopover"] button:hover{background:var(--soft)!important;transform:translateY(-1px);}
.stButton>button[kind="primary"], .stButton>button[data-testid="stBaseButton-primary"],
.stFormSubmitButton>button[kind="primaryFormSubmit"], .stFormSubmitButton>button[data-testid="stBaseButton-primaryFormSubmit"]{
background:linear-gradient(135deg,var(--medio),var(--fuerte))!important;color:#fff!important;border:none!important;box-shadow:0 6px 16px rgba(var(--rgb),.35);}
.stButton>button[kind="primary"] p, .stFormSubmitButton>button[kind="primaryFormSubmit"] p{color:#fff!important;}
.stButton>button:disabled{background:#F6F2F4!important;color:#BFB5BA!important;border-color:#EEE6EA!important;box-shadow:none;opacity:.85;}
.st-key-nowrap_slots .stButton>button:disabled{text-decoration:line-through;}
.stLinkButton a{background:linear-gradient(135deg,#4FCB7D,#25D366)!important;border:none!important;box-shadow:0 6px 16px rgba(37,211,102,.3);}
.stLinkButton a, .stLinkButton a *{color:#fff!important;}

[class*="st-key-nowrap"] [data-testid="stHorizontalBlock"]{flex-wrap:nowrap!important;gap:.35rem!important;}
[class*="st-key-nowrap"] [data-testid="stColumn"], [class*="st-key-nowrap"] [data-testid="column"]{min-width:0!important;}
[class*="st-key-nowrap"] .stButton>button{padding:.35rem .1rem!important;min-height:2.6rem;font-size:.85rem;border-radius:14px!important;white-space:nowrap;}
[class*="st-key-dia_"] button:disabled{opacity:1!important;cursor:not-allowed;}

.stTextInput input, .stTextArea textarea, .stDateInput input, .stNumberInput input{border-radius:14px!important;color:var(--texto)!important;background:#fff!important;}
div[data-baseweb="input"], div[data-baseweb="base-input"], div[data-baseweb="textarea"], div[data-baseweb="select"]>div{border-radius:14px!important;border-color:var(--borde)!important;background:#fff!important;}
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within{border-color:var(--fuerte)!important;}
[data-testid="stForm"]{background:#fff;border:1px solid var(--borde);border-radius:22px;padding:1.2rem;box-shadow:var(--sombra);}
[data-testid="stExpander"]{background:#fff;border:1px solid var(--borde)!important;border-radius:18px!important;}
[data-testid="stFileUploaderDropzone"]{border-radius:16px;background:var(--soft);border:1.5px dashed var(--medio);}
[data-testid="stImage"] img{border-radius:18px;box-shadow:var(--sombra);}
div[role="radiogroup"] label{background:#fff;border:1px solid var(--borde);border-radius:999px;padding:.2rem .9rem;}
hr{border-color:var(--borde);}
@media (max-width:640px){.hero-title{font-size:2rem;}.cita-hora{font-size:1.05rem;}.cal{padding:.5rem;}.cal-d{min-height:56px;}.bar-l{flex-basis:45%;}}
"""


def css_total(tema: dict) -> str:
    c = tema["c"]
    variables = ":root{" + "".join(f"--{k}:{v};" for k, v in c.items()) + "}"
    estados = "".join(
        f".est-{k}{{background:{bg};color:{fg};border-color:{bd};}}" for k, (bg, fg, bd) in COLORES_ESTADO.items()
    )
    decoracion = ""
    if CFG.get("animacion", True):
        emojis = tema["emojis"]
        spans = []
        for i in range(14):
            x = (i * 37 + 11) % 100
            dur = 14 + (i * 7) % 11
            retraso = -((i * 5) % 17)
            tam = 16 + (i * 5) % 14
            spans.append(
                f'<span style="left:{x}%;font-size:{tam}px;animation-duration:{dur}s;'
                f'animation-delay:{retraso}s">{emojis[i % len(emojis)]}</span>'
            )
        decoracion = '<div class="fall">' + "".join(spans) + "</div>"
    return f"<style>{BASE_CSS}</style><style>{variables}{estados}</style>{decoracion}"


def render(markup: str):
    """Renderiza HTML compactando saltos de línea (evita bloques de código en markdown)."""
    limpio = "".join(linea.strip() for linea in markup.strip().splitlines())
    st.markdown(limpio, unsafe_allow_html=True)


@lru_cache(maxsize=None)
def ancho(fn):
    """Parámetros para que un widget ocupe todo el ancho (compatible con versiones nuevas y viejas)."""
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    p = params.get("width")
    if p is not None and "stretch" in str(p.annotation):
        return {"width": "stretch"}
    if "use_container_width" in params:
        return {"use_container_width": True}
    return {}


# ══════════════════════════════════════════════════════════════
# UTILIDADES
# ══════════════════════════════════════════════════════════════
def ahora() -> datetime:
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo(ZONA_HORARIA)).replace(tzinfo=None)
    except Exception:
        return datetime.now()


def esc(texto) -> str:
    """Escapa HTML y el símbolo $ (para que no se interprete como fórmula)."""
    return escape(str(texto if texto is not None else "")).replace("$", "&#36;")


def esc_br(texto) -> str:
    return esc(texto).replace("\r", "").replace("\n", "<br>")


def fecha_bonita(f: date) -> str:
    return f"{DIAS[f.weekday()].capitalize()} {f.day} de {MESES[f.month - 1]}"


def fecha_corta(f: date) -> str:
    return f"{f.day} {MESES[f.month - 1][:3]} {f.year}"


def a_minutos(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def a_hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def hora_12(hhmm: str) -> str:
    h, m = [int(x) for x in hhmm.split(":")]
    sufijo = "AM" if h < 12 else "PM"
    return f"{h % 12 or 12}:{m:02d} {sufijo}"


def dinero(valor) -> str:
    return f"&#36;{float(valor):,.0f}"


def dinero_txt(valor) -> str:
    return f"${float(valor):,.0f}"


def dinero_label(valor) -> str:
    return f"\\${float(valor):,.0f}"


def mes_offset(d: date, n: int) -> date:
    m = d.month - 1 + n
    return date(d.year + m // 12, m % 12 + 1, 1)


def normalizar_telefono(tel: str) -> str:
    d = re.sub(r"\D", "", tel or "")
    if len(d) == 10:
        d = CODIGO_PAIS + d
    elif d.startswith("521") and len(d) == 13:
        d = "52" + d[3:]
    return d


def enlace_whatsapp(numero: str, mensaje: str) -> str:
    return f"https://wa.me/{numero}?text={quote(mensaje)}"


def url_red(red: str, valor: str) -> str:
    v = (valor or "").strip()
    if not v:
        return ""
    if v.lower().startswith("http"):
        return v
    v = v.lstrip("@").strip("/")
    base = {"instagram": "https://instagram.com/", "facebook": "https://facebook.com/",
            "tiktok": "https://tiktok.com/@", "web": "https://"}
    return base.get(red, "https://") + v


def url_maps() -> str:
    m = (CFG.get("maps") or "").strip()
    if m.lower().startswith("http"):
        return m
    if CFG.get("direccion"):
        return "https://www.google.com/maps/search/?api=1&query=" + quote(CFG["direccion"])
    return ""


def redes():
    salida = []
    wa = normalizar_telefono(CFG.get("whatsapp", ""))
    if wa:
        salida.append(("💬", "WhatsApp", f"https://wa.me/{wa}"))
    for clave, emoji, nombre in [("instagram", "📸", "Instagram"), ("facebook", "👍", "Facebook"),
                                 ("tiktok", "🎵", "TikTok"), ("web", "🌐", "Sitio web")]:
        u = url_red(clave, CFG.get(clave, ""))
        if u:
            salida.append((emoji, nombre, u))
    return salida


def password_admin() -> str:
    try:
        return str(st.secrets["ADMIN_PASSWORD"])
    except Exception:
        return os.environ.get("ADMIN_PASSWORD", "admin123")  # ⚠️ Cámbiala


def avisar(texto: str, icono: str = "✅"):
    st.session_state["_aviso"] = (texto, icono)


def procesar_imagen(archivo, ancho_px: int, alto_px=None, calidad: int = 82) -> bytes:
    """Redimensiona y comprime la imagen subida (JPEG). Si hay alto, recorta al centro."""
    from PIL import Image, ImageOps
    img = Image.open(archivo)
    img = ImageOps.exif_transpose(img).convert("RGB")
    if alto_px:
        img = ImageOps.fit(img, (ancho_px, alto_px))
    else:
        img.thumbnail((ancho_px, ancho_px), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=calidad, optimize=True)
    return buf.getvalue()


# ══════════════════════════════════════════════════════════════
# BASE DE DATOS
# ══════════════════════════════════════════════════════════════
def conectar():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def consultar(sql, params=()):
    with closing(conectar()) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def ejecutar(sql, params=()):
    with closing(conectar()) as conn, conn:
        return conn.execute(sql, params).lastrowid


COLUMNAS_NUEVAS = {
    "anticipo_req": "REAL DEFAULT 0",
    "anticipo_pagado": "REAL DEFAULT 0",
    "pago_estado": "TEXT DEFAULT 'no_requerido'",
    "metodo_pago": "TEXT DEFAULT ''",
    "pago_fecha": "TEXT DEFAULT ''",
}


def init_db():
    with closing(conectar()) as conn, conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS citas(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT NOT NULL,
                servicio TEXT NOT NULL,
                precio REAL NOT NULL,
                duracion INTEGER NOT NULL,
                fecha TEXT NOT NULL,
                hora TEXT NOT NULL,
                notas TEXT DEFAULT '',
                estado TEXT NOT NULL DEFAULT 'pendiente',
                creado TEXT NOT NULL
            )"""
        )
        existentes = {r["name"] for r in conn.execute("PRAGMA table_info(citas)").fetchall()}
        for nombre, ddl in COLUMNAS_NUEVAS.items():
            if nombre not in existentes:
                conn.execute(f"ALTER TABLE citas ADD COLUMN {nombre} {ddl}")
        conn.execute("CREATE TABLE IF NOT EXISTS config(clave TEXT PRIMARY KEY, valor TEXT)")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS servicios(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                descripcion TEXT DEFAULT '',
                precio REAL NOT NULL DEFAULT 0,
                duracion INTEGER NOT NULL DEFAULT 60,
                icono TEXT DEFAULT '💅',
                imagen BLOB,
                img_ver INTEGER NOT NULL DEFAULT 0,
                activo INTEGER NOT NULL DEFAULT 1,
                orden INTEGER NOT NULL DEFAULT 0
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS bloqueos(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_ini TEXT NOT NULL,
                fecha_fin TEXT NOT NULL,
                hora_ini TEXT DEFAULT '',
                hora_fin TEXT DEFAULT '',
                tipo TEXT DEFAULT 'Día libre',
                motivo TEXT DEFAULT ''
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS catalogo(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT DEFAULT '',
                categoria TEXT DEFAULT '',
                imagen BLOB NOT NULL,
                creado TEXT NOT NULL
            )"""
        )
        if conn.execute("SELECT COUNT(*) FROM servicios").fetchone()[0] == 0:
            for i, (nombre, desc, precio, dur, icono) in enumerate(SERVICIOS_INICIALES):
                conn.execute(
                    "INSERT INTO servicios(nombre, descripcion, precio, duracion, icono, orden) VALUES(?,?,?,?,?,?)",
                    (nombre, desc, precio, dur, icono, i),
                )


def leer_config():
    cfg = json.loads(json.dumps(CFG_DEFECTO))
    for fila in consultar("SELECT clave, valor FROM config"):
        try:
            cfg[fila["clave"]] = json.loads(fila["valor"])
        except Exception:
            pass
    base = CFG_DEFECTO["horario"]
    guardado = cfg.get("horario") or {}
    cfg["horario"] = {k: {**base[k], **(guardado.get(k) or {})} for k in base}
    CFG.clear()
    CFG.update(cfg)


def guardar_config(**valores):
    with closing(conectar()) as conn, conn:
        for k, v in valores.items():
            conn.execute("INSERT OR REPLACE INTO config(clave, valor) VALUES(?,?)",
                         (k, json.dumps(v, ensure_ascii=False)))
    leer_config()


SVC_COLS = "id, nombre, descripcion, precio, duracion, icono, activo, orden, img_ver, (imagen IS NOT NULL) AS tiene_img"


def servicios_lista(solo_activos=True):
    sql = f"SELECT {SVC_COLS} FROM servicios"
    if solo_activos:
        sql += " WHERE activo=1"
    return consultar(sql + " ORDER BY orden, id")


def servicio_actual():
    sid = st.session_state.get("servicio")
    if sid is None:
        return None
    f = consultar(f"SELECT {SVC_COLS} FROM servicios WHERE id=? AND activo=1", (sid,))
    return f[0] if f else None


def duracion_minima() -> int:
    ds = [int(s["duracion"]) for s in servicios_lista()]
    return min(ds) if ds else 30


@st.cache_data(show_spinner=False)
def imagen_servicio_uri(sid: int, version: int) -> str:
    f = consultar("SELECT imagen FROM servicios WHERE id=?", (sid,))
    if f and f[0]["imagen"]:
        return "data:image/jpeg;base64," + base64.b64encode(f[0]["imagen"]).decode()
    return ""


def version_catalogo() -> str:
    f = consultar("SELECT COUNT(*) AS n, COALESCE(MAX(id),0) AS m FROM catalogo")[0]
    return f"{f['n']}-{f['m']}"


@st.cache_data(show_spinner=False)
def cargar_catalogo(version: str, limite: int, categoria: str):
    sql, params = "SELECT id, titulo, categoria, imagen FROM catalogo", []
    if categoria != "Todo":
        sql += " WHERE categoria=?"
        params.append(categoria)
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limite)
    return consultar(sql, tuple(params))


def expirar_pendientes():
    """Libera horarios cuyo anticipo no llegó a tiempo (si el salón activó el límite)."""
    horas = int(CFG.get("horas_pago") or 0)
    if horas <= 0:
        return
    limite = (ahora() - timedelta(hours=horas)).isoformat(timespec="seconds")
    ejecutar(
        "UPDATE citas SET estado='cancelada', notas = TRIM(COALESCE(notas,'') || ' [Liberada automáticamente: no llegó el anticipo]') "
        "WHERE estado='pendiente' AND pago_estado='pendiente' AND creado < ?",
        (limite,),
    )


# ══════════════════════════════════════════════════════════════
# DISPONIBILIDAD Y CALENDARIO
# ══════════════════════════════════════════════════════════════
def horario_dia(d: date):
    h = CFG["horario"][str(d.weekday())]
    if not h.get("abierto"):
        return None
    return a_minutos(h["ini"]), a_minutos(h["fin"])


def hay_choque(inicio: int, duracion: int, ocupados) -> bool:
    fin = inicio + duracion
    return any(inicio < o_fin and fin > o_ini for o_ini, o_fin in ocupados)


def cargar_datos(desde: date, hasta: date) -> dict:
    """Citas activas y bloqueos de cada día del rango (2 consultas en total)."""
    d0, d1 = desde.isoformat(), hasta.isoformat()
    citas = consultar("SELECT * FROM citas WHERE fecha BETWEEN ? AND ? AND estado!='cancelada'", (d0, d1))
    bloqs = consultar("SELECT * FROM bloqueos WHERE fecha_fin>=? AND fecha_ini<=?", (d0, d1))
    datos, d = {}, desde
    while d <= hasta:
        datos[d] = {"citas": [], "bloqueos": []}
        d += timedelta(days=1)
    for c in citas:
        f = date.fromisoformat(c["fecha"])
        if f in datos:
            datos[f]["citas"].append(c)
    for b in bloqs:
        d = max(date.fromisoformat(b["fecha_ini"]), desde)
        fin = min(date.fromisoformat(b["fecha_fin"]), hasta)
        while d <= fin:
            datos[d]["bloqueos"].append(b)
            d += timedelta(days=1)
    return datos


def intervalos_ocupados(datos_dia: dict):
    oc = [(a_minutos(c["hora"]), a_minutos(c["hora"]) + int(c["duracion"])) for c in datos_dia["citas"]]
    for b in datos_dia["bloqueos"]:
        if b["hora_ini"]:
            oc.append((a_minutos(b["hora_ini"]), a_minutos(b["hora_fin"])))
    return oc


def slots_dia(d: date, duracion: int, datos_dia: dict):
    """Lista de (minuto_inicio, disponible). Omite horas que ya pasaron."""
    if any(not b["hora_ini"] for b in datos_dia["bloqueos"]):
        return []
    h = horario_dia(d)
    if not h:
        return []
    ini, fin = h
    ocupados = intervalos_ocupados(datos_dia)
    n = ahora()
    paso = max(int(CFG["intervalo"]), 5)
    slots, t = [], ini
    while t + duracion <= fin:
        pasado = d < n.date() or (d == n.date() and t <= n.hour * 60 + n.minute + int(CFG["anticipacion_min"]))
        if not pasado:
            slots.append((t, not hay_choque(t, duracion, ocupados)))
        t += paso
    return slots


def resumen_dia(d: date, datos_dia: dict, duracion: int) -> dict:
    hoy = ahora().date()
    citas, bloqs = datos_dia["citas"], datos_dia["bloqueos"]
    r = {"fecha": d, "n": len(citas), "ingresos": sum(float(c["precio"]) for c in citas),
         "estado": "baja", "motivo": "", "libres": 0, "ocup": 0.0}
    dia_completo = next((b for b in bloqs if not b["hora_ini"]), None)
    if dia_completo:
        r["estado"] = "bloqueado"
        r["motivo"] = dia_completo["motivo"] or dia_completo["tipo"] or "No laborable"
        return r
    h = horario_dia(d)
    if not h:
        r["estado"] = "cerrado"
        r["motivo"] = "Descanso"
        return r
    ini, fin = h
    bloqueado_min = 0
    for b in bloqs:
        if b["hora_ini"]:
            bloqueado_min += max(0, min(a_minutos(b["hora_fin"]), fin) - max(a_minutos(b["hora_ini"]), ini))
    capacidad = max(0, (fin - ini) - bloqueado_min)
    usado = 0
    for c in citas:
        c_ini = a_minutos(c["hora"])
        usado += max(0, min(c_ini + int(c["duracion"]), fin) - max(c_ini, ini))
    r["ocup"] = (usado / capacidad) if capacidad else 1.0
    slots = slots_dia(d, duracion, datos_dia)
    r["libres"] = sum(1 for _, libre in slots if libre)
    if d < hoy or (d == hoy and not slots):
        r["estado"] = "pasado"
    elif r["libres"] == 0:
        r["estado"] = "lleno"
    elif r["ocup"] >= 0.65:
        r["estado"] = "alta"
    elif r["ocup"] >= 0.35:
        r["estado"] = "media"
    return r


def primer_dia_libre(duracion: int):
    hoy = ahora().date()
    fin = hoy + timedelta(days=int(CFG["dias_adelante"]))
    datos = cargar_datos(hoy, fin)
    d = hoy
    while d <= fin:
        r = resumen_dia(d, datos[d], duracion)
        if r["estado"] in ("baja", "media", "alta") and r["libres"] > 0:
            return d
        d += timedelta(days=1)
    return None


def calendario_html(mes: date, datos: dict, duracion: int) -> str:
    hoy = ahora().date()
    celdas = [f'<div class="cal-dow">{n}</div>' for n in DIAS_CORTO]
    for semana in pycal.Calendar(0).monthdatescalendar(mes.year, mes.month):
        for d in semana:
            if d.month != mes.month:
                celdas.append('<div class="cal-d fuera"></div>')
                continue
            r = resumen_dia(d, datos[d], duracion)
            clases = f"cal-d est-{r['estado']}" + (" hoy" if d == hoy else "")
            extra = ""
            if r["estado"] in ("cerrado", "bloqueado"):
                extra = f"<small>{esc(r['motivo'][:16])}</small>"
            elif r["n"]:
                extra = f"<small>{r['n']} cita{'s' if r['n'] != 1 else ''}</small><small>{dinero(r['ingresos'])}</small>"
            elif r["estado"] != "pasado":
                extra = f"<small>{ETIQUETA_DIA.get(r['estado'], '')}</small>"
            if r["estado"] in ("alta", "lleno") and r["n"]:
                extra = f"<small>{ETIQUETA_DIA[r['estado']]}</small>" + extra
            celdas.append(f'<div class="{clases}"><b>{d.day}</b>{extra}</div>')
    return f'<div class="cal"><div class="cal-grid">{"".join(celdas)}</div></div>'


def leyenda_html() -> str:
    items = [("baja", "Disponible"), ("media", "Se está llenando"), ("alta", "🔥 Muy solicitado"),
             ("lleno", "Lleno"), ("cerrado", "Cerrado / asueto")]
    return '<div class="legend-row">' + "".join(f'<span class="lg est-{k}">{t}</span>' for k, t in items) + "</div>"


def navegador_mes(clave: str, minimo: date, maximo: date) -> date:
    actual = st.session_state.get(clave, minimo)
    actual = min(max(actual, minimo), maximo)
    st.session_state[clave] = actual
    with st.container(key=f"nowrap_{clave}"):
        c1, c2, c3 = st.columns([1, 3, 1])
        with c1:
            if st.button("◀", key=f"{clave}_prev", disabled=actual <= minimo, **ancho(st.button)):
                st.session_state[clave] = mes_offset(actual, -1)
                st.rerun()
        with c2:
            render(f'<div class="mes-titulo">{MESES[actual.month - 1].capitalize()} {actual.year}</div>')
        with c3:
            if st.button("▶", key=f"{clave}_next", disabled=actual >= maximo, **ancho(st.button)):
                st.session_state[clave] = mes_offset(actual, 1)
                st.rerun()
    return st.session_state[clave]


# ══════════════════════════════════════════════════════════════
# ANTICIPOS Y MENSAJES
# ══════════════════════════════════════════════════════════════
def calcular_anticipo(precio: float) -> float:
    modo, valor = CFG.get("anticipo_modo", "ninguno"), float(CFG.get("anticipo_valor") or 0)
    if modo == "porcentaje":
        monto = round(float(precio) * valor / 100)
    elif modo == "fijo":
        monto = min(valor, float(precio))
    else:
        monto = 0
    return float(max(0, monto))


def registrar_pago(cita_id: int, total_pagado: float, metodo: str, requerido: float):
    if total_pagado <= 0:
        estado = "pendiente" if requerido > 0 else "no_requerido"
    elif total_pagado >= requerido:
        estado = "pagado"
    else:
        estado = "pendiente"
    ejecutar("UPDATE citas SET anticipo_pagado=?, pago_estado=?, metodo_pago=?, pago_fecha=? WHERE id=?",
             (total_pagado, estado, metodo, ahora().isoformat(timespec="seconds"), cita_id))


def quitar_pago(cita_id: int, requerido: float):
    estado = "pendiente" if requerido > 0 else "no_requerido"
    ejecutar("UPDATE citas SET anticipo_pagado=0, pago_estado=?, metodo_pago='', pago_fecha='' WHERE id=?",
             (estado, cita_id))


def texto_pago(c: dict):
    req, pag = float(c.get("anticipo_req") or 0), float(c.get("anticipo_pagado") or 0)
    if c.get("pago_estado") == "pagado":
        return f"✅ Anticipo pagado {dinero(pag)}", "b-pay-ok"
    if c.get("pago_estado") == "pendiente":
        extra = f" · recibido {dinero(pag)}" if pag > 0 else ""
        return f"💳 Anticipo pendiente {dinero(req)}{extra}", "b-pay-p"
    return "Sin anticipo", "b-pay-no"


def mensaje_cliente(c: dict) -> str:
    f = fecha_bonita(date.fromisoformat(c["fecha"]))
    h = hora_12(c["hora"])
    base = f"Hola {c['nombre']} 🌸, te escribimos de {CFG['nombre']}. "
    if c["estado"] == "confirmada":
        return base + f"Tu cita de {c['servicio']} el {f} a las {h} está confirmada ✅. ¡Te esperamos! ✨"
    if c["estado"] == "cancelada":
        return base + (f"Lamentamos informarte que tu cita de {c['servicio']} del {f} a las {h} fue cancelada. "
                       "Si deseas reagendar, con gusto te ayudamos 🌷")
    if c.get("pago_estado") == "pendiente":
        falta = max(float(c.get("anticipo_req") or 0) - float(c.get("anticipo_pagado") or 0), 0)
        return (base + f"Para apartar tu cita de {c['servicio']} el {f} a las {h} necesitamos tu anticipo de "
                f"{dinero_txt(falta)} 💳.\n\n{CFG['datos_pago']}\n\nEnvíanos tu comprobante por aquí y la confirmamos de inmediato 💖")
    return base + f"Recibimos tu solicitud para {c['servicio']} el {f} a las {h}. ¿Nos confirmas tu asistencia? 💖"


# ══════════════════════════════════════════════════════════════
# ESTADO DE SESIÓN
# ══════════════════════════════════════════════════════════════
def init_state():
    defaults = {"paso": 1, "servicio": None, "fecha": None, "hora": None,
                "ultima_cita": None, "admin_ok": False, "gal_n": 12, "blq_n": 0}
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)


def reiniciar_reserva():
    st.session_state.paso = 1
    st.session_state.servicio = None
    st.session_state.fecha = None
    st.session_state.hora = None
    st.session_state.ultima_cita = None


# ══════════════════════════════════════════════════════════════
# COMPONENTES VISUALES
# ══════════════════════════════════════════════════════════════
def hero(tema: dict):
    etiqueta = f'<div class="hero-tag">{esc(tema["etiqueta"])}</div>' if tema["etiqueta"] else ""
    deco = " ".join(tema["emojis"])
    pills = "".join(
        f'<a class="pill" href="{esc(url)}" target="_blank" rel="noopener">{emoji} {nombre}</a>'
        for emoji, nombre, url in redes()
    )
    render(
        f'<div class="hero">{etiqueta}<div class="hero-sub">✨ Nail Studio ✨</div>'
        f'<div class="hero-title">{esc(CFG["nombre"])}</div>'
        f'<p class="hero-text">{esc(CFG["slogan"])}</p>'
        f'<div class="hero-deco">{deco}</div><div class="pills">{pills}</div></div>'
    )


def stepper(paso: int):
    etiquetas = ["Servicio", "Horario", "Tus datos"]
    partes = []
    for i, texto in enumerate(etiquetas, 1):
        clase = "done" if paso > i else ("active" if paso == i else "")
        icono = "✓" if paso > i else str(i)
        partes.append(f'<div class="step {clase}"><div class="dot">{icono}</div><div class="lbl">{texto}</div></div>')
        if i < len(etiquetas):
            linea = "done" if paso > i else ""
            partes.append(f'<div class="line {linea}"></div>')
    render(f'<div class="stepper">{"".join(partes)}</div>')


def chip_servicio(s: dict):
    render(f'<div class="chip">{esc(s["icono"])} <b>{esc(s["nombre"])}</b> · {dinero(s["precio"])} · ⏱ {s["duracion"]} min</div>')


# ══════════════════════════════════════════════════════════════
# FLUJO DE RESERVA
# ══════════════════════════════════════════════════════════════
def paso_servicio():
    render('<div class="section-title">Elige tu servicio</div>'
           '<div class="section-sub">Toca el servicio que más te guste para continuar.</div>')
    servicios = servicios_lista()
    if not servicios:
        st.info("Pronto publicaremos nuestros servicios 💕")
        return
    cols = st.columns(3)
    for i, s in enumerate(servicios):
        with cols[i % 3]:
            sel = st.session_state.servicio == s["id"]
            img = ""
            if s["tiene_img"]:
                uri = imagen_servicio_uri(s["id"], s["img_ver"])
                if uri:
                    img = f'<img class="svc-img" src="{uri}" alt="">'
            clase = "selected" if sel else ""
            render(
                f'<div class="service-card {clase}">{img}'
                f'<div class="svc-name">{esc(s["icono"])} {esc(s["nombre"])}</div>'
                f'<div class="svc-desc">{esc(s["descripcion"])}</div>'
                f'<div class="svc-meta"><span class="svc-price">{dinero(s["precio"])}</span>'
                f'<span class="svc-time">⏱ {s["duracion"]} min</span></div></div>'
            )
            if st.button("Elegido ✓" if sel else "Elegir", key=f"svc_{s['id']}",
                         type="primary" if sel else "secondary", **ancho(st.button)):
                st.session_state.servicio = s["id"]
                st.session_state.hora = None
                st.session_state.paso = 2
                st.rerun()
            render('<div style="height:.9rem"></div>')


def paso_horario():
    s = servicio_actual()
    if not s:
        reiniciar_reserva()
        st.rerun()
    render('<div class="section-title">Elige día y hora</div>'
           '<div class="section-sub">Toca un día del calendario. Los colores te muestran qué tan lleno está.</div>')
    chip_servicio(s)

    hoy = ahora().date()
    max_fecha = hoy + timedelta(days=int(CFG["dias_adelante"]))
    minimo, maximo = hoy.replace(day=1), max_fecha.replace(day=1)

    if st.button("⚡ Elegir el primer día disponible", key="primer_libre"):
        d = primer_dia_libre(int(s["duracion"]))
        if d:
            st.session_state.fecha = d
            st.session_state.hora = None
            st.session_state.cal_res = d.replace(day=1)
            st.rerun()
        else:
            st.warning("No encontramos días disponibles por ahora 💕 Escríbenos por WhatsApp.")

    if "cal_res" not in st.session_state:
        base = st.session_state.fecha or hoy
        st.session_state.cal_res = base.replace(day=1)
    mes = navegador_mes("cal_res", minimo, maximo)
    ultimo = mes_offset(mes, 1) - timedelta(days=1)
    datos = cargar_datos(mes, ultimo)

    css_dias = []
    with st.container(key="nowrap_cal"):
        render('<div class="cal-dowrow">' + "".join(f"<span>{n}</span>" for n in DIAS_CORTO) + "</div>")
        for semana in pycal.Calendar(0).monthdatescalendar(mes.year, mes.month):
            cols = st.columns(7)
            for col, d in zip(cols, semana):
                with col:
                    if d.month != mes.month:
                        st.empty()
                        continue
                    r = resumen_dia(d, datos[d], int(s["duracion"]))
                    fuera = d < hoy or d > max_fecha
                    estado = "pasado" if fuera else r["estado"]
                    deshabilitado = estado in ("pasado", "lleno", "cerrado", "bloqueado")
                    seleccionado = st.session_state.fecha == d
                    clave = f"dia_{d.strftime('%Y%m%d')}"
                    if not seleccionado:
                        bg, fg, bd = COLORES_ESTADO[estado]
                        css_dias.append(
                            f".stApp .st-key-{clave} button{{background:{bg}!important;color:{fg}!important;"
                            f"border-color:{bd}!important;box-shadow:none!important;"
                            f"{'text-decoration:line-through;' if estado == 'lleno' else ''}}}"
                        )
                    if st.button(str(d.day), key=clave, disabled=deshabilitado,
                                 type="primary" if seleccionado else "secondary", **ancho(st.button)):
                        st.session_state.fecha = d
                        st.session_state.hora = None
                        st.rerun()
    st.markdown("<style>" + "".join(css_dias) + "</style>", unsafe_allow_html=True)
    render(leyenda_html())

    fecha = st.session_state.fecha
    listo = False
    if fecha is not None and hoy <= fecha <= max_fecha:
        datos_f = cargar_datos(fecha, fecha)[fecha]
        slots = slots_dia(fecha, int(s["duracion"]), datos_f)
        if not any(libre for _, libre in slots):
            st.warning("Ya no hay horarios disponibles para este día. Prueba con otra fecha 💕")
        else:
            render(f'<div class="mini-title">🕒 Horarios para {fecha_bonita(fecha)}</div>'
                   '<div class="legend">Los horarios tachados ya están ocupados.</div>')
            with st.container(key="nowrap_slots"):
                for i in range(0, len(slots), 4):
                    cols = st.columns(4)
                    for col, (minuto, libre) in zip(cols, slots[i:i + 4]):
                        hhmm = a_hhmm(minuto)
                        with col:
                            if libre:
                                elegido = st.session_state.hora == hhmm
                                if st.button(hora_12(hhmm), key=f"slot_{hhmm}",
                                             type="primary" if elegido else "secondary", **ancho(st.button)):
                                    st.session_state.hora = hhmm
                                    st.rerun()
                            else:
                                st.button(hora_12(hhmm), key=f"slot_{hhmm}", disabled=True, **ancho(st.button))
        listo = bool(st.session_state.hora)

    render('<div style="height:.8rem"></div>')
    c1, c2 = st.columns(2)
    with c1:
        if st.button("← Cambiar servicio", **ancho(st.button)):
            st.session_state.paso = 1
            st.rerun()
    with c2:
        if st.button("Continuar →", type="primary", disabled=not listo, **ancho(st.button)):
            st.session_state.paso = 3
            st.rerun()


def paso_datos():
    s = servicio_actual()
    fecha, hora = st.session_state.fecha, st.session_state.hora
    if not s or not fecha or not hora:
        st.session_state.paso = 1 if not s else 2
        st.rerun()
    anticipo = calcular_anticipo(s["precio"])
    render('<div class="section-title">Tus datos</div>'
           '<div class="section-sub">Último paso: dinos quién eres y te generamos el enlace de WhatsApp.</div>')
    fila_anticipo = (f'<div class="summary-row"><span>Anticipo para apartar</span>'
                     f'<span>{dinero(anticipo)}</span></div>') if anticipo > 0 else ""
    render(
        f'<div class="summary">'
        f'<div class="summary-row"><span>Servicio</span><span>{esc(s["icono"])} {esc(s["nombre"])}</span></div>'
        f'<div class="summary-row"><span>Fecha</span><span>{fecha_bonita(fecha)}</span></div>'
        f'<div class="summary-row"><span>Hora</span><span>{hora_12(hora)}</span></div>'
        f'<div class="summary-row"><span>Duración</span><span>{s["duracion"]} min</span></div>'
        f'<div class="summary-row"><span>Total</span><span style="color:var(--oscuro);font-size:1.1rem">{dinero(s["precio"])}</span></div>'
        f'{fila_anticipo}</div>'
    )

    with st.form("form_datos"):
        nombre = st.text_input("👩 Tu nombre", placeholder="Ej. María López")
        telefono = st.text_input("📱 Tu WhatsApp", placeholder="10 dígitos, ej. 844 123 4567")
        notas = st.text_area("📝 Notas (opcional)", placeholder="Diseño favorito, color, alergias…", height=90)
        enviar = st.form_submit_button("Reservar mi cita 🌸", type="primary", **ancho(st.form_submit_button))

    if st.button("← Cambiar horario", **ancho(st.button)):
        st.session_state.paso = 2
        st.rerun()

    if enviar:
        tel = normalizar_telefono(telefono)
        if len(nombre.strip()) < 2:
            st.error("Por favor escribe tu nombre 💕")
            return
        if len(tel) < 12:
            st.error("Ingresa un número de WhatsApp válido de 10 dígitos 📱")
            return
        # Verificación final contra dobles reservas, días bloqueados y cambios de horario
        datos_f = cargar_datos(fecha, fecha)[fecha]
        libres = {a_hhmm(m) for m, libre in slots_dia(fecha, int(s["duracion"]), datos_f) if libre}
        if hora not in libres:
            st.error("😔 Ese horario acaba de ser reservado o ya no está disponible. Por favor elige otro.")
            st.session_state.hora = None
            st.session_state.paso = 2
            st.rerun()
        cita_id = ejecutar(
            """INSERT INTO citas(nombre, telefono, servicio, precio, duracion, fecha, hora, notas, estado, creado,
                                 anticipo_req, anticipo_pagado, pago_estado)
               VALUES(?,?,?,?,?,?,?,?, 'pendiente', ?, ?, 0, ?)""",
            (nombre.strip(), tel, s["nombre"], s["precio"], s["duracion"], fecha.isoformat(), hora,
             notas.strip(), ahora().isoformat(timespec="seconds"), anticipo,
             "pendiente" if anticipo > 0 else "no_requerido"),
        )
        st.session_state.ultima_cita = {
            "id": cita_id, "nombre": nombre.strip(), "servicio": s["nombre"], "precio": float(s["precio"]),
            "fecha": fecha, "hora": hora, "notas": notas.strip(), "anticipo": anticipo,
        }
        st.session_state.paso = 4
        st.rerun()


def paso_exito():
    c = st.session_state.ultima_cita
    if not c:
        reiniciar_reserva()
        st.rerun()
    nota = ("Falta un último detalle: realiza tu anticipo y envía el mensaje por WhatsApp para confirmar tu cita."
            if c["anticipo"] > 0 else
            "Falta un último detalle: envía el mensaje por WhatsApp para que el salón confirme tu cita.")
    render(
        f'<div class="success"><div class="big">🎉</div>'
        f'<h3>¡Tu cita está reservada, {esc(c["nombre"].split()[0])}!</h3>'
        f'<p style="margin:0">{nota}</p></div>'
        f'<div class="summary">'
        f'<div class="summary-row"><span>Servicio</span><span>{esc(c["servicio"])}</span></div>'
        f'<div class="summary-row"><span>Fecha</span><span>{fecha_bonita(c["fecha"])}</span></div>'
        f'<div class="summary-row"><span>Hora</span><span>{hora_12(c["hora"])}</span></div>'
        f'<div class="summary-row"><span>Total</span><span>{dinero(c["precio"])}</span></div></div>'
    )
    if c["anticipo"] > 0:
        horas = int(CFG.get("horas_pago") or 0)
        limite = (f"Tienes {horas} horas para enviar tu comprobante; después el horario se libera para otras clientas."
                  if horas > 0 else "Envía tu comprobante lo antes posible para asegurar tu horario.")
        render(
            f'<div class="pay-box"><div class="pay-title">💳 Anticipo para apartar tu horario</div>'
            f'<div class="pay-monto">{dinero(c["anticipo"])}</div>'
            f'<div class="pay-datos">{esc_br(CFG["datos_pago"])}</div>'
            f'<div class="pay-nota">{limite}</div></div>'
        )
    lineas = [
        f"¡Hola {CFG['nombre']}! 🌸",
        f"Soy {c['nombre']} y quiero confirmar mi cita:",
        "",
        f"💅 Servicio: {c['servicio']}",
        f"📅 Fecha: {fecha_bonita(c['fecha'])}",
        f"🕒 Hora: {hora_12(c['hora'])}",
        f"💰 Total: {dinero_txt(c['precio'])}",
    ]
    if c["anticipo"] > 0:
        lineas.append(f"💳 Anticipo: {dinero_txt(c['anticipo'])} (adjunto mi comprobante)")
    if c["notas"]:
        lineas.append(f"📝 Notas: {c['notas']}")
    lineas += ["", "¡Gracias! ✨"]
    destino = normalizar_telefono(CFG["whatsapp"])
    st.link_button("💬 Enviar confirmación por WhatsApp", enlace_whatsapp(destino, "\n".join(lineas)),
                   **ancho(st.link_button))
    render('<div style="height:.6rem"></div>')
    if st.button("Agendar otra cita 💖", **ancho(st.button)):
        reiniciar_reserva()
        st.rerun()


def vista_reservar():
    paso = st.session_state.paso
    stepper(min(paso, 3) if paso < 4 else 4)
    if paso == 1:
        paso_servicio()
    elif paso == 2:
        paso_horario()
    elif paso == 3:
        paso_datos()
    else:
        paso_exito()


# ══════════════════════════════════════════════════════════════
# GALERÍA Y CONTACTO (PÚBLICO)
# ══════════════════════════════════════════════════════════════
def vista_galeria():
    render('<div class="section-title">Nuestro trabajo</div>'
           '<div class="section-sub">Inspírate con algunos de nuestros diseños 💅</div>')
    cats = [f["categoria"] for f in consultar("SELECT DISTINCT categoria FROM catalogo WHERE categoria!='' ORDER BY categoria")]
    categoria = "Todo"
    if cats:
        categoria = st.radio("Categoría", ["Todo"] + cats, horizontal=True, key="gal_cat", label_visibility="collapsed")
    fotos = cargar_catalogo(version_catalogo(), int(st.session_state.gal_n), categoria)
    if not fotos:
        st.info("Muy pronto subiremos fotos de nuestros trabajos 🌸")
        return
    cols = st.columns(3)
    for i, f in enumerate(fotos):
        with cols[i % 3]:
            st.image(f["imagen"], caption=f["titulo"] or None, **ancho(st.image))
    if len(fotos) >= int(st.session_state.gal_n):
        if st.button("Ver más fotos ✨", key="gal_mas"):
            st.session_state.gal_n += 12
            st.rerun()


def vista_contacto():
    render('<div class="section-title">Visítanos</div>'
           '<div class="section-sub">Aquí encontrarás nuestro horario y cómo contactarnos.</div>')
    filas = []
    for i in range(7):
        h = CFG["horario"][str(i)]
        txt = f'{hora_12(h["ini"])} – {hora_12(h["fin"])}' if h["abierto"] else "Cerrado"
        filas.append(f'<div class="summary-row"><span>{DIAS[i].capitalize()}</span><span>{txt}</span></div>')
    c1, c2 = st.columns(2)
    with c1:
        render(f'<div class="panel"><h4>🕒 Horario de atención</h4>{"".join(filas)}</div>')
    with c2:
        direccion = esc_br(CFG["direccion"]) if CFG["direccion"] else "Pregúntanos por WhatsApp"
        render(f'<div class="panel"><h4>📍 Ubicación</h4><div>{direccion}</div></div>')
        hoy_iso = ahora().date().isoformat()
        proximos = consultar("SELECT * FROM bloqueos WHERE fecha_fin>=? AND hora_ini='' ORDER BY fecha_ini LIMIT 5", (hoy_iso,))
        if proximos:
            items = ""
            for b in proximos:
                ini, fin = date.fromisoformat(b["fecha_ini"]), date.fromisoformat(b["fecha_fin"])
                rango = fecha_corta(ini) if ini == fin else f"{fecha_corta(ini)} al {fecha_corta(fin)}"
                items += f'<div class="summary-row"><span>{rango}</span><span>{esc(b["motivo"] or b["tipo"])}</span></div>'
            render(f'<div class="panel"><h4>🌷 Próximos días sin servicio</h4>{items}</div>')
    destino = normalizar_telefono(CFG["whatsapp"])
    b1, b2 = st.columns(2)
    with b1:
        if destino:
            st.link_button("💬 Escríbenos por WhatsApp", f"https://wa.me/{destino}", **ancho(st.link_button))
    with b2:
        if url_maps():
            st.link_button("📍 Cómo llegar", url_maps(), **ancho(st.link_button))
    rs = [r for r in redes() if r[1] != "WhatsApp"]
    if rs:
        pills = "".join(f'<a class="pill" href="{esc(u)}" target="_blank" rel="noopener">{e} {n}</a>' for e, n, u in rs)
        render(f'<div class="mini-title" style="text-align:center">Síguenos</div><div class="pills">{pills}</div>')


# ══════════════════════════════════════════════════════════════
# PANEL DE ADMINISTRACIÓN
# ══════════════════════════════════════════════════════════════
ETIQUETA_ESTADO = {"pendiente": ("⏳ Pendiente", "b-pend"),
                   "confirmada": ("✅ Confirmada", "b-ok"),
                   "cancelada": ("✖ Cancelada", "b-no")}
PAGO_FILTROS = {"Todos": None, "💳 Anticipo pendiente": "pendiente",
                "✅ Anticipo pagado": "pagado", "Sin anticipo": "no_requerido"}


def metrica(icono, numero, texto):
    render(f'<div class="metric"><div class="ico">{icono}</div><div class="num">{numero}</div><div class="txt">{texto}</div></div>')


def barras(items) -> str:
    if not items:
        return '<div class="cita-det">Aún no hay datos.</div>'
    maximo = max(n for _, n in items) or 1
    return "".join(
        f'<div class="bar-row"><span class="bar-l">{esc(label)}</span>'
        f'<div class="bar"><div style="width:{n / maximo * 100:.0f}%"></div></div><span class="bar-n">{n}</span></div>'
        for label, n in items
    )


# ---------- Citas ----------
def admin_citas():
    hoy_iso = ahora().date().isoformat()
    citas_hoy = consultar("SELECT * FROM citas WHERE fecha=? AND estado!='cancelada'", (hoy_iso,))
    ingresos = sum(float(c["precio"]) for c in citas_hoy)
    cobrar = consultar(
        "SELECT COUNT(*) AS n, COALESCE(SUM(anticipo_req - anticipo_pagado),0) AS monto FROM citas "
        "WHERE estado!='cancelada' AND pago_estado='pendiente' AND fecha>=?", (hoy_iso,))[0]
    pendientes = consultar("SELECT COUNT(*) AS n FROM citas WHERE estado='pendiente' AND fecha>=?", (hoy_iso,))[0]["n"]

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        metrica("📅", len(citas_hoy), "Citas de hoy")
    with m2:
        metrica("⏳", pendientes, "Por confirmar")
    with m3:
        metrica("💳", dinero(max(cobrar["monto"], 0)), f"Anticipos por cobrar ({cobrar['n']})")
    with m4:
        metrica("💰", dinero(ingresos), "Ingresos estimados hoy")

    render('<div style="height:1rem"></div>')
    f1, f2, f3 = st.columns([2.2, 1.4, 1.6])
    with f1:
        rango = st.radio("Ver citas", ["Hoy", "Próximas", "Todas"], horizontal=True, index=1, key="adm_rango")
    with f2:
        estado_f = st.selectbox("Estado", ["Todos", "Pendiente", "Confirmada", "Cancelada"], key="adm_estado")
    with f3:
        pago_f = st.selectbox("Pago / anticipo", list(PAGO_FILTROS), key="adm_pago")

    sql, params = "SELECT * FROM citas WHERE 1=1", []
    if rango == "Hoy":
        sql += " AND fecha=?"
        params.append(hoy_iso)
    elif rango == "Próximas":
        sql += " AND fecha>=?"
        params.append(hoy_iso)
    if estado_f != "Todos":
        sql += " AND estado=?"
        params.append(estado_f.lower())
    if PAGO_FILTROS[pago_f]:
        sql += " AND pago_estado=?"
        params.append(PAGO_FILTROS[pago_f])
    sql += " ORDER BY fecha ASC, hora ASC"
    citas = consultar(sql, tuple(params))

    if not citas:
        render('<div class="summary" style="text-align:center;margin-top:1rem">🌷 No hay citas para mostrar con estos filtros.</div>')
        return

    iconos = {s["nombre"]: s["icono"] for s in servicios_lista(False)}
    for c in citas:
        etiqueta, clase_badge = ETIQUETA_ESTADO[c["estado"]]
        pago_txt, pago_clase = texto_pago(c)
        fecha_c = date.fromisoformat(c["fecha"])
        notas = f'<div class="cita-det">📝 {esc(c["notas"])}</div>' if c["notas"] else ""
        metodo = f' · {esc(c["metodo_pago"])}' if c.get("metodo_pago") else ""
        badges = f'<span class="badge {clase_badge}">{etiqueta}</span>'
        if c["estado"] != "cancelada":
            badges += f'<span class="badge {pago_clase}">{pago_txt}{metodo}</span>'
        render(
            f'<div class="cita {c["estado"]}"><div class="cita-top"><div>'
            f'<div class="cita-hora">🕒 {hora_12(c["hora"])}</div><div class="cita-fecha">{fecha_bonita(fecha_c)}</div></div>'
            f'<div class="badges">{badges}</div></div>'
            f'<div class="cita-nombre" style="margin-top:.5rem">{esc(c["nombre"])}</div>'
            f'<div class="cita-det">{esc(iconos.get(c["servicio"], "💅"))} {esc(c["servicio"])} · {dinero(c["precio"])} · ⏱ {c["duracion"]} min</div>'
            f'<div class="cita-det">📱 +{esc(c["telefono"])}</div>{notas}</div>'
        )
        req, pag = float(c["anticipo_req"] or 0), float(c["anticipo_pagado"] or 0)
        bloqueada_por_pago = bool(CFG.get("anticipo_obligatorio")) and c["pago_estado"] == "pendiente"
        puede_confirmar = c["estado"] == "pendiente" and not bloqueada_por_pago

        b1, b2, b3, b4 = st.columns(4)
        with b1:
            if st.button("✅ Confirmar", key=f"ok_{c['id']}", disabled=not puede_confirmar, **ancho(st.button)):
                ejecutar("UPDATE citas SET estado='confirmada' WHERE id=?", (c["id"],))
                st.rerun()
        with b2:
            if c["estado"] != "cancelada":
                with st.popover("💵 Anticipo", **ancho(st.popover)):
                    if c["pago_estado"] == "pagado":
                        st.write(f"Pagado: {pag:,.0f} MXN · {c['metodo_pago'] or 'sin método'}")
                        if st.button("↩️ Quitar pago", key=f"unpay_{c['id']}"):
                            quitar_pago(c["id"], req)
                            st.rerun()
                    else:
                        st.write(f"Anticipo solicitado: {req:,.0f} MXN · recibido: {pag:,.0f} MXN")
                        monto = st.number_input("Monto recibido ahora (MXN)", min_value=0.0,
                                                value=float(max(req - pag, 0.0)), step=10.0, key=f"pay_m_{c['id']}")
                        metodo_sel = st.selectbox("Método de pago", METODOS_PAGO, key=f"pay_t_{c['id']}")
                        if st.button("Guardar pago", type="primary", key=f"pay_ok_{c['id']}"):
                            registrar_pago(c["id"], pag + monto, metodo_sel, req)
                            st.rerun()
            else:
                st.empty()
        with b3:
            if st.button("❌ Cancelar", key=f"no_{c['id']}", disabled=c["estado"] == "cancelada", **ancho(st.button)):
                ejecutar("UPDATE citas SET estado='cancelada' WHERE id=?", (c["id"],))
                st.rerun()
        with b4:
            st.link_button("💬 WhatsApp", enlace_whatsapp(c["telefono"], mensaje_cliente(c)), **ancho(st.link_button))
        if c["estado"] == "pendiente" and bloqueada_por_pago:
            st.caption("💳 Registra el anticipo para poder confirmar esta cita.")


# ---------- Calendario ----------
def admin_calendario():
    render('<div class="section-title">Calendario de demanda</div>'
           '<div class="section-sub">Descubre cuáles son tus días más cotizados y cuáles ya están llenos.</div>')
    hoy = ahora().date()
    minimo, maximo = mes_offset(hoy.replace(day=1), -12), mes_offset(hoy.replace(day=1), 12)
    if "cal_adm" not in st.session_state:
        st.session_state.cal_adm = hoy.replace(day=1)
    mes = navegador_mes("cal_adm", minimo, maximo)
    ultimo = mes_offset(mes, 1) - timedelta(days=1)
    datos = cargar_datos(mes, ultimo)
    dur = duracion_minima()

    citas_mes = sum(len(v["citas"]) for v in datos.values())
    ingreso_mes = sum(float(c["precio"]) for v in datos.values() for c in v["citas"])
    llenos = sum(1 for d, v in datos.items() if resumen_dia(d, v, dur)["estado"] == "lleno")
    m1, m2, m3 = st.columns(3)
    with m1:
        metrica("📅", citas_mes, "Citas del mes")
    with m2:
        metrica("💰", dinero(ingreso_mes), "Ingresos estimados")
    with m3:
        metrica("🔥", llenos, "Días llenos")

    render('<div style="height:.8rem"></div>')
    render(calendario_html(mes, datos, dur))
    render(leyenda_html())

    filas = consultar("SELECT fecha, hora, servicio FROM citas WHERE estado!='cancelada'")
    render('<div class="mini-title">📊 Lo más cotizado</div>')
    if not filas:
        st.info("Cuando tengas citas, aquí verás tus días y horas favoritas.")
        return
    por_sem, por_fecha, por_hora, por_srv = Counter(), Counter(), Counter(), Counter()
    for f in filas:
        por_sem[date.fromisoformat(f["fecha"]).weekday()] += 1
        por_fecha[f["fecha"]] += 1
        por_hora[f["hora"]] += 1
        por_srv[f["servicio"]] += 1
    c1, c2 = st.columns(2)
    with c1:
        dias_rank = sorted(((DIAS[i].capitalize(), por_sem.get(i, 0)) for i in range(7)), key=lambda x: -x[1])
        render(f'<div class="panel"><h4>Días de la semana</h4>{barras(dias_rank)}</div>')
        horas_rank = [(hora_12(h), n) for h, n in por_hora.most_common(5)]
        render(f'<div class="panel"><h4>Horarios favoritos</h4>{barras(horas_rank)}</div>')
    with c2:
        fechas_rank = [(fecha_bonita(date.fromisoformat(f)), n) for f, n in por_fecha.most_common(5)]
        render(f'<div class="panel"><h4>Fechas con más citas</h4>{barras(fechas_rank)}</div>')
        render(f'<div class="panel"><h4>Servicios más pedidos</h4>{barras(por_srv.most_common(5))}</div>')


# ---------- Horario y días libres ----------
def n_dia_semana(anio: int, mes: int, dia_sem: int, n: int) -> date:
    d = date(anio, mes, 1)
    d += timedelta(days=(dia_sem - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def festivos_mx(anio: int, extra: bool = False):
    f = [(date(anio, 1, 1), "Año Nuevo"),
         (n_dia_semana(anio, 2, 0, 1), "Día de la Constitución"),
         (n_dia_semana(anio, 3, 0, 3), "Natalicio de Benito Juárez"),
         (date(anio, 5, 1), "Día del Trabajo"),
         (date(anio, 9, 16), "Día de la Independencia"),
         (n_dia_semana(anio, 11, 0, 3), "Día de la Revolución"),
         (date(anio, 12, 25), "Navidad")]
    if extra:
        f += [(date(anio, 12, 24), "Nochebuena"), (date(anio, 12, 31), "Fin de año")]
    return sorted(f)


def admin_horario():
    render('<div class="section-title">Horario de trabajo</div>'
           '<div class="section-sub">Define qué días abres y a qué hora. Los cambios aplican de inmediato en la reserva.</div>')
    with st.form("form_horario"):
        for i in range(7):
            h = CFG["horario"][str(i)]
            opciones = list(OPCIONES_HORA)
            for v in (h["ini"], h["fin"]):
                if v not in opciones:
                    opciones.append(v)
            opciones.sort()
            c0, c1, c2, c3 = st.columns([1.6, 1.2, 1.6, 1.6])
            with c0:
                st.markdown(f"**{DIAS[i].capitalize()}**")
            with c1:
                st.checkbox("Abierto", value=bool(h["abierto"]), key=f"h_ab_{i}")
            with c2:
                st.selectbox("Abre", opciones, index=opciones.index(h["ini"]), format_func=hora_12,
                             key=f"h_ini_{i}", label_visibility="collapsed")
            with c3:
                st.selectbox("Cierra", opciones, index=opciones.index(h["fin"]), format_func=hora_12,
                             key=f"h_fin_{i}", label_visibility="collapsed")
        k1, k2, k3 = st.columns(3)
        with k1:
            intervalo = st.selectbox("Una cita puede iniciar cada", [15, 20, 30, 45, 60],
                                     index=[15, 20, 30, 45, 60].index(int(CFG["intervalo"])) if int(CFG["intervalo"]) in [15, 20, 30, 45, 60] else 2,
                                     format_func=lambda m: f"{m} minutos", key="h_intervalo")
        with k2:
            dias_adelante = st.number_input("Agendar hasta (días adelante)", min_value=7, max_value=365,
                                            value=int(CFG["dias_adelante"]), step=1, key="h_dias")
        with k3:
            antic = st.number_input("Anticipación mínima (minutos)", min_value=0, max_value=2880,
                                    value=int(CFG["anticipacion_min"]), step=15, key="h_antic")
        guardar = st.form_submit_button("💾 Guardar horario", type="primary", **ancho(st.form_submit_button))
    if guardar:
        nuevo, error = {}, None
        for i in range(7):
            ab = bool(st.session_state[f"h_ab_{i}"])
            ini, fin = st.session_state[f"h_ini_{i}"], st.session_state[f"h_fin_{i}"]
            if ab and a_minutos(fin) <= a_minutos(ini):
                error = f"En {DIAS[i]} la hora de cierre debe ser después de la apertura."
            nuevo[str(i)] = {"abierto": ab, "ini": ini, "fin": fin}
        if error:
            st.error(error)
        else:
            guardar_config(horario=nuevo, intervalo=int(intervalo), dias_adelante=int(dias_adelante),
                           anticipacion_min=int(antic))
            avisar("Horario actualizado")
            st.rerun()

    # ----- Días libres / asuetos -----
    render('<div class="mini-title">🗓️ Días libres, asuetos y vacaciones</div>'
           '<div class="section-sub">Los días o rangos que agregues se bloquean automáticamente para las clientas.</div>')
    n = st.session_state.blq_n
    hoy = ahora().date()
    tipo = st.selectbox("Tipo", ["Día libre", "Asueto / festivo", "Vacaciones", "Evento personal", "Otro"], key=f"blq_tipo_{n}")
    d1, d2 = st.columns(2)
    with d1:
        f_ini = st.date_input("Desde", value=hoy, min_value=hoy, format="DD/MM/YYYY", key=f"blq_ini_{n}")
    with d2:
        f_fin = st.date_input("Hasta (inclusive)", value=hoy, min_value=hoy, format="DD/MM/YYYY", key=f"blq_fin_{n}")
    todo_dia = st.checkbox("Bloquear todo el día", value=True, key=f"blq_todo_{n}")
    h_ini = h_fin = ""
    if not todo_dia:
        t1, t2 = st.columns(2)
        with t1:
            h_ini = st.selectbox("De", OPCIONES_HORA, index=OPCIONES_HORA.index("14:00"), format_func=hora_12, key=f"blq_hi_{n}")
        with t2:
            h_fin = st.selectbox("A", OPCIONES_HORA, index=OPCIONES_HORA.index("16:00"), format_func=hora_12, key=f"blq_hf_{n}")
    motivo = st.text_input("Motivo (opcional)", placeholder="Ej. Navidad, Vacaciones de verano, Curso", key=f"blq_mot_{n}")
    if st.button("➕ Agregar bloqueo", type="primary", key=f"blq_add_{n}"):
        if f_fin < f_ini:
            st.error("La fecha final no puede ser antes de la inicial.")
        elif not todo_dia and a_minutos(h_fin) <= a_minutos(h_ini):
            st.error("La hora final debe ser después de la inicial.")
        else:
            ejecutar("INSERT INTO bloqueos(fecha_ini, fecha_fin, hora_ini, hora_fin, tipo, motivo) VALUES(?,?,?,?,?,?)",
                     (f_ini.isoformat(), f_fin.isoformat(), "" if todo_dia else h_ini, "" if todo_dia else h_fin,
                      tipo, motivo.strip()))
            afectadas = consultar("SELECT COUNT(*) AS n FROM citas WHERE fecha BETWEEN ? AND ? AND estado!='cancelada'",
                                  (f_ini.isoformat(), f_fin.isoformat()))[0]["n"]
            st.session_state.blq_n += 1
            if afectadas:
                avisar(f"Bloqueo agregado. Ojo: ya tienes {afectadas} cita(s) en ese rango; revísalas y avisa a tus clientas.", "⚠️")
            else:
                avisar("Bloqueo agregado")
            st.rerun()

    with st.expander("🎉 Cargar festivos oficiales de México"):
        anios = [hoy.year, hoy.year + 1]
        anio = st.radio("Año", anios, horizontal=True, key="fest_anio")
        extra = st.checkbox("Incluir también 24 y 31 de diciembre", key="fest_extra")
        if st.button("Agregar festivos", key="fest_add"):
            nuevos = 0
            for d, nombre in festivos_mx(int(anio), extra):
                if d < hoy:
                    continue
                existe = consultar("SELECT id FROM bloqueos WHERE fecha_ini=? AND fecha_fin=? AND hora_ini=''",
                                   (d.isoformat(), d.isoformat()))
                if not existe:
                    ejecutar("INSERT INTO bloqueos(fecha_ini, fecha_fin, hora_ini, hora_fin, tipo, motivo) VALUES(?,?,?,?,?,?)",
                             (d.isoformat(), d.isoformat(), "", "", "Asueto / festivo", nombre))
                    nuevos += 1
            avisar(f"Se agregaron {nuevos} festivos", "🎉")
            st.rerun()

    bloqueos = consultar("SELECT * FROM bloqueos WHERE fecha_fin>=? ORDER BY fecha_ini, hora_ini", (hoy.isoformat(),))
    render('<div class="mini-title">Próximos bloqueos</div>')
    if not bloqueos:
        st.caption("No tienes días bloqueados por ahora.")
    for b in bloqueos:
        ini, fin = date.fromisoformat(b["fecha_ini"]), date.fromisoformat(b["fecha_fin"])
        rango = fecha_corta(ini) if ini == fin else f"{fecha_corta(ini)} → {fecha_corta(fin)}"
        horas = "Todo el día" if not b["hora_ini"] else f"{hora_12(b['hora_ini'])} – {hora_12(b['hora_fin'])}"
        c1, c2 = st.columns([5, 1], vertical_alignment="center")
        with c1:
            render(f'<div class="blq"><b>{rango}</b> · {esc(b["tipo"])}<br>'
                   f'<small>{horas}{" · " + esc(b["motivo"]) if b["motivo"] else ""}</small></div>')
        with c2:
            if st.button("🗑️", key=f"del_blq_{b['id']}", help="Quitar bloqueo", **ancho(st.button)):
                ejecutar("DELETE FROM bloqueos WHERE id=?", (b["id"],))
                st.rerun()


# ---------- Servicios ----------
def _formulario_servicio(s, prefijo: str):
    """Dibuja los campos de un servicio dentro de un formulario. Devuelve los valores."""
    c1, c2 = st.columns([3, 1])
    nombre = c1.text_input("Nombre", value=s["nombre"] if s else "", key=f"{prefijo}_n")
    icono = c2.text_input("Emoji", value=s["icono"] if s else "💅", key=f"{prefijo}_i")
    desc = st.text_area("Descripción", value=s["descripcion"] if s else "", height=80, key=f"{prefijo}_d")
    c3, c4, c5 = st.columns(3)
    precio = c3.number_input("Precio (MXN)", min_value=0.0, value=float(s["precio"]) if s else 200.0, step=10.0, key=f"{prefijo}_p")
    duracion = c4.number_input("Duración (min)", min_value=15, max_value=480, value=int(s["duracion"]) if s else 60, step=15, key=f"{prefijo}_t")
    orden = c5.number_input("Orden", min_value=0, value=int(s["orden"]) if s else len(servicios_lista(False)), step=1, key=f"{prefijo}_o")
    visible = st.checkbox("Visible para las clientas", value=bool(s["activo"]) if s else True, key=f"{prefijo}_v")
    archivo = st.file_uploader("Imagen del servicio (JPG, PNG o WEBP)", type=["jpg", "jpeg", "png", "webp"], key=f"{prefijo}_f")
    quitar = False
    if s and s["tiene_img"]:
        quitar = st.checkbox("Quitar la imagen actual", key=f"{prefijo}_q")
    return nombre, icono, desc, precio, duracion, orden, visible, archivo, quitar


def admin_servicios():
    render('<div class="section-title">Servicios</div>'
           '<div class="section-sub">Edita nombres, precios, duración e imágenes. Los cambios se ven al instante.</div>')
    for s in servicios_lista(False):
        oculto = "" if s["activo"] else " · (oculto)"
        with st.expander(f"{s['icono']} {s['nombre']} · {dinero_label(s['precio'])} · {s['duracion']} min{oculto}"):
            if s["tiene_img"]:
                blob = consultar("SELECT imagen FROM servicios WHERE id=?", (s["id"],))[0]["imagen"]
                st.image(blob, width=200)
            with st.form(f"form_svc_{s['id']}"):
                nombre, icono, desc, precio, duracion, orden, visible, archivo, quitar = _formulario_servicio(s, f"svc{s['id']}")
                guardar = st.form_submit_button("💾 Guardar cambios", type="primary", **ancho(st.form_submit_button))
            if guardar:
                if len(nombre.strip()) < 2:
                    st.error("El servicio necesita un nombre.")
                else:
                    try:
                        ejecutar("UPDATE servicios SET nombre=?, descripcion=?, precio=?, duracion=?, icono=?, activo=?, orden=? WHERE id=?",
                                 (nombre.strip(), desc.strip(), precio, int(duracion), icono.strip() or "💅",
                                  1 if visible else 0, int(orden), s["id"]))
                        if archivo is not None:
                            ejecutar("UPDATE servicios SET imagen=?, img_ver=img_ver+1 WHERE id=?",
                                     (procesar_imagen(archivo, 640, 480), s["id"]))
                        elif quitar:
                            ejecutar("UPDATE servicios SET imagen=NULL, img_ver=img_ver+1 WHERE id=?", (s["id"],))
                        avisar("Servicio actualizado")
                        st.rerun()
                    except Exception:
                        st.error("No pude leer esa imagen. Prueba con otra en JPG o PNG.")
            with st.popover("🗑️ Eliminar servicio"):
                st.write("Las citas anteriores conservan su información.")
                if st.button("Sí, eliminar", key=f"del_svc_{s['id']}"):
                    ejecutar("DELETE FROM servicios WHERE id=?", (s["id"],))
                    avisar("Servicio eliminado", "🗑️")
                    st.rerun()

    with st.expander("➕ Agregar servicio nuevo"):
        with st.form("form_svc_nuevo", clear_on_submit=True):
            nombre, icono, desc, precio, duracion, orden, visible, archivo, _ = _formulario_servicio(None, "svcnew")
            crear = st.form_submit_button("➕ Crear servicio", type="primary", **ancho(st.form_submit_button))
        if crear:
            if len(nombre.strip()) < 2:
                st.error("El servicio necesita un nombre.")
            else:
                try:
                    blob = procesar_imagen(archivo, 640, 480) if archivo is not None else None
                    ejecutar("INSERT INTO servicios(nombre, descripcion, precio, duracion, icono, imagen, activo, orden) VALUES(?,?,?,?,?,?,?,?)",
                             (nombre.strip(), desc.strip(), precio, int(duracion), icono.strip() or "💅", blob,
                              1 if visible else 0, int(orden)))
                    avisar("Servicio creado", "🎉")
                    st.rerun()
                except Exception:
                    st.error("No pude leer esa imagen. Prueba con otra en JPG o PNG.")


# ---------- Catálogo ----------
def admin_catalogo():
    render('<div class="section-title">Catálogo de trabajos</div>'
           '<div class="section-sub">Sube fotos de tus diseños para que tus clientas se inspiren.</div>')
    with st.form("form_cat", clear_on_submit=True):
        archivos = st.file_uploader("Fotos (puedes elegir varias)", type=["jpg", "jpeg", "png", "webp"],
                                    accept_multiple_files=True, key="cat_files")
        c1, c2 = st.columns(2)
        titulo = c1.text_input("Título (opcional)", key="cat_t")
        categoria = c2.text_input("Categoría", placeholder="Ej. Acrílicas, Francés, Nail art", key="cat_c")
        subir = st.form_submit_button("⬆️ Subir al catálogo", type="primary", **ancho(st.form_submit_button))
    if subir:
        if not archivos:
            st.warning("Elige al menos una foto.")
        else:
            ok = 0
            for a in archivos:
                try:
                    ejecutar("INSERT INTO catalogo(titulo, categoria, imagen, creado) VALUES(?,?,?,?)",
                             (titulo.strip(), categoria.strip(), procesar_imagen(a, 1000), ahora().isoformat(timespec="seconds")))
                    ok += 1
                except Exception:
                    st.error(f"No pude leer «{a.name}».")
            if ok:
                avisar(f"Se subieron {ok} foto(s)", "🖼️")
                st.rerun()

    fotos = cargar_catalogo(version_catalogo(), 500, "Todo")
    render(f'<div class="mini-title">Tu catálogo ({len(fotos)} fotos)</div>')
    if not fotos:
        st.caption("Aún no has subido fotos.")
        return
    cols = st.columns(3)
    for i, f in enumerate(fotos):
        with cols[i % 3]:
            st.image(f["imagen"], caption=" · ".join(x for x in (f["titulo"], f["categoria"]) if x) or None,
                     **ancho(st.image))
            if st.button("🗑️ Eliminar", key=f"del_cat_{f['id']}", **ancho(st.button)):
                ejecutar("DELETE FROM catalogo WHERE id=?", (f["id"],))
                st.rerun()


# ---------- Anticipos ----------
def admin_anticipos():
    render('<div class="section-title">Anticipos y pagos</div>'
           '<div class="section-sub">Configura el anticipo que piden tus citas y los datos para que te paguen.</div>')
    modos = {"ninguno": "Sin anticipo", "porcentaje": "Porcentaje del total", "fijo": "Monto fijo (MXN)"}
    with st.form("form_anticipos"):
        modo = st.selectbox("Tipo de anticipo", list(modos), format_func=lambda k: modos[k],
                            index=list(modos).index(CFG["anticipo_modo"]) if CFG["anticipo_modo"] in modos else 1, key="ant_modo")
        valor = st.number_input("Valor (% o monto en MXN, según el tipo)", min_value=0.0, value=float(CFG["anticipo_valor"]), step=5.0, key="ant_val")
        obligatorio = st.checkbox("Exigir anticipo pagado para poder confirmar la cita", value=bool(CFG["anticipo_obligatorio"]), key="ant_obl")
        horas = st.number_input("Liberar el horario si no llega el anticipo en (horas). 0 = nunca", min_value=0, max_value=720,
                                value=int(CFG["horas_pago"]), step=1, key="ant_horas")
        datos = st.text_area("Datos de pago que verá la clienta (banco, CLABE, titular…)", value=CFG["datos_pago"], height=130, key="ant_datos")
        guardar = st.form_submit_button("💾 Guardar", type="primary", **ancho(st.form_submit_button))
    if guardar:
        guardar_config(anticipo_modo=modo, anticipo_valor=float(valor), anticipo_obligatorio=bool(obligatorio),
                       horas_pago=int(horas), datos_pago=datos.strip())
        avisar("Configuración de anticipos guardada", "💳")
        st.rerun()
    filas = "".join(
        f'<div class="summary-row"><span>{esc(s["icono"])} {esc(s["nombre"])} ({dinero(s["precio"])})</span>'
        f'<span>{dinero(calcular_anticipo(s["precio"])) if calcular_anticipo(s["precio"]) > 0 else "Sin anticipo"}</span></div>'
        for s in servicios_lista()
    )
    render(f'<div class="panel"><h4>Así se verá el anticipo de cada servicio</h4>{filas}</div>')


# ---------- Negocio y apariencia ----------
def vista_previa_tema(t: dict):
    c = t["c"]
    muestras = "".join(f'<span class="swatch" style="background:{c[k]}"></span>' for k in ("pastel", "medio", "fuerte", "oscuro", "titulo"))
    render(
        f'<div class="theme-prev" style="background:linear-gradient(135deg,{c["hero1"]},{c["hero2"]},{c["hero3"]})">'
        f'<div class="hero-deco" style="margin:0">{" ".join(t["emojis"])}</div>'
        f'<div class="theme-name" style="color:{c["titulo"]}">{esc(t["nombre"])}</div><div>{muestras}</div></div>'
    )


def admin_negocio():
    render('<div class="section-title">Mi negocio</div>'
           '<div class="section-sub">Nombre, contacto y redes sociales.</div>')
    with st.form("form_negocio"):
        nombre = st.text_input("Nombre del salón", value=CFG["nombre"], key="neg_n")
        slogan = st.text_input("Frase de bienvenida", value=CFG["slogan"], key="neg_s")
        wa = st.text_input("WhatsApp del salón (con código de país)", value=CFG["whatsapp"], key="neg_w",
                           help="Ejemplo para México: 528441234567")
        direccion = st.text_area("Dirección", value=CFG["direccion"], height=70, key="neg_d")
        maps = st.text_input("Enlace de Google Maps (opcional)", value=CFG["maps"], key="neg_m")
        r1, r2 = st.columns(2)
        ig = r1.text_input("📸 Instagram", value=CFG["instagram"], placeholder="@tusalon", key="neg_ig")
        fb = r2.text_input("👍 Facebook", value=CFG["facebook"], placeholder="tusalon o enlace completo", key="neg_fb")
        tt = r1.text_input("🎵 TikTok", value=CFG["tiktok"], placeholder="@tusalon", key="neg_tt")
        web = r2.text_input("🌐 Sitio web", value=CFG["web"], placeholder="www.tusalon.com", key="neg_web")
        guardar = st.form_submit_button("💾 Guardar datos", type="primary", **ancho(st.form_submit_button))
    if guardar:
        if len(nombre.strip()) < 2:
            st.error("Escribe el nombre del salón.")
        else:
            guardar_config(nombre=nombre.strip(), slogan=slogan.strip(), whatsapp=normalizar_telefono(wa),
                           direccion=direccion.strip(), maps=maps.strip(), instagram=ig.strip(),
                           facebook=fb.strip(), tiktok=tt.strip(), web=web.strip())
            avisar("Datos del negocio guardados")
            st.rerun()

    render('<div class="mini-title">🎨 Apariencia por temporada</div>'
           '<div class="section-sub">La app cambia sola según la fecha (Navidad, Reyes, San Valentín, Día de Muertos…). También puedes fijar un tema.</div>')
    opciones = ["auto"] + list(TEMAS)
    actual = CFG["tema"] if CFG["tema"] in opciones else "auto"
    sel = st.selectbox("Tema", opciones, index=opciones.index(actual), key="tema_sel",
                       format_func=lambda k: "🔄 Automático (según la fecha)" if k == "auto" else TEMAS[k]["nombre"])
    clave_prev = tema_para(ahora().date()) if sel == "auto" else sel
    if sel == "auto":
        st.caption(f"Hoy se aplicaría: {TEMAS[clave_prev]['nombre']}")
    vista_previa_tema(TEMAS[clave_prev])
    anim = st.checkbox("Mostrar decoración animada de temporada", value=bool(CFG["animacion"]), key="tema_anim")
    if st.button("Aplicar apariencia", type="primary", key="tema_ok"):
        guardar_config(tema=sel, animacion=bool(anim))
        avisar("Apariencia actualizada", "🎨")
        st.rerun()


# ---------- Contenedor del panel ----------
def vista_admin():
    if not st.session_state.admin_ok:
        render('<div class="section-title">Acceso del salón</div>'
               '<div class="section-sub">Ingresa tu contraseña para administrar las citas.</div>')
        with st.form("login_admin"):
            pwd = st.text_input("🔐 Contraseña", type="password")
            entrar = st.form_submit_button("Entrar", type="primary", **ancho(st.form_submit_button))
        if entrar:
            if pwd == password_admin():
                st.session_state.admin_ok = True
                st.rerun()
            else:
                st.error("Contraseña incorrecta.")
        return

    c_t, c_b = st.columns([4, 1], vertical_alignment="center")
    with c_t:
        render('<div class="section-title">Panel de administración</div>'
               f'<div class="section-sub">{fecha_bonita(ahora().date())}</div>')
    with c_b:
        if st.button("Cerrar sesión", **ancho(st.button)):
            st.session_state.admin_ok = False
            st.rerun()

    t = st.tabs(["📋 Citas", "📆 Calendario", "🗓️ Horario", "💅 Servicios", "🖼️ Catálogo", "💳 Anticipos", "⚙️ Negocio"])
    with t[0]:
        admin_citas()
    with t[1]:
        admin_calendario()
    with t[2]:
        admin_horario()
    with t[3]:
        admin_servicios()
    with t[4]:
        admin_catalogo()
    with t[5]:
        admin_anticipos()
    with t[6]:
        admin_negocio()


# ══════════════════════════════════════════════════════════════
# APP PRINCIPAL
# ══════════════════════════════════════════════════════════════
def main():
    init_db()
    leer_config()
    st.set_page_config(page_title=f"{CFG['nombre']} · Citas", page_icon="💅", layout="wide")
    expirar_pendientes()
    init_state()

    clave = CFG["tema"] if CFG["tema"] in TEMAS else tema_para(ahora().date())
    tema = TEMAS[clave]
    st.markdown(css_total(tema), unsafe_allow_html=True)

    aviso = st.session_state.pop("_aviso", None)
    if aviso:
        st.toast(aviso[0], icon=aviso[1])

    hero(tema)
    tab_reservar, tab_galeria, tab_contacto, tab_admin = st.tabs(
        ["💅 Reservar cita", "🖼️ Galería", "📍 Contacto", "🔐 Administración"])
    with tab_reservar:
        vista_reservar()
    with tab_galeria:
        vista_galeria()
    with tab_contacto:
        vista_contacto()
    with tab_admin:
        vista_admin()
    render(f'<div class="footer">Hecho con 💖 para {esc(CFG["nombre"])}</div>')


main()
