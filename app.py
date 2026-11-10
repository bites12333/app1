"""농사 날씨 길잡이 — streamlit run app.py
GitHub에 app.py / requirements.txt 업로드 후 Streamlit Community Cloud로 배포.
인터넷 필요. API 키 불필요. Open-Meteo 무료 비상업 API의 이용 한도/약관 적용.
장기 계절예보 모델이 아닌 최근 5개 완결 연도 기후 기반 시나리오 앱.
추가 채소의 기간은 파종/정식/첫 수확을 단순화한 40~120일 비교 구간이며 실제 전 생육 기간이 아닙니다.
작물 조건은 교육용 단순화 가정이며 지역별 재배 지침이나 수확량 예측이 아님.
"""
from __future__ import annotations

import calendar
import html
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="농사 날씨 길잡이", page_icon="🌱", layout="wide")
# 도 단위 선택이며 좌표는 각 도 안의 대표 지점입니다(도 전체 평균 아님).
CITIES = {
    "경기도": (37.26, 127.03),
    "강원도": (37.88, 127.73),
    "충청북도": (36.64, 127.49),
    "충청남도": (36.66, 126.67),
    "전라북도": (35.82, 127.15),
    "전라남도": (34.81, 126.46),
    "경상북도": (36.57, 128.73),
    "경상남도": (35.23, 128.68),
    "제주도": (33.50, 126.53),
    "독도": (37.24, 131.87),
}

# 도별 주요 시·군의 도심 대표 좌표. 실제 밭 위치나 시군 전체 평균이 아님.
LOCALITIES = {
 '경기도': {'수원시':(37.264,127.029),'용인시':(37.241,127.178),'이천시':(37.272,127.435),'파주시':(37.760,126.780),'양평군':(37.491,127.488),'평택시':(36.992,127.113)},
 '강원도': {'춘천시':(37.881,127.730),'강릉시':(37.752,128.876),'원주시':(37.342,127.920),'홍천군':(37.697,127.889),'평창군':(37.370,128.390),'철원군':(38.146,127.313)},
 '충청북도': {'청주시':(36.642,127.489),'충주시':(36.991,127.926),'제천시':(37.132,128.192),'괴산군':(36.815,127.787),'옥천군':(36.306,127.571)},
 '충청남도': {'천안시':(36.815,127.114),'공주시':(36.446,127.120),'논산시':(36.187,127.098),'서산시':(36.784,126.450),'홍성군':(36.601,126.661),'예산군':(36.680,126.845)},
 '전라북도': {'전주시':(35.824,127.148),'익산시':(35.948,126.957),'정읍시':(35.570,126.856),'김제시':(35.803,126.880),'고창군':(35.435,126.702),'남원시':(35.416,127.390)},
 '전라남도': {'나주시':(35.015,126.711),'순천시':(34.950,127.487),'해남군':(34.573,126.599),'무안군':(34.991,126.482),'보성군':(34.771,127.080),'담양군':(35.321,126.988)},
 '경상북도': {'안동시':(36.568,128.729),'상주시':(36.411,128.159),'영주시':(36.805,128.624),'경주시':(35.856,129.225),'의성군':(36.353,128.698),'청도군':(35.648,128.734)},
 '경상남도': {'창원시':(35.228,128.681),'진주시':(35.180,128.108),'밀양시':(35.504,128.746),'김해시':(35.228,128.889),'거창군':(35.687,127.909),'남해군':(34.838,127.892)},
 '제주도': {'제주시':(33.500,126.531),'서귀포시':(33.254,126.560)},
 '독도': {'독도 (기후 참고용)':(37.242,131.868)},
}

# 이름, 비교 기간(일), 적정 평균기온 하한/상한, 저온 위험 기준, 고온 위험 기준,
# 주당 강수 비교범위 하한/상한(mm). 모두 교육용 가정이며 품종별 기준이 아님.
CROPS = [
    ("상추", 60, 15, 22, 3, 30, 15, 40),
    ("시금치", 60, 10, 20, -3, 27, 10, 35),
    ("무", 75, 15, 22, 0, 30, 15, 40),
    ("배추", 90, 15, 22, 0, 30, 20, 45),
    ("감자", 100, 15, 22, 0, 29, 15, 40),
    ("옥수수", 100, 20, 28, 8, 35, 20, 45),
    ("고구마", 120, 20, 28, 10, 35, 15, 40),
    ("콩", 110, 20, 28, 8, 35, 15, 40),
    ("고추", 120, 20, 28, 10, 35, 15, 40),
    ("토마토", 110, 18, 26, 8, 33, 15, 40),
    ("방울토마토", 100, 18, 26, 8, 33, 15, 40),
    ("오이", 75, 20, 28, 10, 35, 20, 45),
    ("가지", 110, 22, 28, 12, 35, 15, 40),
    ("애호박", 80, 18, 26, 8, 33, 20, 45),
    ("단호박", 110, 18, 26, 8, 33, 15, 40),
    ("당근", 100, 15, 22, 0, 30, 10, 35),
    ("열무", 40, 15, 23, 0, 30, 15, 40),
    ("청경채", 45, 15, 22, 0, 28, 15, 40),
    ("쑥갓", 50, 15, 22, 0, 28, 15, 35),
    ("깻잎", 70, 18, 26, 5, 33, 15, 40),
    ("부추", 80, 15, 24, 0, 30, 15, 40),
    ("대파", 100, 15, 24, -3, 30, 15, 40),
    ("쪽파", 60, 12, 22, -3, 28, 10, 35),
    ("브로콜리", 100, 15, 22, 0, 28, 15, 40),
    ("양배추", 110, 15, 22, 0, 30, 15, 40),
    ("케일", 70, 15, 23, -3, 30, 15, 40),
    ("비트", 80, 15, 23, 0, 30, 10, 35),
    ("완두콩", 90, 12, 20, -2, 27, 10, 35),
]
DAILY = "temperature_2m_mean,temperature_2m_min,temperature_2m_max,precipitation_sum"
COLS = DAILY.split(",")


