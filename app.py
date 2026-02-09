# ==========================================
# #1. 기본 설정 및 보안 영역 (인증 시스템)
# ==========================================


import streamlit as st
import pandas as pd
import requests
import json
import time
import re
from datetime import datetime, timedelta
from streamlit_calendar import calendar
import calendar as py_calendar



st.set_page_config(page_title="K-View", layout="wide")



# 🔗 연결 정보 및 상품 데이터
DEPLOY_URL = "https://script.google.com/macros/s/AKfycbxK_qwgL2BPZHWuCMfTa7clW1qfL_ipHAVg_dOdV3NoTHeCRe5oTFAwkqMBP8E0AxcX/exec"
SPREADSHEET_ID = "1o704HhhIJrBCux7ibPdYDDq6Z00J9QoogZ2oq6Fjgfc"
READ_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet="
PRODUCT_DATA = {"HP": 500000, "S1": 50000, "S2": 100000, "S3": 1000000, "S4": 9999999, "기타": 0}



# ==========================================
# #2. 데이터 통신 및 백엔드 함수 영역
# ==========================================


# #2-1. 구글 시트 데이터 로드 (Read) ㅋ
@st.cache_data(ttl=0)
def load_data(sheet_name):
    expected = {
        "members": ["순번", "성함", "연락처", "생년월일", "성별", "주소", "최초방문일", "상담사", "비고(특이사항)"],
        "schedules": ["성함", "날짜", "상품명", "상담사", "수가", "특가", "정산", "비고"],
        "reservations": ["성함", "날짜", "상품명", "상담사", "시간", "특이사항"],
        "stocks": ["항목", "현재고"],
        "users": ["ID", "PW", "이름", "권한"]
    }
    try:
        url = f"{READ_URL}{sheet_name}&t={int(time.time())}"
        data = pd.read_csv(url, dtype=object).fillna("")
        if not data.empty and len(data.columns) == len(expected.get(sheet_name, [])):
            data.columns = expected[sheet_name]
        return data
    except: return pd.DataFrame(columns=expected.get(sheet_name, []))



# #2-2. 구글 시트 데이터 조작 (C.U.D) ㅋ
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
# #3. 사용자 인증 및 로그인 관리 영역
# ==========================================


if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_role = None
    st.session_state.user_name = None



if not st.session_state.authenticated:
    st.title("🔐 K-View 멤버 접속")
    df_users = load_data("users")
    with st.form("login"):
        u = st.text_input("ID")
        p = st.text_input("PW", type="password")
        if st.form_submit_button("로그인"):
            user_match = df_users[(df_users['ID'] == u) & (df_users['PW'] == p)]
            if not user_match.empty:
                st.session_state.authenticated = True
                st.session_state.user_role = user_match.iloc[0]['권한']
                st.session_state.user_name = user_match.iloc[0]['이름']
                st.success(f"{st.session_state.user_name}님 환영합니다!")
                time.sleep(1); st.rerun()
            else: st.error("ID 또는 비밀번호가 올바르지 않습니다.")
    st.stop()



# ==========================================
# #4. 유틸리티 및 팝업 대화상자 (모달)
# ==========================================


# #4-1. 텍스트 포맷팅 유틸리티 ㅋ
def format_phone(p):
    c = re.sub(r'\D', '', str(p)); return f"{c[:3]}-{c[3:7]}-{c[7:]}" if len(c) == 11 else c


def format_birth(b):
    c = re.sub(r'\D', '', str(b)); return f"{c[:4]}.{c[4:6]}.{c[6:]}" if len(c) == 8 else c


