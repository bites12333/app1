"""농사 날씨 길잡이 — streamlit run app.py
GitHub에 app.py / requirements.txt 업로드 후 Streamlit Community Cloud로 배포.
인터넷 필요. API 키 불필요. Open-Meteo 무료 비상업 API의 이용 한도/약관 적용.
장기 계절예보 모델이 아닌 최근 5개 완결 연도 기후 기반 시나리오 앱.
추가 채소의 기간은 파종/정식/첫 수확을 단순화한 40~120일 비교 구간이며 실제 전 생육 기간이 아닙니다.
작물 조건은 교육용 단순화 가정이며 지역별 재배 지침이나 수확량 예측이 아님.
"""
from __future__ import annotations

import calendar
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


def score_crop(crop, outlook):
    name, days, lo, hi, cold, hot, rain_lo, rain_hi = crop
    frame = outlook.iloc[:days]
    t = frame[COLS[0]]
    # 점수는 확률/수확량이 아니라 명시적인 교육용 비교 지수입니다.
    deviation = (lo-t).clip(lower=0) + (t-hi).clip(lower=0)
    temp_fit = float((100-deviation*7).clip(lower=0).mean())
    cold_fraction = float((frame[COLS[1]] < cold).mean())
    hot_fraction = float((frame[COLS[2]] > hot).mean())
    weekly_rain = float(frame[COLS[3]].mean()*7)
    rain_gap = max(rain_lo-weekly_rain, 0, weekly_rain-rain_hi)
    rain_fit = max(0, 100-rain_gap*2)
    score = max(0, min(100, .8*temp_fit + .2*rain_fit - 25*cold_fraction - 20*hot_fraction))
    reasons = []
    if temp_fit >= 80:
        reasons.append("평균기온이 설정한 생육 조건에 비교적 잘 맞습니다")
    else:
        reasons.append("평균기온이 설정한 생육 조건에서 벗어나는 기간이 있습니다")
    if cold_fraction >= .1:
        reasons.append("저온 주의 기준보다 낮은 날이 많아 보온 관리가 필요합니다")
    if hot_fraction >= .1:
        reasons.append("고온 주의 기준보다 높은 날이 많아 더위 관리가 필요합니다")
    if weekly_rain < rain_lo:
        reasons.append("비가 적을 수 있어 물주기 계획이 필요합니다")
    elif weekly_rain > rain_hi:
        reasons.append("비가 많을 수 있어 배수 관리가 필요합니다")
    else:
        reasons.append("주당 강수량 평균이 설정한 비교 범위 안에 있습니다")
    return {"작물": name, "적합도": round(score, 1), "비교 기간": days,
            "평균기온": round(float(t.mean()), 1), "주당 강수량": round(weekly_rain, 1),
            "예보 일수": int((frame['자료'] == '단기 예보').sum()), "이유": reasons}


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


