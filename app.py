"""농사 날씨 길잡이: streamlit run app.py
API 키 없이 Open-Meteo 비상업용 API 사용. 인터넷 필요.
작업 추천은 공개된 농업 표준이 아닌 교육용 비교 규칙입니다.
"""
from datetime import datetime, timedelta, timezone
import requests
import pandas as pd
import streamlit as st

st.set_page_config(page_title='농사 날씨 길잡이', page_icon='🌱', layout='wide')
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

@st.cache_data(ttl=3600, show_spinner=False)
def weather(lat, lon, year):
    daily='temperature_2m_mean,temperature_2m_min,temperature_2m_max,precipitation_sum,wind_speed_10m_max'
    r=requests.get('https://api.open-meteo.com/v1/forecast',params={'latitude':lat,'longitude':lon,'daily':daily,'timezone':'Asia/Seoul','wind_speed_unit':'ms','forecast_days':7},timeout=40)
    r.raise_for_status(); p=r.json()
    if p.get('error'): raise ValueError(p.get('reason'))
    f=pd.DataFrame(p['daily']).rename(columns={'time':'date'})
    f['date']=pd.to_datetime(f['date'])
    r=requests.get('https://archive-api.open-meteo.com/v1/archive',params={'latitude':lat,'longitude':lon,'start_date':f'{year-5}-01-01','end_date':f'{year-1}-12-31','daily':'temperature_2m_mean','timezone':'Asia/Seoul'},timeout=90)
    r.raise_for_status();p=r.json()
    if p.get('error'):raise ValueError(p.get('reason'))
    h=pd.DataFrame(p['daily']).rename(columns={'time':'date'})
    h['date']=pd.to_datetime(h['date']);h['key']=h.date.dt.strftime('%m-%d')
    baseline=h.groupby('key').temperature_2m_mean.agg(['mean','count'])
    for col in f.columns:
        if col!='date':f[col]=pd.to_numeric(f[col],errors='coerce')
    if f.dropna().shape[0]!=7:raise ValueError('7일 예보가 부족해요. 잠시 뒤 다시 눌러 주세요.')
    keys=f.date.dt.strftime('%m-%d')
    for key in keys:
        if key=='02-29' and (key not in baseline.index or baseline.loc[key,'count']<4):
            baseline.loc[key]=[(baseline.loc['02-28','mean']+baseline.loc['03-01','mean'])/2,5]
        if key not in baseline.index or baseline.loc[key,'count']<4:raise ValueError('과거 비교 자료가 부족해요.')
    f['평소기온']=keys.map(baseline['mean']);f['기온차']=f.temperature_2m_mean-f['평소기온']
    return f

def assess(row, task):
    rain=row['precipitation_sum']; wind=row['wind_speed_10m_max']; high=row['temperature_2m_max'];low=row['temperature_2m_min']
    issues=[]
    if high>=33:issues.append('너무 더워요')
    if low<=0:issues.append('얼 수 있어요')
    if wind>=8:issues.append('바람이 강해요')
    if task=='물주기':
        if rain>=3:issues.append('비가 예상돼요')
        action='흙이 마른지 먼저 만져 보세요. 젖어 있으면 물주기를 미루세요.'
    elif task=='수확':
        if rain>=1:issues.append('비가 예상돼요')
        action='날씨와 작물의 익은 정도를 함께 확인하세요.'
    else:
        if rain>=3:issues.append('비가 예상돼요')
        action='흙이 질면 밭일을 미루세요.'
    return len(issues), ' · '.join(issues) if issues else '큰 날씨 위험이 적어요', action

mode=st.radio('화면',['밝게 ☀️','어둡게 🌙'],horizontal=True)
dark=mode=='어둡게 🌙'; bg='#172019' if dark else '#f5f4e9'; fg='#f5f8f2' if dark else '#18241b';surface='#29382d' if dark else '#ffffff';red='#ffacac' if dark else '#ae2020'
st.markdown(f'''<style>
.stApp,[data-testid="stHeader"]{{background:{bg};color:{fg};}}
.block-container{{max-width:1300px;padding-top:2rem;}}
p,li,label,[data-testid="stWidgetLabel"] p{{font-size:21px!important;color:{fg}!important;}}
h1,h2,h3,[data-testid="stMetricValue"],[data-testid="stMetricLabel"] *{{color:{fg}!important;}}
[data-baseweb="select"] div,[data-baseweb="select"] input,[role="listbox"],[role="option"],button[kind]{{background:{surface}!important;color:{fg}!important;-webkit-text-fill-color:{fg}!important;}}
button p{{color:{fg}!important;}}svg{{fill:currentColor;}}
.action{{font-size:26px;font-weight:800;color:{red};margin:12px 0;}}
@media(max-width:768px){{[data-testid="stHorizontalBlock"]{{flex-direction:column;}}[data-testid="stColumn"]{{width:100%!important;flex:1 1 100%!important;}}}}
</style>''',unsafe_allow_html=True)
st.title('🌱 농사 날씨 길잡이')
st.write('평소와 다른 날씨, 밭일하기 좋은 날을 찾아요.')
a,b,c=st.columns(3)
with a:province=st.selectbox('지역',list(LOCALITIES))
with b:town=st.selectbox('가까운 시·군',list(LOCALITIES[province]))
with c:task=st.selectbox('할 일',['밭일','물주기','수확'])
st.caption('가까운 시·군의 대표 지점 기준이에요. 실제 밭의 날씨와 다를 수 있어요.')
if st.button('좋은 날 알아보기',use_container_width=True):
    try:
        today=datetime.now(timezone(timedelta(hours=9))).date()
        with st.spinner('날씨를 살펴보고 있어요…'):f=weather(*LOCALITIES[province][town],today.year)
        st.session_state['report']=(province,town,task,f)
    except (requests.RequestException,ValueError,KeyError,TypeError) as e:
        st.error('날씨를 불러오지 못했어요. 잠시 뒤 다시 눌러 주세요.')
        st.session_state.pop('report',None)