# #4-2. [팝업] 신규 회원 등록 모달 ㅋ
@st.dialog("👤 새 회원 등록")
def add_member_modal():
    with st.form("add_member_form", clear_on_submit=True):
        c1, c2 = st.columns(2); n_name, n_phone = c1.text_input("성함 (필수)"), c2.text_input("연락처")
        c3, c4 = st.columns(2); n_birth, n_gender = c3.text_input("생년월일"), c4.selectbox("성별", ["남", "여"])
        n_addr, n_coun = st.text_input("주소"), st.text_input("담당 상담사")
        n_memo = st.text_area("비고(특이사항)")
        if st.form_submit_button("✅ 회원 등록 완료"):
            if n_name:
                row = ["", n_name, n_phone, n_birth, n_gender, n_addr, datetime.now().strftime("%Y-%m-%d"), n_coun, n_memo]
                if manage_gsheet("members", row, action="add"): st.cache_data.clear(); st.rerun()


# #4-3. [팝업] 신규 예약 등록 모달 (시차 보정 및 상태 초기화 완벽 반영) ㅋ
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
        res_time_str = st.selectbox("시간 선택", options=time_slots, index=time_slots.index(fixed_time.strftime("%H:%M")) if fixed_time.strftime("%H:%M") in time_slots else 0)
        item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"])
        coun = st.text_input("상담사", value=m_list[m_list['성함']==res_name]['상담사'].iloc[0] if not m_list[m_list['성함']==res_name].empty else "")
        etc = st.text_area("특이사항")


        if st.form_submit_button("✅ 예약 저장"):
            if res_name and not st.session_state.res_submitting:
                st.session_state.res_submitting = True
                if manage_gsheet("reservations", [res_name, res_date.strftime("%Y-%m-%d"), item, coun, res_time_str, etc]):
                    # 💡 성공 시 모든 팝업 관련 상태 초기화 후 리런 ㅋ
                    st.session_state.show_res_modal = False
                    st.session_state.clicked_date = None
                    st.session_state.res_name_input = ""
                    st.cache_data.clear()
                    st.rerun()