def fetch_daily(url, params):
    response = requests.get(url, params=params, timeout=(10, 70))
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise ValueError(payload.get("reason", "날씨 제공 서비스 오류"))
    raw = payload.get("daily", {})
    if not raw.get("time") or any(c not in raw for c in COLS):
        raise ValueError("날씨 응답에 필요한 자료가 없습니다.")
    frame = pd.DataFrame({"date": pd.to_datetime(raw["time"]), **{c: raw[c] for c in COLS}})
    for col in COLS:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    return frame


@st.cache_data(ttl=86400, show_spinner=False)
def historical(lat, lon, year):
    frame = fetch_daily("https://archive-api.open-meteo.com/v1/archive", {
        "latitude": lat, "longitude": lon,
        "start_date": f"{year-5}-01-01", "end_date": f"{year-1}-12-31",
        "daily": DAILY, "timezone": "Asia/Seoul",
    })
    valid = frame.dropna(subset=COLS).copy()
    if len(valid) < len(frame) * .95 or len(valid) < 1700:
        raise ValueError("최근 5년 자료가 충분하지 않아 비교할 수 없습니다.")
    valid["monthday"] = valid["date"].dt.strftime("%m-%d")
    grouped = valid.groupby("monthday")[COLS]
    return grouped.mean(), grouped.count().min(axis=1)


@st.cache_data(ttl=3600, show_spinner=False)
def forecast(lat, lon, today_string):
    return fetch_daily("https://api.open-meteo.com/v1/forecast", {
        "latitude": lat, "longitude": lon, "daily": DAILY,
        "timezone": "Asia/Seoul", "forecast_days": 16,
    }).dropna(subset=COLS)


def build_outlook(normal, counts, short, start, days, adjustment):
    rows = []
    lookup = {r['date'].date(): r for _, r in short.iterrows()}
    for i in range(days):
        day = start + timedelta(days=i)
        key = day.strftime("%m-%d")
        if key == "02-29":
            baseline = (normal.loc["02-28"] + normal.loc["03-01"]) / 2
        else:
            if key not in normal.index or counts.loc[key] < 4:
                raise ValueError("해당 날짜의 과거 자료가 부족합니다.")
            baseline = normal.loc[key]
        if day in lookup:
            values = lookup[day]
            source = "단기 예보"
        else:
            values = baseline.copy()
            for col in COLS[:3]:
                values[col] += adjustment
            source = "과거 기후 기반 추정"
        rows.append({"날짜": day, **{c: float(values[c]) for c in COLS}, "자료": source})
    return pd.DataFrame(rows)


def facility_outlook(outlook, method, warming):
    frame = outlook.copy()
    if method != '노지':
        for col in COLS[:3]:
            frame[col] += warming
    return frame


def score_crop(crop, outlook):
    # Transparent educational screening, not calibrated agronomic probabilities.
    name, days, lo, hi, cold, hot, rain_lo, rain_hi = crop
    frame = outlook.iloc[:days]
    initial = frame.iloc[:14]
    growth = frame.iloc[14:]
    # Same per-crop temperature band is deliberately retained: no unsupported
    # germination/soil thresholds are invented. Initial establishment is a proxy.
    def stage_fit(part):
        t = part[COLS[0]]
        return float(((t >= lo) & (t <= hi)).mean())
    initial_fit, growth_fit = stage_fit(initial), stage_fit(growth)
    cold_fraction = float((frame[COLS[1]] < cold).mean())
    hot_fraction = float((frame[COLS[2]] > hot).mean())
    risk = max(cold_fraction, hot_fraction)
    fit = .4*initial_fit + .6*growth_fit
    # Grade gates make severe exposure impossible to hide behind an average.
    grade = '불리' if risk >= .3 or fit < .3 else '유리' if fit >= .7 and risk < .1 else '주의'
    rank = {'불리':0,'주의':1,'유리':2}[grade]*1000 + fit*100 - risk*50
    display_score = round(100 * fit * (1 - .5*risk), 1)
    return {'점수':display_score,'작물':name,'적합도':rank,'판정':grade,'초기':initial_fit,'생육':growth_fit,
            '위험':risk,'비교 기간':days,'평균기온':round(float(frame[COLS[0]].mean()),1),
            '주당 강수량':round(float(frame[COLS[3]].mean()*7),1),
            '예보 일수':int((frame['자료']=='단기 예보').sum()),
            '이유':['초기 14일과 이후 기간의 기온 적합일 비중 및 저온·고온 노출을 비교합니다.']}