st.markdown("""<style>
:root {color-scheme:light;}
.stApp, [data-testid="stAppViewContainer"] {background:#f5f4e9;color:#20251d;}
[data-testid="stHeader"] {background:#f5f4e9;}
.block-container {max-width:1440px;padding:2.5rem 4vw 3rem;}
html, body, p, label, input {font-family:system-ui,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;}
p, li {font-size:18px;line-height:1.7;color:#30392c;}
h1,h2,h3,label,[data-testid="stWidgetLabel"] p {color:#20251d!important;}
.hero {padding:24px 0 30px;border-top:2px solid #20251d;border-bottom:1px solid #a7ad98;margin-bottom:28px;}
.hero .eyebrow {font-size:17px;font-weight:700;color:#47633c;letter-spacing:.12em;}
.hero h1 {font-size:clamp(36px,5.7vw,78px)!important;line-height:1.12;letter-spacing:-.055em;font-weight:900;margin:14px 0;}
.hero p {margin:0;max-width:760px;font-size:20px;}
[data-testid="stForm"] {background:#fffef7;border:1px solid #c7ccb8;border-radius:20px;padding:24px;}
[data-testid="stWidgetLabel"] p {font-size:20px!important;font-weight:700;}
[data-baseweb="select"]>div, [data-baseweb="input"] {background:#fffef7!important;color:#20251d!important;border-color:#8b967d!important;min-height:52px;}
input {color:#20251d!important;-webkit-text-fill-color:#20251d!important;font-size:18px!important;}
[data-baseweb="select"] span {color:#20251d!important;}
[data-baseweb="popover"] {color-scheme:light;}
[data-baseweb="popover"] [role="listbox"], [data-baseweb="popover"] [role="option"] {background:#fffef7!important;color:#20251d!important;}
[data-testid="stCaptionContainer"] p {font-size:15px!important;color:#57614e!important;}
[data-testid="stRadio"] label p {font-size:18px!important;}
.stButton button, [data-testid="stFormSubmitButton"] button {background:#365a32!important;color:#ffffff!important;border:0!important;min-height:58px;border-radius:12px;font-size:20px!important;font-weight:700;}
/* White input surfaces with black text, including nested BaseWeb elements. */
[data-testid="stSelectbox"] [data-baseweb="select"],
[data-testid="stSelectbox"] [data-baseweb="select"] div,
[data-testid="stDateInput"] [data-baseweb="input"],
[data-testid="stDateInput"] [data-baseweb="input"] div,
[data-testid="stDateInput"] input {
background-color:#ffffff!important;color:#111111!important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] *,
[data-testid="stDateInput"] input {
color:#111111!important;-webkit-text-fill-color:#111111!important;
caret-color:#111111!important;
}
[data-testid="stSelectbox"] [data-baseweb="select"] > div,
[data-testid="stDateInput"] [data-baseweb="input"] {border:1px solid #8b967d!important;}
[data-testid="stSelectbox"] svg, [data-testid="stDateInput"] svg {color:#111111!important;fill:currentColor;}
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="popover"] [role="option"],
[data-baseweb="popover"] [role="option"] * {
background-color:#ffffff!important;color:#111111!important;-webkit-text-fill-color:#111111!important;
}
[data-baseweb="popover"] [role="option"]:hover,
[data-baseweb="popover"] [role="option"][aria-selected="true"] {background-color:#e8efdf!important;}
[data-testid="stFormSubmitButton"] button *, .stButton button *,
button[kind="primary"] *, button[data-testid="stBaseButton-primaryFormSubmit"] * {
color:#ffffff!important;-webkit-text-fill-color:#ffffff!important;
}

[data-testid="stExpander"] {background:#fffef7;color:#20251d;border-color:#c7ccb8;border-radius:12px;}
[data-testid="stExpander"] summary p {color:#20251d!important;}
[data-testid="stVerticalBlockBorderWrapper"]>div {border-color:#c7ccb8!important;border-radius:18px;}
[data-testid="stAlert"] {border-radius:12px;}
@media(min-width:769px) {[data-testid="stHorizontalBlock"] {align-items:stretch;gap:28px;}}
@media(max-width:768px) {
.block-container {padding:1.2rem 1rem 2rem;}
.hero {padding:18px 0 22px;margin-bottom:20px;}
.hero h1 {font-size:42px!important;}
.hero p {font-size:18px;}
[data-testid="stHorizontalBlock"] {flex-direction:column!important;gap:18px;}
[data-testid="stHorizontalBlock"]>[data-testid="stColumn"] {width:100%!important;flex:1 1 100%!important;min-width:0!important;}
[data-testid="stForm"] {padding:18px;}
}

/* LIGHT INPUT V3: target actual control surfaces independently of wrapper names. */
[data-baseweb="select"], [data-baseweb="select"] *,
[data-baseweb="input"], [data-baseweb="input"] *,
[data-baseweb="base-input"], [data-baseweb="base-input"] *,
[data-baseweb="textarea"], [role="combobox"],
input:not([type="radio"]):not([type="checkbox"]),
[data-baseweb="popover"] [role="listbox"],
[data-baseweb="popover"] [role="listbox"] * {
    background:#ffffff!important;
    background-color:#ffffff!important;
    color:#111111!important;
    -webkit-text-fill-color:#111111!important;
    caret-color:#111111!important;
    color-scheme:light!important;
}
[data-baseweb="select"] svg, [data-baseweb="input"] svg {
    fill:#111111!important;color:#111111!important;background:transparent!important;
}
[data-testid="stFormSubmitButton"] button,
[data-testid="stFormSubmitButton"] button *,
[data-testid="stDownloadButton"] button,
[data-testid="stDownloadButton"] button *,
.stButton button, .stButton button * {
    background:#ffffff!important;color:#111111!important;
    -webkit-text-fill-color:#111111!important;
    border-color:#809173!important;
}
[data-testid="stFormSubmitButton"] button,
[data-testid="stDownloadButton"] button {border:2px solid #809173!important;}


/* V4: include date-input's outer styled wrapper and select arrow wrappers.
   Streamlit versions differ in their BaseWeb wrapper attributes. */
[data-testid="stDateInput"] > div,
[data-testid="stDateInput"] > div > div,
[data-testid="stDateInput"] [data-baseweb],
[data-testid="stDateInput"] [data-baseweb] *,
[data-testid="stDateInputField"],
[data-testid="stDateInput"] input,
[data-baseweb="select"] > div,
[data-baseweb="select"] > div > div,
[data-baseweb="select"] [role="button"],
[data-baseweb="select"] [data-baseweb],
[data-baseweb="select"] [data-baseweb] *,
[data-testid="stSelectbox"] [data-baseweb="select"] > div > div:last-child {
 background:#ffffff!important;
 background-color:#ffffff!important;
 color:#111111!important;
 -webkit-text-fill-color:#111111!important;
 color-scheme:light!important;
}
[data-testid="stDateInput"] button,
[data-testid="stDateInput"] button *,
[data-testid="stDateInput"] svg,
[data-baseweb="select"] svg,
[data-baseweb="select"] svg * {
 background:#ffffff!important;color:#111111!important;
 -webkit-text-fill-color:#111111!important;
}
[data-testid="stDateInput"] svg,
[data-baseweb="select"] svg {fill:currentColor!important;}


/* V5: readable notices, static tables and save controls in light/dark themes. */
[data-testid="stAlert"],
[data-testid="stAlert"] > div,
[data-testid="stAlert"] [data-testid="stMarkdownContainer"],
[data-testid="stAlert"] [data-testid="stMarkdownContainer"] * {
 background:#edf3e7!important;color:#172315!important;
 -webkit-text-fill-color:#172315!important;
}
[data-testid="stAlert"] {border:1px solid #9bad8a!important;}
[data-testid="stTable"], [data-testid="stTable"] *,
[data-testid="stTable"] table, [data-testid="stTable"] th,
[data-testid="stTable"] td {
 background:#ffffff!important;color:#111111!important;
 -webkit-text-fill-color:#111111!important;
 border-color:#c3ccb9!important;
}
[data-testid="stTable"] th {background:#e8efdf!important;}
[data-testid="stTable"] {overflow-x:auto;}
[data-testid="stCaptionContainer"] p {color:#46513d!important;}

</style>""", unsafe_allow_html=True)
st.markdown("""<section class="hero"><div class="eyebrow">농사 날씨 길잡이 · 나의 밭, 나의 계절</div>
<h1>무엇을 심을까요?<br>날씨에서 답을 찾아요.</h1>
<p>지역과 심을 날짜를 골라 주세요. 앞으로 자라는 동안의 기온과 비를 살펴, 잘 맞는 작물과 주의할 작물을 알려드려요.</p></section>""", unsafe_allow_html=True)
st.caption("화면 버전: 화면 개선 5 · 작물 28종")
today = datetime.now(timezone(timedelta(hours=9))).date()
with st.form("settings"):
    st.subheader("우리 밭에 맞게 골라 주세요")
    region_col, date_col, climate_col = st.columns([1, 1, 1.15])
    with region_col:
        city = st.selectbox("① 농사지을 지역", list(CITIES), index=0)
        st.caption("도별 대표 지점 기준입니다. 같은 도에서도 날씨는 다를 수 있어요.")
    with date_col:
        selected_date = st.date_input("② 심을 날짜", value=today, min_value=today,
                                      max_value=today+timedelta(days=365), format="YYYY/MM/DD")
        st.caption("날짜 칸을 누르면 달력이 열려요. 선택한 날부터 비교합니다.")
    with climate_col:
        scenario = st.radio("③ 앞으로의 기온 가정", ["최근 5년과 비슷", "조금 더 따뜻함 (+2℃)", "조금 더 서늘함 (-2℃)"], horizontal=False)
    crop_choice = st.selectbox("④ 관심 작물 (선택사항)", ["작물 추천받기"] + [c[0] for c in CROPS])
    st.caption("잘 모르겠다면 추천받기를 그대로 두세요. 작물을 고르면 해당 작물의 관리 방법을 안내해 드려요.")
    run = st.form_submit_button("우리 밭에 맞는 작물 알아보기 →", type="primary", use_container_width=True)