# #4-4. [팝업] 회원 상세 정보 및 매출/수정 통합 관리 모달 ㅋ
@st.dialog("👤 회원 정보 및 매출 관리")
def show_detail(m_info, h_df):
    if "pop_id" not in st.session_state or st.session_state.pop_id != m_info['성함']:
        st.session_state.sel_items = []; st.session_state.pop_id = m_info['성함']

    t_v, t_s, t_e = st.tabs(["🔍 상세조회", "💰 매출등록", "✏️ 정보수정"])

    
    # --- [탭 1] 회원 상세 조회 ㅋ ---
    with t_v:
        st.markdown(f"""
            <div style="background-color:#1E90FF; padding:12px; border-radius:8px; margin-bottom:20px; text-align:center;">
                <h3 style="margin:0; color:white;">👑 {m_info['성함']} <span style="font-size:14px; opacity:0.8;">회원님 상세 정보</span></h3>
            </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
            <div style="background-color:#ffffff; padding:20px; border-radius:10px; border:1px solid #e1e4e8; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">No. / 성함</span>
                    <b style="font-size:18px; color:#333;">{m_info['순번']}번 / {m_info['성함']}</b>
                </div>
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">연락처 / 생년월일</span>
                    <b style="font-size:18px; color:#333;">{format_phone(m_info['연락처'])} / {format_birth(m_info['생년월일'])}</b>
                </div>
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">주소</span>
                    <b style="font-size:16px; color:#333;">{m_info['주소'] if m_info['주소'] else '-'}</b>
                </div>
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">담당 상담사 / 최초방문일</span>
                    <b style="font-size:16px; color:#333;">{m_info['상담사']} / {m_info['최초방문일']}</b>
                </div>
            </div>
        """, unsafe_allow_html=True)
        st.write(""); st.markdown(f"📝 **비고(특이사항)**"); st.info(m_info['비고(특이사항)'] if m_info['비고(특이사항)'] else "내용 없음")
        
        st.divider(); st.write("#### 💰 최근 매출 내역")
        if not h_df.empty:
            for i, r in h_df.iterrows():
                ci, cd = st.columns([8, 2]); ci.write(f"📅 {r['날짜']} | 📦 {r['상품명']} | 💰 **{r['수가']}원**")
                if st.session_state.user_role == "admin" and cd.button("삭제", key=f"d_{i}"):
                    if manage_gsheet("schedules", action="delete_sales", key=m_info['성함'], extra={"date": r['날짜'], "item": r['상품명']}): st.cache_data.clear(); st.rerun()
        else: st.write("내역 없음")


    # --- [탭 2] 매출 등록 관리 ㅋ ---
    with t_s:
        if st.session_state.user_role != "admin": st.warning("매출 등록 권한이 없습니다.")
        else:
            s_date = st.date_input("결제 날짜", datetime.now())
            cols = st.columns(3)
            for k in PRODUCT_DATA.keys():
                if cols[list(PRODUCT_DATA.keys()).index(k)%3].button(f"{k}", key=f"pbtn_{k}"): st.session_state.sel_items.append({"n": k, "p": PRODUCT_DATA[k]})
            with st.form("sale_f"):
                f_item = st.text_input("상품명", value=", ".join([x['n'] for x in st.session_state.sel_items]))
                v_su = st.text_input("수가", value=str(sum([x['p'] for x in st.session_state.sel_items])))
                if st.form_submit_button("💰 매출 저장"):
                    if manage_gsheet("schedules", [m_info['성함'], s_date.strftime('%Y-%m-%d'), f_item, m_info['상담사'], int(re.sub(r'\D','',v_su)), 0, 0, ""]):
                        st.session_state.sel_items = []; st.cache_data.clear(); st.rerun()


    # --- [탭 3] 회원 정보 수정 ㅋ ---
    with t_e:
        with st.form("ef"):
            e_n = st.text_input("성함", value=m_info['성함']); e_p = st.text_input("연락처", value=m_info['연락처'])
            if st.form_submit_button("✅ 정보 수정 완료"):
                if manage_gsheet("members", [m_info['순번'], e_n, e_p, m_info['생년월일'], m_info['성별'], m_info['주소'], m_info['최초방문일'], m_info['상담사'], m_info['비고(특이사항)']], action="update", key=m_info['성함']): st.cache_data.clear(); st.rerun()


# #4-5. [팝업] 예약 정보 수정 모달 ㅋ
@st.dialog("✏️ 예약 수정")
def edit_res_modal(res_info):
    with st.form("edit_res_form"):
        n_date = st.date_input("날짜", value=pd.to_datetime(res_info['날짜']).date())
        time_slots = [f"{h:02d}:{m:02d}" for h in range(10, 19) for m in (0, 30)][:-1]
        n_time = st.selectbox("시간", options=time_slots, index=time_slots.index(res_info['시간']) if res_info['시간'] in time_slots else 0)
        n_item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"], index=["상담", "HP", "S1", "S2", "S3", "S4", "기타"].index(res_info['상품명']))
        n_etc = st.text_area("특이사항", value=res_info['특이사항'])
        if st.form_submit_button("✅ 수정 완료"):
            if manage_gsheet("reservations", [res_info['성함'], n_date.strftime("%Y-%m-%d"), n_item, res_info['상담사'], n_time, n_etc], action="update_res", key=res_info['성함'], extra={"old_date": res_info['날짜'], "old_time": res_info['시간']}): st.cache_data.clear(); st.rerun()

            

# ==========================================
# #5. 메인 레이아웃 및 상단 바 영역
# ==========================================


df_m, df_s, df_r, df_stock = load_data("members"), load_data("schedules"), load_data("reservations"), load_data("stocks")


def get_stock_val(item_name):
    if df_stock is None or df_stock.empty: return "?"
    try:
        temp = df_stock.copy(); temp.columns = temp.columns.str.strip()
        row = temp[temp['항목'].astype(str).str.strip() == item_name]
        return int(float(row['현재고'].values[0])) if not row.empty else 0
    except: return "!"


