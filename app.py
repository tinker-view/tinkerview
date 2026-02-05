# ==========================================
# #1. 기본 설정 및 보안 영역
# ==========================================


# #1-1. 라이브러리 임포트
import streamlit as st
import pandas as pd
import requests
import json
import time
import re
from datetime import datetime, timedelta
from streamlit_calendar import calendar



# #1-2. 페이지 기본 설정 및 구글 시트 연결 정보
st.set_page_config(page_title="K-View", layout="wide")

DEPLOY_URL = "https://script.google.com/macros/s/AKfycbyy-bnPp9gZvvOSlFUFsvkGcYaTrIoR4Pyg7h6-9iDPOvIvvKHP2iqX79VCtpRUMfUz/exec"
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


# #2-1. 구글 시트 데이터 로드 (Read)
@st.cache_data(ttl=0)
def load_data(sheet_name):
    expected = {
        "members": ["순번", "성함", "연락처", "생년월일", "성별", "주소", "최초방문일", "상담사", "비고(특이사항)"],
        "schedules": ["성함", "날짜", "상품명", "상담사", "수가", "특가", "정산", "비고"],
        "reservations": ["성함", "날짜", "상품명", "상담사", "시간", "특이사항"]
    }
    try:
        url = f"{READ_URL}{sheet_name}&t={int(time.time())}"
        data = pd.read_csv(url, dtype=object).fillna("")
        if not data.empty:
            if len(data.columns) == len(expected[sheet_name]):
                data.columns = expected[sheet_name]
        return data
    except:
        return pd.DataFrame(columns=expected.get(sheet_name, []))



# #2-2. 구글 시트 데이터 조작 (C.U.D)
def manage_gsheet(sheet, row=None, action="add", key=None, extra=None):
    try:
        f_row = []
        for v in (row or []):
            val = str(v).strip()
            if not val:
                f_row.append("")
                continue
            if val.isdigit() and val.startswith("0"):
                f_row.append(f"'{val}")
            elif re.match(r'^[0-9.-]+$', val):
                f_row.append(val) 
            else:
                f_row.append(f"'{val}")
        
        params = {"sheet": sheet, "values": json.dumps(f_row), "action": action, "key": key}
        if extra: params.update(extra)
        r = requests.get(DEPLOY_URL, params=params, timeout=15)
        return "Success" in r.text
    except: return False



# ==========================================
# #3. 유틸리티 및 팝업 대화상자 영역
# ==========================================


# #3-1. 포맷팅 유틸리티
def format_phone(p):
    c = re.sub(r'\D', '', str(p)); return f"{c[:3]}-{c[3:7]}-{c[7:]}" if len(c) == 11 else c

def format_birth(b):
    c = re.sub(r'\D', '', str(b))
    if len(c) == 8: return f"{c[:4]}.{c[4:6]}.{c[6:]}"
    return c