st.caption("가까운 날은 단기 예보, 먼 날은 최근 5년 기후를 활용합니다. 몇 달 뒤 실제 날씨를 정확히 예측하는 서비스는 아닙니다.")

if run:
    st.session_state.pop("analysis", None)
    start = selected_date
    adjustment = {"최근 5년과 비슷": 0, "조금 더 따뜻함 (+2℃)": 2, "조금 더 서늘함 (-2℃)": -2}[scenario]
    lat, lon = CITIES[city]
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
            results = sorted([score_crop(c, outlook) for c in CROPS], key=lambda r: r['적합도'], reverse=True)
            target_name = results[0]['작물'] if crop_choice == '작물 추천받기' else crop_choice
            target_crop = next(c for c in CROPS if c[0] == target_name)
            date_options = []
            for offset in (0, 14, 30):
                candidate_date = start + timedelta(days=offset)
                candidate_outlook = build_outlook(normal, counts, short, candidate_date, 120, adjustment)
                candidate_score = score_crop(target_crop, candidate_outlook)
                date_options.append({'심을 날짜': candidate_date, '점수': candidate_score['적합도']})
            st.session_state['analysis'] = (city, start, scenario, results, outlook, note, today.year, crop_choice, date_options)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        st.error("날씨 자료를 불러오지 못했습니다. 인터넷 연결을 확인한 뒤 다시 눌러 주세요. 임의의 날씨로 대체하지 않습니다.")
        with st.expander("오류 내용 보기"):
            st.code(str(exc))