st.markdown(f"""
    <style>
        [data-testid="stHeader"], header {{ visibility: hidden !important; height: 0 !important; }}
        .top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-top: -45px; margin-bottom: 15px; }}
        .main-title {{ font-size: 22px !important; font-weight: 800 !important; color: #1E3A8A; }}
        .user-info {{ font-size: 14px; color: #6b7280; font-weight: 500; }}
        .stock-badge {{ font-size: 13px !important; font-weight: 700 !important; color: white; background: #ef4444; padding: 5px 12px; border-radius: 20px; }}
    </style>
    <div class="top-bar">
        <div class="main-title">✨ K-View <span class="user-info">({st.session_state.user_name} 님)</span></div>
        <div class="stock-badge">📦 HP: {get_stock_val("HP")} | S3: {get_stock_val("S3")}</div>
    </div>
""", unsafe_allow_html=True)


# ==========================================
# #6. 메인 탭 및 콘텐츠 영역
# ==========================================


tabs = st.tabs(["📅 달력", "📋 예약", "👥 회원", "📊 매출", "📦 재고"])


# #6-1. [탭 1] 스케줄 달력 (팝업 간섭 방지 및 클릭 연동) ㅋ
with tabs[0]:
    if "show_res_modal" not in st.session_state: st.session_state.show_res_modal = False


    events = []
    if not df_r.empty:
        for _, r in df_r.iterrows():
            try:
                res_date = str(r['날짜']).replace("'", "").replace(".", "-").strip()
                res_time = re.sub(r'[^0-9:]', '', str(r['시간']))
                events.append({
                    "title": f"{r['성함']} ({r['상품명']})", 
                    "start": f"{res_date}T{res_time}:00", 
                    "backgroundColor": "#3D5AFE", "borderColor": "#3D5AFE"
                })
            except: continue


    cal_opt = {
        "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"},
        "initialView": "timeGridWeek", "locale": "ko", "allDaySlot": False,
        "slotMinTime": "10:00:00", "slotMaxTime": "19:00:00", "height": "auto",
        "selectable": True, "slotEventOverlap": False,
        "slotLabelFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False}
    }


    state = calendar(events=events, options=cal_opt, key="kview_main_cal_v3")


    if state.get("callback") == "dateClick":
        new_date = state["dateClick"]["date"]
        if st.session_state.get("clicked_date") != new_date:
            st.session_state.clicked_date = new_date
            st.session_state.show_res_modal = True
            st.rerun()


    # 💡 팝업 호출을 탭 내부로 제한하여 다른 탭 간섭 방지 ㅋ
    if st.session_state.show_res_modal and st.session_state.get("clicked_date"):
        add_res_modal(st.session_state.clicked_date, df_m)
        


# #6-2. [탭 2] 예약 내역 관리 ㅋ
with tabs[1]:
    st.subheader("📋 예약 내역 관리")
    if not df_r.empty:
        c1, c2 = st.columns([2, 2]); today = datetime.now().date()
        f_type = c1.radio("📅 조회 기간", ["오늘", "이번 주", "이번 달", "전체"], horizontal=True, index=1)
        search = c2.text_input("🔍 예약 검색", key="res_search_tab2")
        f_df = df_r.copy(); f_df['날짜'] = pd.to_datetime(f_df['날짜']).dt.date
        if f_type == "오늘": f_df = f_df[f_df['날짜'] == today]
        elif f_type == "이번 주":
            start_of_week = today - timedelta(days=today.weekday())
            end_of_week = start_of_week + timedelta(days=6)
            f_df = f_df[(f_df['날짜'] >= start_of_week) & (f_df['날짜'] <= end_of_week)]
        elif f_type == "이번 달":
            f_df = f_df[(f_df['날짜'] >= today.replace(day=1)) & (f_df['날짜'] <= today.replace(day=py_calendar.monthrange(today.year, today.month)[1]))]
        if search: f_df = f_df[f_df['성함'].str.contains(search, na=False) | f_df['상품명'].str.contains(search, na=False)]
        f_df = f_df.sort_values(by=['날짜', '시간'], ascending=[True, True])
        sel_res = st.dataframe(f_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="res_table_final")
        if sel_res.selection.rows:
            row = f_df.iloc[sel_res.selection.rows[0]]; b1, b2, _ = st.columns([1, 1, 3])
            if b1.button("✏️ 예약 수정", key="btn_edit_res"): edit_res_modal(row)
            if st.session_state.user_role == "admin" and b2.button("🗑️ 즉시 삭제", key="btn_del_res", type="primary"):
                if manage_gsheet("reservations", action="delete_res", key=row['성함'], extra={"date": str(row['날짜']), "time": row['시간']}): st.cache_data.clear(); st.rerun()