def management(crop, outlook):
    name, days, lo, hi, cold, hot, rain_lo, rain_hi = crop
    period = outlook.iloc[:days]
    tips = []
    if (period[COLS[1]] < cold).any():
        tips.append("보온 준비: 저온 주의 조건이 있습니다. 심기 직전 예보를 확인하고 보온 덮개나 심는 시기 조정을 검토하세요.")
    if (period[COLS[2]] > hot).any():
        tips.append("더위 대비: 고온 주의 조건이 있습니다. 토양 수분을 살피고 작물에 맞는 차광·환기 방법을 확인하세요.")
    weekly = float(period[COLS[3]].mean() * 7)
    if weekly < rain_lo:
        tips.append("물주기 준비: 비가 적은 조건입니다. 물 공급 방법을 준비하되, 실제 물주기는 흙의 수분과 가까운 예보를 보고 결정하세요.")
    elif weekly > rain_hi:
        tips.append("배수 준비: 비가 많은 조건입니다. 물길과 배수로를 점검하고 밭에 물이 고이지 않도록 준비하세요.")
    else:
        tips.append("수분 점검: 평균 강수는 비교 범위 안이지만, 비가 고르게 오지는 않습니다. 밭의 마름과 물 고임을 직접 확인하세요.")
    basics = {
        "상추": "잎과 흙의 상태를 자주 보고, 잎을 수확할 때 생장점이 상하지 않도록 관리하세요.",
        "시금치": "씨앗이 마르지 않도록 발아기 수분을 살피고, 밀식하면 솎아 주는 계획을 세우세요.",
        "무": "뿌리가 자랄 공간을 확보하고, 너무 빽빽한 포기는 적절히 솎아 주세요.",
        "배추": "잎 뒷면의 해충과 생장 상태를 자주 살피고, 결구기에 수분이 크게 들쭉날쭉하지 않도록 점검하세요.",
        "감자": "건전한 씨감자를 준비하고, 자라는 감자가 햇빛에 노출되지 않도록 흙덮기 상태를 점검하세요.",
        "옥수수": "쓰러짐에 대비해 뿌리 주변 흙과 지지 상태를 살피고, 꽃이 피는 무렵 수분 상태를 점검하세요.",
        "고구마": "건전한 묘를 준비하고, 심은 직후 뿌리가 자리 잡는 동안 토양 수분을 살피세요.",
        "콩": "물 고임과 쓰러짐을 점검하고, 꽃과 꼬투리가 생기는 동안 수분 상태를 자주 살피세요.",
    }
    basics.update({
        "고추": "지지대를 준비하고 가지가 쓰러지지 않도록 묶음 상태와 배수 상태를 살피세요.",
        "토마토": "지지대를 세우고 줄기를 유인하세요. 곁순 관리는 품종과 재배 방식에 맞춰 확인하세요.",
        "방울토마토": "지지대와 줄기 유인을 준비하고 과실이 갈라지지 않도록 토양 수분의 급격한 변화를 살피세요.",
        "오이": "덩굴이 자랄 지지망을 준비하고 통풍과 토양 수분을 살피세요.",
        "가지": "가지와 열매를 지탱할 지지대를 준비하고 잎 뒷면의 해충을 점검하세요.",
        "애호박": "잎이 겹치지 않을 공간을 확보하고 착과가 잘되는지 관찰하세요.",
        "단호박": "덩굴이 뻗을 공간을 확보하고 열매가 물 고인 땅에 닿지 않도록 살피세요.",
        "당근": "흙 속 돌과 굳은 층을 정리하고 발아 후 빽빽한 포기는 적절히 솎아 주세요.",
        "열무": "발아기 수분과 밀식을 살피고 어린 잎의 해충 피해를 점검하세요.",
        "청경채": "밀식과 물 고임을 피하고 잎 뒷면의 해충과 꽃대 발생을 살피세요.",
        "쑥갓": "발아 후 밀식 상태를 살피고 연한 잎과 줄기를 품종에 맞춰 수확하세요.",
        "깻잎": "잎이 겹쳐 통풍이 나빠지지 않도록 간격과 잎 뒷면을 점검하세요.",
        "부추": "수확 후 새잎의 생육과 토양 수분을 살피고 포기 주변 잡초를 관리하세요.",
        "대파": "흙덮기 방법은 재배 방식에 맞춰 확인하고 생장점에 흙이 들어가지 않도록 주의하세요.",
        "쪽파": "건전한 종구를 준비하고 물 고임과 잎의 병반을 점검하세요.",
        "브로콜리": "꽃봉오리 발달과 해충을 살피고 수확 시기를 놓치지 않도록 관찰하세요.",
        "양배추": "결구 상태와 잎 뒷면의 해충을 살피고 수분의 급격한 변화를 점검하세요.",
        "케일": "잎 뒷면의 해충을 자주 살피고 새잎이 자랄 수 있도록 수확 방법을 확인하세요.",
        "비트": "뿌리가 자랄 간격을 확보하고 발아 후 빽빽한 포기는 솎아 주세요.",
        "완두콩": "덩굴성 품종은 지지망을 준비하고 꽃과 꼬투리의 생육을 살피세요.",
    })
    tips.append("작물 관리: " + basics.get(name, "생육 상태와 잎 뒷면의 병해충을 살피고, 품종별 심는 간격·지지대·수확 시기를 확인하세요."))
    tips.append("관리 안내는 교육용 준비 사항입니다. 품종·토양·생육 단계에 맞는 방법은 지역 농업기술센터에 확인하세요.")
    return tips