if 'analysis' in st.session_state:
    city, start, scenario, results, outlook, note, year, saved_choice, date_options = st.session_state['analysis']
    st.divider()
    st.subheader(f"{city} · {start.year}년 {start.month}월 {start.day}일 심기")
    if city == "독도":
        st.warning("독도는 해상 격자 기반 기후 참고용입니다. 작은 섬의 실제 기후·토양·염해·재배 가능성을 반영하지 않으므로 농작물 추천을 실제 재배 판단에 사용하지 마세요.")
    st.caption(f"기온 가정: {scenario} | 과거 자료: {year-5}~{year-1}년 | 노지 재배 가정")
    if note:
        st.warning(note)
    st.warning("점수는 아래 작물 사이의 교육용 비교 지수입니다. 수확 성공 확률이나 실제 수익이 아니며, 최고 점수가 낮으면 추천 작물도 적합하지 않을 수 있습니다.")
    target = results[0] if saved_choice == '작물 추천받기' else next(r for r in results if r['작물'] == saved_choice)
    cards = [("🌱 가장 유리한 작물", results[0]), ("🍂 가장 불리한 작물", results[-1])] if saved_choice == '작물 추천받기' else [("🌱 선택한 작물", target)]
    result_columns = st.columns(len(cards))
    for result_col, (heading, item) in zip(result_columns, cards):
        with result_col, st.container(border=True):
            st.subheader(f"{heading}: {item['작물']}")
            st.write(f"**비교 점수 {item['적합도']:.1f} / 100 · 생육 비교 {item['비교 기간']}일**")
            st.write(f"기간 평균 {item['평균기온']}℃ · 주당 평균 강수 {item['주당 강수량']}mm")
            for reason in item['이유']:
                st.write(f"• {reason}")
            st.caption(f"단기 예보 {item['예보 일수']}일 / 기후 기반 추정 {item['비교 기간']-item['예보 일수']}일")
    if target['적합도'] < 60:
        st.error("이번 조건에서는 안내 대상 작물의 점수가 낮습니다. 심는 시기를 바꾸거나 지역 농업기술센터에 확인하세요.")
    if results[0]['적합도'] == results[-1]['적합도']:
        st.info("모든 작물의 점수가 같습니다. 순위만으로 작물을 선택하지 마세요.")
    st.subheader(f"{target['작물']}, 이렇게 준비하세요")
    target_crop = next(c for c in CROPS if c[0] == target['작물'])
    tips = management(target_crop, outlook)
    for tip in tips:
        st.write("• " + tip)
    st.caption("장기 추정에 따른 준비 안내입니다. 실제 작업 날짜·물의 양·약제 사용을 지시하는 기능은 아닙니다.")
    st.subheader("언제 심으면 더 유리할까요?")
    st.write(f"같은 작물 **{target['작물']}**을 선택일·2주 뒤·30일 뒤에 심는 경우를 비교했어요.")
    st.table(pd.DataFrame(date_options))
    best_date = max(date_options, key=lambda x: x['점수'])
    base_score = date_options[0]['점수']
    if best_date['점수'] > base_score:
        st.success(f"세 날짜 중 {best_date['심을 날짜']:%Y년 %m월 %d일}이 {best_date['점수']:.1f}점으로 가장 유리합니다. 선택일보다 {best_date['점수']-base_score:.1f}점 높아요.")
    else:
        st.info("비교한 세 날짜 중 선택한 날보다 점수가 더 높은 날은 없습니다. 동점은 우열이 없어요.")
    st.caption("전체 날짜의 최적해가 아닌 세 날짜 비교입니다. 예보/추정 구성과 비교 기간이 날짜마다 달라지며, 높은 점수도 재배 성공을 보장하지 않습니다.")
    lines = ["농사 날씨 길잡이 · 결과 요약", f"지역: {city} / 심을 날짜: {start:%Y-%m-%d}",
             f"분석 방식: {saved_choice} / 기온 가정: {scenario}",
             f"안내 작물: {target['작물']} · {target['적합도']:.1f}점 / 100점",
             f"생육 비교: {target['비교 기간']}일 · 단기 예보 {target['예보 일수']}일, 나머지는 기후 추정"]
    if saved_choice == '작물 추천받기':
        lines += [f"가장 불리한 작물: {results[-1]['작물']} ({results[-1]['적합도']:.1f}점)"]
    lines += ['선정 이유'] + target['이유'] + ['관리 준비 사항'] + tips
    lines += ['심는 날짜 비교 (같은 작물)'] + [f"{r['심을 날짜']:%Y-%m-%d}: {r['점수']:.1f}점" for r in date_options]
    lines += [f"과거 기후 기준: {year-5}~{year-1}년 / 자료: Open-Meteo",
              "장기 일별 예보가 아닌 교육용 기후 비교입니다. 실제 농사 전 지역 농업기술센터에 확인하세요."]
    if note:
        lines.append(note)
    if city == '독도':
        lines.append('독도는 해상 격자 기후 참고용입니다. 실제 재배 판단에 사용하지 마세요.')
    st.subheader("결과를 저장해 두세요")
    try:
        png = result_image(lines)
        st.download_button("결과 한 장 저장 (이미지)", png, file_name=f"농사결과_{city}_{start}.png", mime="image/png", use_container_width=True)
    except (ValueError, OSError) as exc:
        st.warning(str(exc))
    st.download_button("글로 저장하기", '\n'.join(lines).encode('utf-8-sig'), file_name=f"농사결과_{start}.txt", mime="text/plain", use_container_width=True)
    with st.expander("전체 작물 비교 보기"):
        table = pd.DataFrame([{"작물": r['작물'], "점수(100점)": r['적합도'], "비교 기간(일)": r['비교 기간'], "평균기온(℃)": r['평균기온'], "주당 강수(mm)": r['주당 강수량']} for r in results])
        st.table(table)
        st.caption("작물별 일반적인 생육 기간을 단순화해 서로 다른 기간을 비교합니다. 동점은 우열이 없습니다.")
    with st.expander("월별 기온과 비 보기"):
        tmp = outlook.copy()
        tmp['월'] = pd.to_datetime(tmp['날짜']).dt.strftime('%Y년 %m월')
        monthly = tmp.groupby('월').agg(평균기온=(COLS[0], 'mean'), 기간강수량=(COLS[3], 'sum'), 비교일수=('날짜', 'count'))
        st.table(monthly.round(1).rename(columns={'평균기온': '평균기온(℃)', '기간강수량': '해당 기간 강수량(mm)', '비교일수': '비교 일수'}))
        st.caption("첫 달과 마지막 달은 일부 날짜만 포함합니다. 장기 값은 예보가 아니라 과거 기후 기반 추정입니다.")

