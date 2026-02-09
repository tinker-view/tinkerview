# ==========================================
# #1. 기본 설정 및 보안 영역
# ==========================================

import streamlit as st
import pandas as pd
import requests
import json
import time
import re
from datetime import datetime, timedelta
from streamlit_calendar import calendar

st.set_page_config(page_title="K-View", layout="wide")

# 🔗 연결 정보 (대장님 정보 유지 ㅋ)
DEPLOY_URL = "https://script.google.com/macros/s/AKfycbxK_qwgL2BPZHWuCMfTa7clW1qfL_ipHAVg_dOdV3NoTHeCRe5oTFAwkqMBP8E0AxcX/exec"
SPREADSHEET_ID = "1o704HhhIJrBCux7ibPdYDDq6Z00J9QoogZ2oq6Fjgfc"
READ_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet="

PRODUCT_DATA = {"HP": 500000, "S1": 50000, "S2": 100000, "S3": 1000000, "S4": 9999999, "기타": 0}

# #1-3. 관리자 인증 시스템
if "authenticated" not in st.session_state:
    st.session_state.authenticated = True if st.query_params.get("auth") == "true" else False

if not st.session_state.authenticated:
    st.title("🔐 K-View 접속")
    with st.form("login"):
        u, p = st.text_input("ID"), st.text_input("PW", type="password")
        if st.form_submit_button("로그인"):
            if u == st.secrets["admin_id"] and p == st.secrets["admin_pw"]:
                st.session_state.authenticated = True
                st.query_params["auth"] = "true"
                st.rerun()
    st.stop()


# ==========================================
# #2. 데이터 통신 및 백엔드 관리 영역
# ==========================================

# #2-1. 구글 시트 데이터 로드 (stocks 추가 완료! ㅋ)
@st.cache_data(ttl=0)
def load_data(sheet_name):
    # 💡 욜루! 여기에 'stocks'를 추가해줘야 읽어옵니다 ㅋ
    expected = {
        "members": ["순번", "성함", "연락처", "생년월일", "성별", "주소", "최초방문일", "상담사", "비고(특이사항)"],
        "schedules": ["성함", "날짜", "상품명", "상담사", "수가", "특가", "정산", "비고"],
        "reservations": ["성함", "날짜", "상품명", "상담사", "시간", "특이사항"],
        "stocks": ["항목", "현재고"] # 💡 재고 시트 구조 정의 ㅋ
    }
    try:
        url = f"{READ_URL}{sheet_name}&t={int(time.time())}"
        data = pd.read_csv(url, dtype=object).fillna("")
        if not data.empty:
            # 컬럼 수가 맞으면 정의된 이름으로 변경 ㅋ
            if len(data.columns) == len(expected.get(sheet_name, [])):
                data.columns = expected[sheet_name]
        return data
    except:
        return pd.DataFrame(columns=expected.get(sheet_name, []))

# #2-2. 구글 시트 데이터 조작
def manage_gsheet(sheet, row=None, action="add", key=None, extra=None):
    try:
        f_row = []
        for v in (row or []):
            val = str(v).strip()
            if not val: f_row.append(""); continue
            if val.isdigit() and val.startswith("0"): f_row.append(f"'{val}")
            elif re.match(r'^[0-9.-]+$', val): f_row.append(val)
            else: f_row.append(f"'{val}")
        
        params = {"sheet": sheet, "values": json.dumps(f_row), "action": action, "key": key}
        if extra: params.update(extra)
        r = requests.get(DEPLOY_URL, params=params, timeout=15)
        return "Success" in r.text
    except: return False


# ==========================================
# #3. 유틸리티 및 팝업 대화상자 영역 (함수들 유지)
# ==========================================

def format_phone(p):
    c = re.sub(r'\D', '', str(p)); return f"{c[:3]}-{c[3:7]}-{c[7:]}" if len(c) == 11 else c