# #3-2. [팝업] 신규 회원 등록
@st.dialog("👤 새 회원 등록")
def add_member_modal():
    with st.form("add_member_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        new_name = col1.text_input("성함 (필수)")
        new_phone = col2.text_input("연락처")
        col3, col4 = st.columns(2)
        new_birth = col3.text_input("생년월일 (8자리)")
        new_gender = col4.selectbox("성별", ["남", "여"])
        new_addr = st.text_input("주소")
        new_coun = st.text_input("담당 상담사")
        new_memo = st.text_area("비고")
        if st.form_submit_button("✅ 회원 등록 완료"):
            if not new_name: st.error("성함을 입력해주세요!")
            else:
                new_row = ["", new_name, new_phone, new_birth, new_gender, new_addr, datetime.now().strftime("%Y-%m-%d"), new_coun, new_memo]
                if manage_gsheet("members", new_row, action="add"):
                    st.cache_data.clear(); st.rerun()



# #3-3. [팝업] 신규 예약 등록 (검색 보완형)
@st.dialog("📅 새 예약 등록")
def add_res_modal(clicked_date, m_list):
    try:
        dt_parts = clicked_date.replace("Z", "").split("T")
        date_str, time_str = dt_parts[0], dt_parts[1][:5]
        base_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        kor_dt = base_dt + timedelta(hours=9)
        f_date, f_time = kor_dt.date(), kor_dt.time()
    except:
        f_date, f_time = datetime.now().date(), datetime.now().time()

    if "res_name_input" not in st.session_state: st.session_state.res_name_input = ""

    search_q = st.text_input("🔍 회원 검색", placeholder="이름 입력...")
    if search_q:
        filtered = m_list[m_list['성함'].str.contains(search_q, na=False)]['성함'].tolist()
        if filtered:
            sel_hint = st.selectbox("검색 결과 선택", ["선택하세요"] + filtered)
            if sel_hint != "선택하세요": st.session_state.res_name_input = sel_hint

    with st.form("res_real_form"):
        res_name = st.text_input("👤 예약자 성함", value=st.session_state.res_name_input)
        res_date = st.date_input("예약 날짜", value=f_date)
        time_slots = [f"{h:02d}:{m:02d}" for h in range(10, 19) for m in (0, 30)][:-1]
        t_idx = time_slots.index(f_time.strftime("%H:%M")) if f_time.strftime("%H:%M") in time_slots else 0
        res_time = st.selectbox("시간 선택", options=time_slots, index=t_idx)
        item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"])
        etc = st.text_area("특이사항")
        if st.form_submit_button("✅ 예약 저장"):
            if not res_name: st.error("성함을 입력해 주세요!")
            else:
                if manage_gsheet("reservations", [res_name, res_date.strftime("%Y-%m-%d"), item, "", res_time, etc]):
                    st.session_state.res_name_input = ""; st.cache_data.clear(); st.rerun()



# #3-4. [팝업] 회원 상세 정보 및 매출 관리
@st.dialog("👤 회원 정보 및 매출 관리")
def show_detail(m_info, h_df):
    t_v, t_s, t_e = st.tabs(["🔍 상세조회", "💰 매출등록", "✏️ 정보수정"])
    with t_v:
        st.markdown(f"### 👑 {m_info['성함']} 회원님")
        st.write(f"📞 {format_phone(m_info['연락처'])} | 🎂 {format_birth(m_info['생년월일'])}")
        st.write(f"🏠 {m_info['주소']}")
        st.divider()
        st.write("#### 💰 최근 매출 내역")
        if not h_df.empty:
            for i, r in h_df.iterrows():
                ci, cd = st.columns([8, 2])
                ci.write(f"📅 {r['날짜']} | 📦 {r['상품명']} | 💰 **{r['수가']}원**")
                if cd.button("삭제", key=f"d_sale_{i}"):
                    if manage_gsheet("schedules", action="delete_sales", key=m_info['성함'], extra={"date": r['날짜'], "item": r['상품명']}):
                        st.cache_data.clear(); st.rerun()
    with t_s:
        s_date = st.date_input("결제 날짜", datetime.now())
        with st.form("sale_f"):
            f_item = st.text_input("상품명")
            v_su = st.text_input("수가", value="0")
            if st.form_submit_button("💰 매출 저장"):
                if manage_gsheet("schedules", [m_info['성함'], s_date.strftime('%Y-%m-%d'), f_item, m_info['상담사'], v_su, 0, 0, ""]):
                    st.cache_data.clear(); st.rerun()
    with t_e:
        with st.form("ef"):
            e_p = st.text_input("연락처", value=m_info['연락처'])
            e_a = st.text_input("주소", value=m_info['주소'])
            e_m = st.text_area("비고", value=m_info['비고(특이사항)'])
            if st.form_submit_button("✅ 정보 수정 완료"):
                up_row = [m_info['순번'], m_info['성함'], e_p, m_info['생년월일'], m_info['성별'], e_a, m_info['최초방문일'], m_info['상담사'], e_m]
                if manage_gsheet("members", up_row, action="update", key=m_info['성함']):
                    st.cache_data.clear(); st.rerun()



# ==========================================
# #4. 메인 탭 UI 영역
# ==========================================


# #4-1. 데이터 로드 및 스타일
df_m, df_s, df_r = load_data("members"), load_data("schedules"), load_data("reservations")
st.markdown("<div style='font-size:26px; font-weight:800; color:#1E3A8A;'>✨ K-View</div>", unsafe_allow_html=True)
tabs = st.tabs(["📅 달력", "📋 예약", "👥 회원", "📊 매출"])



# #4-2. [탭 1] 스케줄 달력
with tabs[0]:
    st.subheader("📅 스케줄 달력")
    events = []
    if not df_r.empty:
        for _, r in df_r.iterrows():
            try:
                res_date = str(r.get('날짜', '')).replace("'", "").replace(".", "-").strip()
                res_time = re.sub(r'[^0-9:]', '', str(r.get('시간', '10:00')))
                hh, mm = (res_time.split(":") + ["00"])[:2]
                events.append({
                    "title": f"{r['성함']} ({r['상품명']})", "start": f"{res_date}T{hh.zfill(2)}:{mm.zfill(2)}:00",
                    "backgroundColor": "#3D5AFE", "borderColor": "#3D5AFE"
                })
            except: continue
    state = calendar(events=events, options={"initialView": "dayGridMonth", "selectable": True, "locale": "ko"}, key="calendar_v10")
    if state.get("dateClick"):
        raw_date = str(state["dateClick"]["date"])
        if "T" in raw_date: add_res_modal(raw_date, df_m)



# #4-3. [탭 2] 예약 내역 관리
with tabs[1]:
    st.subheader("📋 예약 내역 관리")
    if not df_r.empty:
        f_df = df_r.copy()
        sel_res = st.dataframe(f_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="res_tab")
        if sel_res.selection.rows:
            row = f_df.iloc[sel_res.selection.rows[0]]
            st.warning(f"⚠️ {row['성함']} 님의 예약을 삭제하시겠습니까?")
            if st.button("🗑️ 즉시 삭제", type="primary"):
                if manage_gsheet("reservations", action="delete_res", key=row['성함'], extra={"date": row['날짜'], "time": row['시간']}):
                    st.cache_data.clear(); st.rerun()
    else: st.info("내역 없음")



# #4-4. [탭 3] 회원 관리
with tabs[2]:
    st.subheader("👥 회원 관리")
    if st.button("➕ 새 회원 등록", use_container_width=True): add_member_modal()
    search_m = st.text_input("👤 회원 검색", key="m_search_main")
    if not df_m.empty:
        df_disp = df_m.copy()
        if search_m: df_disp = df_disp[df_disp['성함'].str.contains(search_m, na=False) | df_disp['연락처'].str.contains(search_m, na=False)]
        sel = st.dataframe(df_disp, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="mem_tab")
        if sel.selection.rows:
            m_info = df_disp.iloc[sel.selection.rows[0]]
            show_detail(m_info, df_s[df_s['성함'] == m_info['성함']])



# #4-5. [탭 4] 매출 및 로그아웃
with tabs[3]:
    if not df_s.empty:
        st.dataframe(df_s, use_container_width=True, hide_index=True)
if st.sidebar.button("로그아웃"): st.query_params.clear(); st.session_state.authenticated = False; st.rerun()