@st.cache_data(ttl=604800, show_spinner=False)
def korean_font_bytes():
    response = requests.get('https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf', timeout=20)
    response.raise_for_status()
    return response.content


def result_image(lines):
    # Fonts are bundled inside Pillow's host system, not fetched from the internet.
    candidates = [Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf'),
                  Path('/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf'),
                  Path('C:/Windows/Fonts/malgun.ttf'),
                  Path('/System/Library/Fonts/AppleSDGothicNeo.ttc')]
    candidates += list(Path('/usr/share/fonts').rglob('*NanumGothic*.ttf')) if Path('/usr/share/fonts').exists() else []
    font_path = next((f for f in candidates if f.exists()), None)
    if font_path is None:
        try:
            font_data = korean_font_bytes()
            font = ImageFont.truetype(io.BytesIO(font_data), 29)
        except (requests.RequestException, OSError, ValueError) as exc:
            raise ValueError('이미지용 한글 글꼴을 불러오지 못했습니다. 아래 글로 저장하기를 이용해 주세요.') from exc
    else:
        font = ImageFont.truetype(str(font_path), 29)
    probe = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    wrapped = []
    for line in lines:
        current = ''
        for char in line:
            if probe.textlength(current + char, font=font) > 1000:
                wrapped.append(current); current = char
            else:
                current += char
        wrapped.append(current)
    image = Image.new('RGB', (1120, 100 + len(wrapped)*47), '#f5f4e9')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((30, 25, 1090, image.height-25), radius=20, fill='#fffef7', outline='#c7ccb8', width=2)
    for i, line in enumerate(wrapped):
        draw.text((60, 50+i*47), line, font=font, fill='#20251d')
    buffer = io.BytesIO(); image.save(buffer, format='PNG')
    return buffer.getvalue()