with st.expander("계산 방법과 꼭 알아둘 점"):
    st.write("최근 5개 완결 연도의 같은 월·일 기온과 강수량을 평균합니다. 단기 예보가 있는 날짜는 그 예보를 사용하고, 나머지는 과거 평균을 사용합니다. ±2℃ 선택은 장기 추정값에만 적용하는 사용자의 가정이며 공식 기후 전망이 아닙니다.")
    st.write("점수 = 기온 적합도 80% + 강수 적합도 20% − 저온·고온 주의일 비중에 따른 감점. 기온은 적정 범위에서 1℃ 벗어날 때 7점, 주당 강수는 비교 범위에서 1mm 벗어날 때 2점 감점합니다. 저온·고온 감점 계수는 각각 25와 20이며 최종 점수는 0~100점입니다.")
    st.write("아래 기준은 앱 작동을 설명하기 위한 교육용 가정입니다. 작물별 기간은 실제 전체 생육 기간이 아니라 파종·정식 후 첫 수확 등을 단순화한 비교 구간입니다. 장기 재배 작물의 전 기간을 평가하지 않습니다. 공식 재배 권장 기준으로 검증되지 않았습니다. 파종·정식 구분, 품종, 토양, 일조, 시설, 관수, 병해충, 생육 단계는 반영하지 않았습니다. 과거 평균 최저·최고기온은 실제 한파·폭염 극값을 완화하므로 위험을 과소평가할 수 있습니다.")
    st.table(pd.DataFrame([{'작물': c[0], '기간(일)': c[1], '적정 평균기온(℃)': f'{c[2]}~{c[3]}', '저온 주의(℃ 미만)': c[4], '고온 주의(℃ 초과)': c[5], '주당 강수 비교(mm)': f'{c[6]}~{c[7]}'} for c in CROPS]))
    st.write("실제 재배 결정 전에는 지역 농업기술센터 또는 농사로의 품종별 재배 정보를 확인하세요. 대표 지점 자료이므로 같은 지역 안에서도 고도·지형에 따라 달라집니다.")
st.caption("날씨 자료: Open-Meteo · 기온/강수 재분석 자료와 단기 예보 사용 · 인터넷 연결 필요")
st.markdown("[날씨 자료 및 이용 조건](https://open-meteo.com/) · [과거 날씨 자료 설명](https://open-meteo.com/en/docs/historical-weather-api) · [농사로 재배 정보](https://www.nongsaro.go.kr/)")