def format_birth(b):
    c = re.sub(r'\D', '', str(b)); return f"{c[:4]}.{c[4:6]}.{c[6:]}" if len(c) == 8 else c

@st.dialog("👤 새 회원 등록")
def add_member_modal():
    with st.form("add_member_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        new_name, new_phone = col1.text_input("성함 (필수)"), col2.text_input("연락처")
        col3, col4 = st.columns(2)
        new_birth, new_gender = col3.text_input("생년월일"), col4.selectbox("성별", ["남", "여"])
        new_addr, new_coun = st.text_input("주소"), st.text_input("담당 상담사")
        new_memo = st.text_area("비고")
        if st.form_submit_button("✅ 회원 등록 완료"):
            if new_name:
                new_row = ["", new_name, new_phone, new_birth, new_gender, new_addr, datetime.now().strftime("%Y-%m-%d"), new_coun, new_memo]
                if manage_gsheet("members", new_row, action="add"):
                    st.cache_data.clear(); st.rerun()

@st.dialog("📅 새 예약 등록")
def add_res_modal(clicked_date, m_list):
    if "last_clicked_date" not in st.session_state or st.session_state.last_clicked_date != clicked_date:
        st.session_state.res_name_input = ""; st.session_state.last_clicked_date = clicked_date; st.session_state.res_submitting = False
    try:
        dt_parts = clicked_date.replace("Z", "").split("T")
        kor_dt = datetime.strptime(f"{dt_parts[0]} {dt_parts[1][:5]}", "%Y-%m-%d %H:%M") + timedelta(hours=9)
        fixed_date, fixed_time = kor_dt.date(), kor_dt.time()
    except: fixed_date, fixed_time = datetime.now().date(), datetime.now().time()
    st.write(f"📅 선택 시간: **{fixed_date} {fixed_time.strftime('%H:%M')}**")
    search_q = st.text_input("🔍 회원 검색", key="res_search_field")
    if search_q:
        filtered = m_list[m_list['성함'].str.contains(search_q, na=False)]['성함'].tolist()
        if filtered:
            sel_hint = st.selectbox("검색 결과 선택", ["선택하세요"] + filtered)
            if sel_hint != "선택하세요": st.session_state.res_name_input = sel_hint
    with st.form("res_real_form_final", clear_on_submit=True):
        res_name = st.text_input("👤 예약자 성함 (필수)", value=st.session_state.res_name_input)
        res_date = st.date_input("예약 날짜", value=fixed_date)
        time_slots = [f"{h:02d}:{m:02d}" for h in range(10, 19) for m in (0, 30)][:-1]
        default_idx = time_slots.index(fixed_time.strftime("%H:%M")) if fixed_time.strftime("%H:%M") in time_slots else 0
        res_time_str = st.selectbox("시간 선택", options=time_slots, index=default_idx)
        item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"])
        coun = st.text_input("상담사")
        etc = st.text_area("특이사항")
        submit_label = "⏳ 등록 중..." if st.session_state.res_submitting else "✅ 예약 저장"
        if st.form_submit_button(submit_label):
            if res_name and not st.session_state.res_submitting:
                st.session_state.res_submitting = True
                if manage_gsheet("reservations", [res_name, res_date.strftime("%Y-%m-%d"), item, coun, res_time_str, etc]):
                    st.session_state.show_res_modal = False; st.cache_data.clear(); st.rerun()

@st.dialog("👤 회원 정보 및 매출 관리")
def show_detail(m_info, h_df):
    if "pop_id" not in st.session_state or st.session_state.pop_id != m_info['성함']:
        st.session_state.sel_items = []; st.session_state.pop_id = m_info['성함']
    t_v, t_s, t_e = st.tabs(["🔍 상세조회", "💰 매출등록", "✏️ 정보수정"])
    with t_v:
        st.info(f"👑 {m_info['성함']} 회원님 정보")
        st.write(m_info)
        st.divider(); st.write("💰 최근 매출 내역")
        if not h_df.empty:
            for i, r in h_df.iterrows():
                if st.button(f"🗑️ {r['날짜']} {r['상품명']} 삭제", key=f"d_{i}"):
                    if manage_gsheet("schedules", action="delete_sales", key=m_info['성함'], extra={"date": r['날짜'], "item": r['상품명']}):
                        st.cache_data.clear(); st.rerun()
    with t_s:
        s_date = st.date_input("결제 날짜", datetime.now())
        cols = st.columns(3)
        for k in PRODUCT_DATA.keys():
            if cols[list(PRODUCT_DATA.keys()).index(k)%3].button(f"{k}", key=f"pbtn_{k}"):
                st.session_state.sel_items.append({"n": k, "p": PRODUCT_DATA[k]})
        calc_t = sum([x['p'] for x in st.session_state.sel_items])
        with st.form("sale_f"):
            f_item = st.text_input("상품명", value=", ".join([x['n'] for x in st.session_state.sel_items]))
            v_su = st.text_input("수가", value=str(calc_t))
            if st.form_submit_button("💰 매출 저장"):
                if manage_gsheet("schedules", [m_info['성함'], s_date.strftime('%Y-%m-%d'), f_item, m_info['상담사'], int(v_su), 0, 0, ""]):
                    st.session_state.sel_items = []; st.cache_data.clear(); st.rerun()
    with t_e:
        with st.form("ef"):
            e_n = st.text_input("성함", value=m_info['성함'])
            if st.form_submit_button("✅ 정보 수정 완료"):
                if manage_gsheet("members", [m_info['순번'], e_n, m_info['연락처'], m_info['생년월일'], m_info['성별'], m_info['주소'], m_info['최초방문일'], m_info['상담사'], m_info['비고(특이사항)']], action="update", key=m_info['성함']):
                    st.cache_data.clear(); st.rerun()

@st.dialog("✏️ 예약 수정")
def edit_res_modal(res_info):
    with st.form("edit_res_form"):
        new_date = st.date_input("날짜", value=pd.to_datetime(res_info['날짜']).date())
        time_slots = [f"{h:02d}:{m:02d}" for h in range(10, 19) for m in (0, 30)][:-1]
        new_time = st.selectbox("시간", options=time_slots, index=time_slots.index(res_info['시간']) if res_info['시간'] in time_slots else 0)
        new_item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"], index=["상담", "HP", "S1", "S2", "S3", "S4", "기타"].index(res_info['상품명']))
        if st.form_submit_button("✅ 수정 완료"):
            if manage_gsheet("reservations", [res_info['성함'], new_date.strftime("%Y-%m-%d"), new_item, res_info['상담사'], new_time, res_info['특이사항']], action="update_res", key=res_info['성함'], extra={"old_date": res_info['날짜'], "old_time": res_info['시간']}):
                st.cache_data.clear(); st.rerun()


# ==========================================
# #4. 메인 탭 UI 및 대시보드 영역 (재고 연동 완벽 버전! ㅋ)
# ==========================================

# #4-1. 데이터 로드
df_m, df_s, df_r = load_data("members"), load_data("schedules"), load_data("reservations")
df_stock = load_data("stocks")

# 💡 실시간 재고 계산 함수 (공백 및 타입 방어 로직 ㅋ)
def get_stock_val(item_name):
    if df_stock is None or df_stock.empty: return 0
    try:
        # 헤더와 데이터의 공백을 제거하고 비교 ㅋ
        temp = df_stock.copy()
        temp.columns = temp.columns.str.strip()
        row = temp[temp['항목'].astype(str).str.strip() == item_name]
        if not row.empty:
            return int(float(row['현재고'].values[0]))
    except: return 0
    return 0

# 상단 현황판 스타일
st.markdown(f"""
    <style>
        [data-testid="stHeader"], header {{ visibility: hidden !important; height: 0 !important; }}
        .top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-top: -45px; margin-bottom: 15px; padding: 0 5px; }}
        .main-title {{ font-size: 22px !important; font-weight: 800 !important; color: #1E3A8A; }}
        .stock-badge {{ font-size: 13px !important; font-weight: 700 !important; color: #ffffff; background: #ef4444; padding: 5px 12px; border-radius: 20px; }}
        /* 달력/반응형 스타일 ㅋ */
        @media screen and (max-width: 600px) {{ .fc-event-time {{ display: none !important; }} .fc-event-title {{ font-size: 12px !important; white-space: nowrap !important; }} }}
    </style>
    <div class="top-bar">
        <div class="main-title">✨ K-View</div>
        <div class="stock-badge">📦 HP: {get_stock_val("HP")} | S3: {get_stock_val("S3")}</div>
    </div>
""", unsafe_allow_html=True)

tabs = st.tabs(["📅 달력", "📋 예약", "👥 회원", "📊 매출", "📦 재고"])

# #4-2 ~ #4-5 (기존 로직 유지)
with tabs[0]:
    if "show_res_modal" not in st.session_state: st.session_state.show_res_modal = False
    events = []
    if not df_r.empty:
        for _, r in df_r.iterrows():
            events.append({"title": f"{r['성함']} ({r['상품명']})", "start": f"{r['날짜']}T{r['시간']}:00", "backgroundColor": "#3D5AFE"})
    state = calendar(events=events, options={"initialView": "timeGridWeek", "locale": "ko", "slotMinTime": "10:00:00", "slotMaxTime": "19:00:00", "hiddenDays": [0]}, key="cal")
    if state.get("callback") == "dateClick":
        st.session_state.clicked_res_info = str(state["dateClick"]["date"])
        st.session_state.show_res_modal = True; st.rerun()
    if st.session_state.show_res_modal: add_res_modal(st.session_state.clicked_res_info, df_m)

with tabs[1]:
    st.subheader("📋 예약 내역")
    st.dataframe(df_r, use_container_width=True, hide_index=True)

with tabs[2]:
    st.subheader("👥 회원 관리")
    if st.button("➕ 새 회원 등록"): add_member_modal()
    sel = st.dataframe(df_m, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
    if sel.selection.rows:
        m = df_m.iloc[sel.selection.rows[0]]
        show_detail(m, df_s[df_s['성함'] == m['성함']])

with tabs[3]:
    st.subheader("📊 매출 통계")
    st.dataframe(df_s, use_container_width=True)

# #4-6. [탭 5] 재고 관리 (성공 보장 버전! ㅋ)
with tabs[4]:
    st.subheader("📦 필수 재고 관리")
    if df_stock is None or df_stock.empty:
        st.error("🚨 'stocks' 시트를 읽어오지 못했습니다! (load_data 체크 필요)")
        if st.button("🔄 강제 새로고침"): st.cache_data.clear(); st.rerun()
    else:
        col1, col2 = st.columns(2)
        for i, item in enumerate(["HP", "S3"]):
            with [col1, col2][i%2]:
                cur = get_stock_val(item)
                st.metric(f"{item} 현재고", f"{cur}개")
                adj = st.number_input(f"{item} 증감 (+/-)", value=0, key=f"adj_{item}")
                if st.button(f"{item} 반영", key=f"btn_{item}"):
                    # 💡 GAS로 계산된 최종 수량 전달 ㅋ
                    if manage_gsheet("stocks", action="update_stock", key=item, extra={"new_total": str(cur + adj)}):
                        st.success("반영 완료!"); st.cache_data.clear(); st.rerun()
        st.divider(); st.write("📋 전체 현황")
        st.dataframe(df_stock, use_container_width=True, hide_index=True)

if st.sidebar.button("로그아웃"): st.query_params.clear(); st.session_state.authenticated = False; st.rerun()