theme = st.radio("화면 테마", ["밝게 ☀️", "어둡게 🌙"], horizontal=True, key="display_theme")
dark = theme == "어둡게 🌙"
colors = {
    "red": "#ff9e9e" if dark else "#b42318",
    "bg": "#151b18" if dark else "#f5f4e9",
    "surface": "#222d26" if dark else "#ffffff",
    "text": "#f2f6ed" if dark else "#172315",
    "muted": "#c4d0bf" if dark else "#46513d",
    "border": "#71836d" if dark else "#87977b",
    "tint": "#304235" if dark else "#e8efdf",
}
st.markdown("""<style>
.stApp, [data-testid="stAppViewContainer"], [data-testid="stHeader"] {background:var(--farm-bg)!important;color:var(--farm-text)!important;}
.block-container {max-width:1440px;padding:2rem 4vw 3rem;}
html,body,input,button {font-family:system-ui,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;}
h1,h2,h3,h4,p,li,label,summary, [data-testid="stMarkdownContainer"], [data-testid="stMarkdownContainer"] * {
 color:var(--farm-text)!important;-webkit-text-fill-color:var(--farm-text)!important;
}
p,li,[data-testid="stMarkdownContainer"] p {font-size:21px!important;line-height:1.6!important;}
h2,h3 {font-size:27px!important;}
.hero {padding:24px 0;border-top:2px solid var(--farm-border);border-bottom:1px solid var(--farm-border);margin:20px 0 26px;}
.hero .eyebrow {font-size:18px;font-weight:700;color:var(--farm-muted)!important;}
.hero h1 {font-size:clamp(36px,5vw,68px)!important;line-height:1.15;letter-spacing:-.05em;font-weight:900;}
.hero p {max-width:900px;}
[data-testid="stForm"], [data-testid="stExpander"] {background:var(--farm-surface)!important;border:1px solid var(--farm-border)!important;border-radius:18px;padding:18px;}
[data-testid="stWidgetLabel"] p {font-size:21px!important;font-weight:700;}
[data-baseweb="select"], [data-baseweb="select"] *,
[data-baseweb="input"], [data-baseweb="input"] *,
[data-baseweb="base-input"], [data-baseweb="base-input"] *,
[data-testid="stDateInput"] > div, [data-testid="stDateInput"] > div > div,
[data-testid="stDateInput"] [data-baseweb], [data-testid="stDateInput"] [data-baseweb] *,
[data-testid="stDateInput"] button, [data-testid="stDateInput"] button *,
input:not([type="radio"]):not([type="checkbox"]), [role="combobox"] {
 background:var(--farm-surface)!important;color:var(--farm-text)!important;
 -webkit-text-fill-color:var(--farm-text)!important;caret-color:var(--farm-text)!important;
}
[data-baseweb="select"] > div, [data-baseweb="input"] {min-height:54px;border-color:var(--farm-border)!important;}
[data-baseweb="select"] svg,[data-testid="stDateInput"] svg {fill:currentColor!important;color:var(--farm-text)!important;}
[data-baseweb="popover"], [data-baseweb="popover"] *,
[data-baseweb="calendar"], [data-baseweb="calendar"] * {
 background-color:var(--farm-surface)!important;color:var(--farm-text)!important;-webkit-text-fill-color:var(--farm-text)!important;
}
[data-baseweb="popover"] [aria-disabled="true"] {opacity:.4;}
[data-baseweb="popover"] [aria-selected="true"], [data-baseweb="popover"] [role="option"]:hover {
 background:var(--farm-tint)!important;outline:2px solid var(--farm-border);outline-offset:-2px;
}
.stButton button, [data-testid="stFormSubmitButton"] button, [data-testid="stDownloadButton"] button {
 background:var(--farm-surface)!important;color:var(--farm-text)!important;border:2px solid var(--farm-border)!important;
 min-height:58px;border-radius:12px;font-size:21px!important;
}
.stButton button *, [data-testid="stFormSubmitButton"] button *, [data-testid="stDownloadButton"] button * {
 color:var(--farm-text)!important;-webkit-text-fill-color:var(--farm-text)!important;
}
[data-testid="stAlert"], [data-testid="stAlert"] > div {background:var(--farm-tint)!important;border-radius:12px;color:var(--farm-text)!important;}
[data-testid="stMetricValue"] {font-size:42px!important;font-weight:800;color:var(--farm-text)!important;}
[data-testid="stMetricLabel"] p {font-size:21px!important;}
[data-testid="stCaptionContainer"] p {font-size:17px!important;color:var(--farm-muted)!important;-webkit-text-fill-color:var(--farm-muted)!important;}
[data-testid="stTable"], [data-testid="stTable"] * {background:var(--farm-surface)!important;color:var(--farm-text)!important;-webkit-text-fill-color:var(--farm-text)!important;border-color:var(--farm-border)!important;}
[data-testid="stTable"] th {background:var(--farm-tint)!important;}
[data-testid="stTable"] {overflow-x:auto;}
[data-testid="stVerticalBlockBorderWrapper"]>div {border-color:var(--farm-border)!important;border-radius:16px;}
@media(max-width:768px) {
.block-container {padding:1rem 1rem 2rem;}
.hero h1 {font-size:40px!important;}
[data-testid="stHorizontalBlock"] {flex-direction:column!important;gap:16px;}
[data-testid="stHorizontalBlock"]>[data-testid="stColumn"] {width:100%!important;flex:1 1 100%!important;min-width:0!important;}
}
.red-advice {color:var(--farm-red)!important;-webkit-text-fill-color:var(--farm-red)!important;font-size:23px!important;font-weight:800;line-height:1.6;margin:8px 0;}
</style>""", unsafe_allow_html=True)
# Define shared variables on root so portaled calendars/dropdown menus inherit them too.
st.markdown("<style>:root{" + ''.join(f"--farm-{key}:{value};" for key,value in colors.items()) + f"color-scheme:{'dark' if dark else 'light'};" + "}</style>", unsafe_allow_html=True)
st.markdown("""<section class="hero"><div class="eyebrow">농사 날씨 길잡이 · 나의 밭, 나의 계절</div>
<h1>무엇을 심을까요?<br>날씨에서 답을 찾아요.</h1>
<p>지역과 심을 날짜를 골라 주세요. 앞으로 자라는 동안의 기온과 비를 살펴, 잘 맞는 작물과 주의할 작물을 알려드려요.</p></section>""", unsafe_allow_html=True)
st.caption("화면 버전: 점수와 개선 안내 9 · 작물 28종")
today = datetime.now(timezone(timedelta(hours=9))).date()
province = st.selectbox("① 도 선택", list(LOCALITIES), key="province_choice")
with st.form("settings"):
    st.subheader("우리 밭에 맞게 골라 주세요")
    region_col, date_col, climate_col = st.columns([1, 1, 1.15])
    with region_col:
        locality = st.selectbox("가까운 시·군", list(LOCALITIES[province]), key="locality_" + province)
        city = province + " · " + locality
        st.caption("주요 시·군 대표 지점입니다. 실제 밭 위치와는 다를 수 있어요.")
    with date_col:
        selected_date = st.date_input("② 심을 날짜", value=today, min_value=today,
                                      max_value=today+timedelta(days=365), format="YYYY/MM/DD")
        st.caption("날짜 칸을 누르면 달력이 열려요. 선택한 날부터 비교합니다.")
    with climate_col:
        scenario = st.radio("③ 앞으로의 기온 가정", ["최근 5년과 비슷", "조금 더 따뜻함 (+2℃)", "조금 더 서늘함 (-2℃)"], horizontal=False)
    crop_choice = st.selectbox("④ 관심 작물 (선택사항)", ["작물 추천받기"] + [c[0] for c in CROPS])
    st.caption("잘 모르겠다면 추천받기를 그대로 두세요. 작물을 고르면 해당 작물의 관리 방법을 안내해 드려요.")
    method = st.selectbox("⑤ 재배 방식", ["노지", "보온 덮개", "비닐하우스"])
    warming = st.number_input("시설 내부 기온 상승 가정 (℃)", min_value=0.0, max_value=15.0, value=0.0, step=0.5)
    st.caption("노지는 0℃로 계산합니다. 시설은 실제 측정값에 맞춰 입력하세요. 일정한 보온 효과를 보장하지 않습니다.")
    run = st.form_submit_button("우리 밭에 맞는 작물 알아보기 →", type="primary", use_container_width=True)