if 'report' in st.session_state:
    saved_province,saved_town,saved_task,f=st.session_state['report']
    st.subheader(f'{saved_province} {saved_town} · {saved_task}')
    if (province,town,task)!=(saved_province,saved_town,saved_task):st.caption('선택을 바꿨다면 알아보기를 다시 눌러 주세요.')
    diff=f['기온차'].mean()
    st.subheader('① 평소와 뭐가 달라요?')
    st.write(f'최근 5년 같은 날짜보다 평균 {abs(diff):.1f}℃ '+('높아요.' if diff>=0 else '낮아요.'))
    alerts=[]
    cold=f[f.temperature_2m_min<=0];hot=f[f.temperature_2m_max>=33];wet=f[f.precipitation_sum>=20]
    drops=f.temperature_2m_min.diff();drop_rows=f[drops<=-5]
    if not cold.empty:alerts.append((cold.iloc[0]['date'],'얼 수 있어요.','추위에 약한 작물의 보온 덮개를 준비하세요.'))
    if not hot.empty:alerts.append((hot.iloc[0]['date'],'많이 더워요.','한낮 작업을 피하고 작물이 마르는지 확인하세요.'))
    if not wet.empty:alerts.append((wet.iloc[0]['date'],'비가 많이 예상돼요.','물 빠지는 길을 확인하세요.'))
    if not drop_rows.empty:alerts.append((drop_rows.iloc[0]['date'],'아침 기온이 전날보다 5℃ 이상 내려가요.','추위에 약한 작물의 보온 준비를 하세요.'))
    if alerts:
        for day,problem,action in sorted(alerts,key=lambda x:x[0])[:3]:
            st.write(f'{day:%m/%d} · {problem}');st.markdown(f'<div class="action">{action}</div>',unsafe_allow_html=True)
    else:st.write('설정한 기준에서 큰 위험 신호는 없어요.')
    st.subheader('② 언제 하면 좋아요?')
    records=[]
    for _,row in f.iterrows():
        risk,problem,action=assess(row,saved_task)
        records.append({'date':row['date'],'위험수':risk,'문제':problem,'할일':action})
    ranked=sorted(records,key=lambda x:(x['위험수'],x['date']))
    best=ranked[0]
    if best['위험수']==0:
        st.markdown(f"### {best['date']:%m월 %d일}부터 확인해 보세요.")
        st.write('7일 중 날씨 위험이 가장 적은 날이에요. 동점이면 빠른 날을 골라요.')
    else:
        st.markdown('### 이번 주는 주의가 필요해요.')
        st.write(f"그중 {best['date']:%m/%d}의 위험 항목이 가장 적어요. 무조건 작업하기 좋은 날은 아니에요.")
    st.markdown(f'<div class="action">{best["할일"]}</div>',unsafe_allow_html=True)
    with st.expander('7일 날씨 보기'):
        table=pd.DataFrame({'날짜':f.date.dt.strftime('%m/%d'),'최저 ℃':f.temperature_2m_min,'최고 ℃':f.temperature_2m_max,'비 mm':f.precipitation_sum,'바람 m/s':f.wind_speed_10m_max,'참고':[r['문제'] for r in records]})
        st.table(table.set_index('날짜'))
    lines=[f'{saved_province} {saved_town} / {saved_task}',f'7일 평균 기온 차: {diff:+.1f}℃',f'위험 항목 최소 날짜: {best["date"]:%Y-%m-%d}',best['문제'],best['할일'],'예보는 바뀔 수 있어요. 작업 당일 다시 확인하세요.']
    st.download_button('결과 저장', '\n'.join(lines).encode('utf-8-sig'),file_name='농사날씨.txt',mime='text/plain')
st.caption('작업 당일 예보와 밭 상태를 다시 확인하세요. 농약 살포 추천은 하지 않아요.')
with st.expander('자료와 비교 기준'):
    st.write('Open-Meteo의 7일 일별 예보와 최근 5개 완결 연도의 같은 날짜 평균을 비교해요. 평년값(30년 평균)이나 올해의 실제 관측값은 아니에요.')
    st.write('교육용 기준: 최저 0℃ 이하, 최고 33℃ 이상, 일최대 바람 8m/s 이상을 주의로 봐요. 밭일은 비 3mm 이상, 수확은 1mm 이상을 추가 주의로 봐요. 토양·작물·시간대별 조건을 반영하지 않으므로 작업 가능 여부를 보장하지 않아요.')
    st.markdown('[날씨 자료: Open-Meteo](https://open-meteo.com/) · [자료 이용 조건](https://open-meteo.com/en/terms)')
st.caption('버전 13 · 다른 날씨 + 작업 날짜')
