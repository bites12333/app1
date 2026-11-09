"""농사 날씨 길잡이 — streamlit run app.py
GitHub에 app.py / requirements.txt 업로드 후 Streamlit Community Cloud로 배포.
인터넷 필요. API 키 불필요. Open-Meteo 무료 비상업 API의 이용 한도/약관 적용.
장기 계절예보 모델이 아닌 최근 5개 완결 연도 기후 기반 시나리오 앱.
작물 조건은 교육용 단순화 가정이며 지역별 재배 지침이나 수확량 예측이 아님.
"""
from __future__ import annotations

import calendar
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
button[kind="primary"] p {color:white!important;}
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
</style>""", unsafe_allow_html=True)
st.markdown("""<section class="hero"><div class="eyebrow">농사 날씨 길잡이 · 나의 밭, 나의 계절</div>
<h1>무엇을 심을까요?<br>날씨에서 답을 찾아요.</h1>
<p>지역과 심을 날짜를 골라 주세요. 앞으로 자라는 동안의 기온과 비를 살펴, 잘 맞는 작물과 주의할 작물을 알려드려요.</p></section>""", unsafe_allow_html=True)
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
            st.session_state['analysis'] = (city, start, scenario, results, outlook, note, today.year)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        st.error("날씨 자료를 불러오지 못했습니다. 인터넷 연결을 확인한 뒤 다시 눌러 주세요. 임의의 날씨로 대체하지 않습니다.")
        with st.expander("오류 내용 보기"):
            st.code(str(exc))

if 'analysis' in st.session_state:
    city, start, scenario, results, outlook, note, year = st.session_state['analysis']
    st.divider()
    st.subheader(f"{city} · {start.year}년 {start.month}월 {start.day}일 심기")
    if city == "독도":
        st.warning("독도는 해상 격자 기반 기후 참고용입니다. 작은 섬의 실제 기후·토양·염해·재배 가능성을 반영하지 않으므로 농작물 추천을 실제 재배 판단에 사용하지 마세요.")
    st.caption(f"기온 가정: {scenario} | 과거 자료: {year-5}~{year-1}년 | 노지 재배 가정")
    if note:
        st.warning(note)
    st.warning("점수는 아래 8개 작물 사이의 교육용 비교 지수입니다. 수확 성공 확률이나 실제 수익이 아니며, 최고 점수가 낮으면 추천 작물도 적합하지 않을 수 있습니다.")
    result_columns = st.columns(2)
    for result_col, (heading, item) in zip(result_columns, [("🌱 가장 유리한 작물", results[0]), ("🍂 가장 불리한 작물", results[-1])]):
        with result_col, st.container(border=True):
            st.subheader(f"{heading}: {item['작물']}")
            st.write(f"**비교 점수 {item['적합도']:.1f} / 100 · 생육 비교 {item['비교 기간']}일**")
            st.write(f"기간 평균 {item['평균기온']}℃ · 주당 평균 강수 {item['주당 강수량']}mm")
            for reason in item['이유']:
                st.write(f"• {reason}")
            st.caption(f"단기 예보 {item['예보 일수']}일 / 기후 기반 추정 {item['비교 기간']-item['예보 일수']}일")
    if results[0]['적합도'] < 60:
        st.error("이번 조건에서는 최고 점수도 낮습니다. 심는 시기를 바꾸거나 지역 농업기술센터에 확인하세요.")
    if results[0]['적합도'] == results[-1]['적합도']:
        st.info("모든 작물의 점수가 같습니다. 순위만으로 작물을 선택하지 마세요.")
    with st.expander("전체 작물 비교 보기"):
        table = pd.DataFrame([{"작물": r['작물'], "점수(100점)": r['적합도'], "비교 기간(일)": r['비교 기간'], "평균기온(℃)": r['평균기온'], "주당 강수(mm)": r['주당 강수량']} for r in results])
        st.dataframe(table, hide_index=True, use_container_width=True)
        st.caption("작물별 일반적인 생육 기간을 단순화해 서로 다른 기간을 비교합니다. 동점은 우열이 없습니다.")
    with st.expander("월별 기온과 비 보기"):
        tmp = outlook.copy()
        tmp['월'] = pd.to_datetime(tmp['날짜']).dt.strftime('%Y년 %m월')
        monthly = tmp.groupby('월').agg(평균기온=(COLS[0], 'mean'), 기간강수량=(COLS[3], 'sum'), 비교일수=('날짜', 'count'))
        st.dataframe(monthly.round(1).rename(columns={'평균기온': '평균기온(℃)', '기간강수량': '해당 기간 강수량(mm)', '비교일수': '비교 일수'}), use_container_width=True)
        st.caption("첫 달과 마지막 달은 일부 날짜만 포함합니다. 장기 값은 예보가 아니라 과거 기후 기반 추정입니다.")

with st.expander("계산 방법과 꼭 알아둘 점"):
    st.write("최근 5개 완결 연도의 같은 월·일 기온과 강수량을 평균합니다. 단기 예보가 있는 날짜는 그 예보를 사용하고, 나머지는 과거 평균을 사용합니다. ±2℃ 선택은 장기 추정값에만 적용하는 사용자의 가정이며 공식 기후 전망이 아닙니다.")
    st.write("점수 = 기온 적합도 80% + 강수 적합도 20% − 저온·고온 주의일 비중에 따른 감점. 기온은 적정 범위에서 1℃ 벗어날 때 7점, 주당 강수는 비교 범위에서 1mm 벗어날 때 2점 감점합니다. 저온·고온 감점 계수는 각각 25와 20이며 최종 점수는 0~100점입니다.")
    st.write("아래 기준은 앱 작동을 설명하기 위한 교육용 가정입니다. 공식 재배 권장 기준으로 검증되지 않았습니다. 파종·정식 구분, 품종, 토양, 일조, 시설, 관수, 병해충, 생육 단계는 반영하지 않았습니다. 과거 평균 최저·최고기온은 실제 한파·폭염 극값을 완화하므로 위험을 과소평가할 수 있습니다.")
    st.dataframe(pd.DataFrame([{'작물': c[0], '기간(일)': c[1], '적정 평균기온(℃)': f'{c[2]}~{c[3]}', '저온 주의(℃ 미만)': c[4], '고온 주의(℃ 초과)': c[5], '주당 강수 비교(mm)': f'{c[6]}~{c[7]}'} for c in CROPS]), hide_index=True, use_container_width=True)
    st.write("실제 재배 결정 전에는 지역 농업기술센터 또는 농사로의 품종별 재배 정보를 확인하세요. 대표 지점 자료이므로 같은 지역 안에서도 고도·지형에 따라 달라집니다.")
st.caption("날씨 자료: Open-Meteo · 기온/강수 재분석 자료와 단기 예보 사용 · 인터넷 연결 필요")
st.markdown("[날씨 자료 및 이용 조건](https://open-meteo.com/) · [과거 날씨 자료 설명](https://open-meteo.com/en/docs/historical-weather-api) · [농사로 재배 정보](https://www.nongsaro.go.kr/)")