st.caption("가까운 날은 단기 예보, 먼 날은 최근 5년 기후를 활용합니다. 몇 달 뒤 실제 날씨를 정확히 예측하는 서비스는 아닙니다.")

if run:
    st.session_state.pop("analysis", None)
    start = selected_date
    adjustment = {"최근 5년과 비슷": 0, "조금 더 따뜻함 (+2℃)": 2, "조금 더 서늘함 (-2℃)": -2}[scenario]
    lat, lon = LOCALITIES[province][locality]
    try:
        with st.spinner("기온과 비 자료를 확인하고 있습니다. 처음에는 잠시 걸릴 수 있어요."):
            normal, counts = historical(lat, lon, today.year)
            short = pd.DataFrame(columns=["date", *COLS])
            note = ""
            if start <= today+timedelta(days=15):
                try:
                    short = forecast(lat, lon, today.isoformat())
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    note = "단기 예보를 가져오지 못해 전 기간을 과거 기후 기반으로 비교했습니다."
            outlook = build_outlook(normal, counts, short, start, 120, adjustment)
            outlook = facility_outlook(outlook, method, warming)
            results = sorted([score_crop(c, outlook) for c in CROPS], key=lambda r: (r['점수'],r['적합도']), reverse=True)
            target_name = results[0]['작물'] if crop_choice == '작물 추천받기' else crop_choice
            target_crop = next(c for c in CROPS if c[0] == target_name)
            date_options = []
            for offset in (0, 14, 30):
                candidate_date = start + timedelta(days=offset)
                candidate_outlook = build_outlook(normal, counts, short, candidate_date, 120, adjustment)
                candidate_outlook = facility_outlook(candidate_outlook, method, warming)
                candidate_score = score_crop(target_crop, candidate_outlook)
                date_options.append({'심을 날짜': candidate_date, '점수': candidate_score['점수'], '순위': candidate_score['적합도'], '판정': candidate_score['판정']})
            st.session_state['analysis'] = (city, start, scenario, results, outlook, note, today.year, crop_choice, date_options, method, warming)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        st.error("날씨 자료를 불러오지 못했습니다. 인터넷 연결을 확인한 뒤 다시 눌러 주세요. 임의의 날씨로 대체하지 않습니다.")
        with st.expander("오류 내용 보기"):
            st.code(str(exc))

if 'analysis' in st.session_state and (len(st.session_state['analysis']) != 11 or '점수' not in st.session_state['analysis'][3][0]):
    st.session_state.pop('analysis', None)