# #6-3. [탭 3] 회원 관리 (팝업 충돌 방지 로직 포함) ㅋ
with tabs[2]:
    st.subheader("👥 회원 관리")
    
    if st.button("➕ 새 회원 등록", use_container_width=True):
        # 💡 다른 팝업 신호 강제 종료 후 회원 등록 팝업 호출 ㅋ
        st.session_state.show_res_modal = False
        st.session_state.clicked_date = None
        add_member_modal()


    st.divider()
    search_m = st.text_input("👤 회원 검색 (성함 또는 연락처 입력...)")


    if not df_m.empty:
        df_disp = df_m.copy()
        if search_m:
            df_disp = df_disp[df_disp['성함'].str.contains(search_m, na=False) | df_disp['연락처'].str.contains(search_m, na=False)]
        
        df_disp['연락처'] = df_disp['연락처'].apply(format_phone)
        sel = st.dataframe(df_disp, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="mem_table_main")


        if sel.selection.rows:
            # 💡 회원을 선택하는 순간 예약 팝업 스위치를 강제로 끕니다 ㅋ
            st.session_state.show_res_modal = False
            st.session_state.clicked_date = None
            
            m_info = df_disp.iloc[sel.selection.rows[0]]
            show_detail(m_info, df_s[df_s['성함'] == m_info['성함']])
    else:
        st.warning("등록된 회원 데이터가 없습니다.")



# #6-4. [탭 4] 매출 통계 ㅋ
with tabs[3]:
    st.subheader("📊 매출 통계")
    if not df_s.empty:
        st.dataframe(df_s, use_container_width=True, hide_index=True)
        if st.session_state.user_role == "admin":
            st.metric("총 정산 합계", f"{pd.to_numeric(df_s['정산'].apply(lambda x: str(x).replace(',','')), errors='coerce').sum():,.0f}원")


# #6-5. [탭 5] 재고 관리 ㅋ
with tabs[4]:
    st.subheader("📦 필수 재고 관리")
    if df_stock is None or df_stock.empty:
        if st.button("🔄 시트 다시 로드"): st.cache_data.clear(); st.rerun()
    else:
        col1, col2 = st.columns(2)
        for i, item in enumerate(["HP", "S3"]):
            with [col1, col2][i%2]:
                cur = get_stock_val(item); st.metric(f"{item} 현재고", f"{cur}개")
                if st.session_state.user_role == "admin":
                    adj = st.number_input(f"{item} 증감", value=0, key=f"adj_{item}")
                    if st.button(f"{item} 반영", key=f"btn_{item}"):
                        if manage_gsheet("stocks", action="update_stock", key=item, extra={"new_total": str(cur + adj)}): st.cache_data.clear(); st.rerun()
        st.divider(); st.dataframe(df_stock, use_container_width=True, hide_index=True)



# #7. 로그아웃 버튼 ㅋ
if st.sidebar.button("로그아웃"):
    st.query_params.clear(); st.session_state.authenticated = False; st.session_state.user_role = None; st.rerun()