if 'analysis' in st.session_state:
    city, start, scenario, results, outlook, note, year, saved_choice, date_options, saved_method, saved_warming = st.session_state['analysis']
    target = results[0] if saved_choice == '작물 추천받기' else next(r for r in results if r['작물'] == saved_choice)
    target_crop = next(c for c in CROPS if c[0] == target['작물'])
    st.divider()
    st.subheader(f"{city} · {start:%Y년 %m월 %d일} 심기")
    best_date_summary = max(date_options, key=lambda r:r['점수'])
    if best_date_summary['점수'] > date_options[0]['점수']:
        st.success(f"지금 할 일 · {target['작물']}은 {best_date_summary['심을 날짜']:%m월 %d일} 심기를 먼저 검토하세요.")
    elif target['판정'] == '불리':
        st.warning("지금 할 일 · 심기보다 다른 시기를 먼저 확인하세요.")
    elif saved_choice == '작물 추천받기':
        st.success(f"지금 할 일 · {target['작물']} 재배를 먼저 검토하세요.")
    else:
        st.info(f"지금 할 일 · {target['작물']}의 아래 관리 핵심을 확인하세요.")
    st.subheader("추천 상위 3개" if saved_choice == '작물 추천받기' else "선택한 작물")
    cards = [(f"{i+1}위", item) for i,item in enumerate(results[:3])] if saved_choice == '작물 추천받기' else [("선택한 작물", target)]
    for col, (heading, item) in zip(st.columns(len(cards)), cards):
        with col, st.container(border=True):
            st.subheader(f"{heading} · {item['작물']}")
            st.metric("기후 비교 점수", f"{item['점수']:.1f} / 100점")
            st.write(f"**판정 · {item['판정']}**")
            st.write(f"초기 2주 적합일 {item['초기']:.0%} · 이후 {item['생육']:.0%}")
            st.write(f"평균 {item['평균기온']}℃ · 비교 {item['비교 기간']}일")
    st.caption(f"{saved_method} · 기온 상승 가정 {0 if saved_method == '노지' else saved_warming}℃")
    if saved_choice == '작물 추천받기' and not any(r['판정']=='유리' for r in results):
        st.warning("뚜렷하게 유리한 작물이 없어요. 심는 시기 조정을 먼저 검토하세요.")
    elif target['판정'] == '불리':
        st.warning("선택한 조건에서는 불리해요. 시기나 재배 방식을 검토하세요.")
    cold = bool((outlook.iloc[:target_crop[1]][COLS[1]] < target_crop[4]).any())
    hot = bool((outlook.iloc[:target_crop[1]][COLS[2]] > target_crop[5]).any())
    rain = float(outlook.iloc[:target_crop[1]][COLS[3]].mean()*7)
    short_tips = []
    if cold: short_tips.append("추위 주의 · 심는 시기 조정 / 보온 준비")
    if hot: short_tips.append("더위 주의 · 차광 / 수분 점검")
    short_tips.append("비 부족 · 물 공급 준비" if rain < target_crop[6] else "비 많음 · 배수로 점검" if rain > target_crop[7] else "흙의 수분 · 직접 확인")
    if saved_method == '비닐하우스':
        short_tips = [t for t in short_tips if not t.startswith(('비 부족', '비 많음', '흙의 수분'))]
        short_tips += ["하우스 내부 · 환기와 토양 수분 직접 점검"]
    elif saved_method == '보온 덮개':
        short_tips += ["덮개 안 실제 온도·수분 확인"]
    st.subheader("무엇이 문제인가요?")
    mean = float(outlook.iloc[:target_crop[1]][COLS[0]].mean())
    issues = []
    if target['초기'] < .7: issues.append(f"초기 2주 적합일이 {target['초기']:.0%}로 적어요.")
    if target['생육'] < .7: issues.append(f"이후 생육 적합일이 {target['생육']:.0%}로 적어요.")
    if cold: issues.append("저온 주의 기준보다 낮은 날이 있어요.")
    if hot: issues.append("고온 주의 기준보다 높은 날이 있어요.")
    if not issues: issues.append("현재 기온 가정에서는 큰 감점 요인이 없어요.")
    actions = []
    if cold or mean < target_crop[2]: actions.append("더 따뜻한 심는 시기를 비교하세요. 시설은 실제 내부 온도를 측정해 입력하세요.")
    if hot or mean > target_crop[3]: actions.append("더 서늘한 심는 시기를 비교하세요. 차광·환기는 실제 온도를 확인하며 적용하세요.")
    alternatives = [r for r in date_options if r['점수'] > date_options[0]['점수']]
    if alternatives:
        better = max(alternatives, key=lambda r:r['점수'])
        actions.append(f"같은 작물을 {better['심을 날짜']:%m월 %d일}에 심는 가정은 {better['점수']:.1f}점으로 {better['점수']-date_options[0]['점수']:.1f}점 높아요.")
    else: actions.append("비교한 세 날짜에는 더 높은 점수가 없어요. 다른 달도 비교해 보세요.")
    for message in issues:
        st.markdown('<div class="red-advice">문제 · '+html.escape(message)+'</div>', unsafe_allow_html=True)
    st.subheader("점수를 높이려면?")
    for message in actions:
        st.markdown('<div class="red-advice">대안 · '+html.escape(message)+'</div>', unsafe_allow_html=True)
    st.caption("점수는 기온 적합일과 온도 위험만 반영합니다. 물주기·비료·배수는 중요하지만 이 점수를 직접 올리지는 않습니다. 입력값만 바꾸는 것은 실제 개선이 아닙니다.")
    st.subheader("관리 핵심")
    for tip in short_tips[:3]:
        st.write("**• " + tip + "**")
    st.subheader("심는 날짜 비교")
    for col, r in zip(st.columns(3), date_options):
        with col:
            st.metric(f"{r['심을 날짜']:%m월 %d일}", f"{r['점수']:.1f}점")
            st.write(r["판정"])
    best_date = max(date_options, key=lambda x:x['점수'])
    gain = best_date['점수'] - date_options[0]['점수']
    st.subheader("바꾸면 얼마나 좋아질까요?")
    before, after = st.columns(2)
    with before:
        st.metric(f"선택한 날 · {start:%m월 %d일}", f"{date_options[0]['점수']:.1f}점")
    with after:
        st.metric(f"비교한 날 중 최고 · {best_date['심을 날짜']:%m월 %d일}", f"{best_date['점수']:.1f}점", delta=f"+{gain:.1f}점" if gain > 0 else "변화 없음")
    if gain > 0:
        message = f"{target['작물']} · {best_date['심을 날짜']:%m월 %d일}에 심는 가정은 {gain:.1f}점 높아요."
        st.markdown('<div class="red-advice">'+html.escape(message)+'</div>', unsafe_allow_html=True)
    else:
        st.info("비교한 세 날짜에 더 높은 점수는 없어요. 다른 달도 확인해 보세요.")
    st.caption("같은 작물·같은 시설 가정에서 날짜만 비교한 교육용 점수입니다.")
    lines = ['농사 날씨 길잡이',f'{city} · {start:%Y-%m-%d}',f"{target['작물']} · {target['점수']:.1f}점 · {target['판정']} / {saved_method}", '관리 핵심',*short_tips,'심는 날짜 비교']
    lines += [f"{r['심을 날짜']:%Y-%m-%d} · {r['점수']:.1f}점 · {r['판정']}" for r in date_options]
    lines += [f'날짜 변경 비교: {date_options[0]["점수"]:.1f}점 → {best_date["점수"]:.1f}점 (+{gain:.1f}점)', '문제', *issues, '개선 방향', *actions]
    lines += ['과거 기후 기반 교육용 비교 · 실제 장기 날씨 예측 아님',f'과거 자료 {year-5}~{year-1} · Open-Meteo']
    st.subheader("결과 저장")
    try:
        st.download_button("이미지 저장", result_image(lines), file_name=f"농사결과_{start}.png", mime="image/png", use_container_width=True)
    except (ValueError,OSError) as exc:
        st.warning("이미지 저장을 준비하지 못했어요. 글로 저장을 이용하세요.")
    st.download_button("글로 저장", '\n'.join(lines).encode('utf-8-sig'), file_name=f"농사결과_{start}.txt", mime="text/plain", use_container_width=True)
    with st.expander("전체 28종 보기 · 관리 / 자료"):
        st.table(pd.DataFrame([{'작물':r['작물'],'점수':r['점수'],'판정':r['판정']} for r in results]))
        for tip in management(target_crop,outlook):
            if saved_method != '비닐하우스' or not tip.startswith(('물주기 준비:', '배수 준비:', '수분 점검:')): st.write('• '+tip)
        st.write(f"단기 예보 {target['예보 일수']}일 · 나머지는 과거 기후 기반 추정")
        if note: st.write(note)
        if city.startswith('독도'): st.warning('독도는 해상 기후 참고용입니다. 실제 재배 판단에 사용하지 마세요.')
    st.caption("교육용 기후 비교입니다. 실제 재배 전 지역 농업기술센터에 확인하세요.")

with st.expander("판정 기준과 한계"):
    st.write("검증된 농업 진단이 아닌 교육용 선별 기준입니다. 초기 14일(활착 참고)과 이후 기간을 나누되, 둘 다 같은 작물별 적정 평균기온 범위를 사용합니다. 발아·토양온도·정식 기준을 따로 검증한 모델이 아닙니다.")
    st.write("비교 점수 = 100 × (초기 적합일 비중 × 0.4 + 이후 적합일 비중 × 0.6) × (1 − 저온·고온 중 큰 노출 비중 × 0.5). 실제 성공 확률이 아닙니다. 등급은 심한 위험을 우선 확인하므로 점수 순서와 등급 순서는 다를 수 있습니다.")
    st.write("적합일 비중 = 초기 40% + 이후 60%. 유리: 적합일 비중 70% 이상이고 저온·고온 노출 각각 10% 미만. 불리: 적합일 비중 30% 미만이거나 저온 또는 고온 노출 30% 이상. 나머지는 주의입니다. 이 수치는 교육용 가정입니다. 같은 등급에서도 적합일과 위험 노출로 상대 비교합니다.")
    st.write("비는 관수·배수 준비에만 사용하며 판정에서 제외합니다. 하우스 안에 실외 강수를 적용하지 않습니다. 시설은 입력한 기온 차이를 모든 날짜의 기온에 더하는 시나리오일 뿐 실제 보온·환기 효과 예측이 아닙니다. 광량·습도·토양·품종·병해충은 미반영입니다.")
    st.write("장기 자료는 최근 5년 같은 날짜의 평균입니다. 실제 한파·폭염·연속 강우 위험은 과소평가할 수 있습니다. 날짜 비교는 같은 작물의 세 날짜에 한정합니다. 작물 기간은 단순화된 비교 구간이며 수확일 예측이 아닙니다.")
    st.table(pd.DataFrame([{'작물':c[0],'비교일':c[1],'적정 평균기온':f'{c[2]}~{c[3]}℃','저온 주의':c[4],'고온 주의':c[5]} for c in CROPS]))
st.caption("날씨 자료: Open-Meteo · 기온/강수 재분석 자료와 단기 예보 사용 · 인터넷 연결 필요")
st.markdown("[날씨 자료 및 이용 조건](https://open-meteo.com/) · [과거 날씨 자료 설명](https://open-meteo.com/en/docs/historical-weather-api) · [농사로 재배 정보](https://www.nongsaro.go.kr/)")

st.caption("화면 버전 · 지역 세분화와 상위 3개 · 10")
