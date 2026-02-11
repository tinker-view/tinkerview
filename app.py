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


# 💡 세션 상태 초기화 및 주소창 파라미터 체크 (새로고침 대응) ㅋ
if "authenticated" not in st.session_state:
    if st.query_params.get("auth") == "true":
        st.session_state.authenticated = True
        st.session_state.user_name = st.query_params.get("u_name")
        st.session_state.user_role = st.query_params.get("u_role")
    else:
        st.session_state.authenticated = False
        st.session_state.user_role = None
        st.session_state.user_name = None


# 💡 미인증 상태일 때 로그인 폼 출력 ㅋ
if not st.session_state.authenticated:
    st.title("🔐 K-View 멤버 접속")
    df_users = load_data("users")
    with st.form("login"):
        u, p = st.text_input("ID"), st.text_input("PW", type="password")
        if st.form_submit_button("로그인"):
            user_match = df_users[(df_users['ID'] == u) & (df_users['PW'] == p)]
            if not user_match.empty:
                st.session_state.authenticated = True
                st.session_state.user_role = user_match.iloc[0]['권한']
                st.session_state.user_name = user_match.iloc[0]['이름']
                st.query_params["auth"] = "true"
                st.query_params["u_name"] = st.session_state.user_name
                st.query_params["u_role"] = st.session_state.user_role
                st.success(f"{st.session_state.user_name}님 환영합니다!"); time.sleep(1); st.rerun()
            else: st.error("ID 또는 비밀번호가 올바르지 않습니다.")
    st.stop()


# 💡 새로고침 시 정보 복구 ㅋ
if st.session_state.authenticated and (st.session_state.user_name is None):
    st.session_state.user_name = st.query_params.get("u_name", "사용자")
    st.session_state.user_role = st.query_params.get("u_role", "staff")



# ==========================================
# #4. 유틸리티 및 팝업 대화상자 (모달)
# ==========================================


def format_phone(p):
    c = re.sub(r'\D', '', str(p)); return f"{c[:3]}-{c[3:7]}-{c[7:]}" if len(c) == 11 else c


def format_birth(b):
    c = re.sub(r'\D', '', str(b)); return f"{c[:4]}.{c[4:6]}.{c[6:]}" if len(c) == 8 else c


# #4-2. [팝업] 신규 회원 등록 모달 (순번 자동+수동 입력) ㅋ
@st.dialog("👤 새 회원 등록")
def add_member_modal():
    # 💡 현재 회원 데이터에서 마지막 순번 찾기 ㅋ
    df_m = load_data("members")
    try:
        # 숫자로 변환 가능한 것 중 최대값 찾기 ㅋ
        last_no = pd.to_numeric(df_m['순번'], errors='coerce').max()
        if pd.isna(last_no): last_no = 0
    except:
        last_no = 0
    
    next_no = int(last_no) + 1 # 자동 제안 번호 ㅋ


    with st.form("add_member_form", clear_on_submit=True):
        col_id, col_name = st.columns([1, 2])
        # 💡 자동 계산된 번호를 기본값으로 넣되, 수정 가능하게 함 ㅋ
        new_no = col_id.text_input("순번", value=str(next_no)) 
        new_name = col_name.text_input("성함 (필수)")
        
        c1, c2 = st.columns(2)
        new_phone = c1.text_input("연락처 (예: 01012345678)")
        new_birth = c2.text_input("생년월일 (예: 19900101)")
        
        c3, c4 = st.columns(2)
        new_gender = c3.selectbox("성별", ["남", "여"])
        new_date = c4.date_input("최초가입일", value=datetime.now())
        
        new_addr = st.text_input("주소")
        new_coun = st.text_input("담당 상담사")
        new_memo = st.text_area("비고(특이사항)")
        
        if st.form_submit_button("✅ 회원 등록 완료"):
            if not new_name:
                st.error("성함을 입력해주세요!")
            else:
                row = [
                    new_no,               
                    new_name,             
                    new_phone,            
                    new_birth,            
                    new_gender,           
                    new_addr,             
                    new_date.strftime("%Y-%m-%d"), 
                    new_coun,             
                    new_memo              
                ]
                
                if manage_gsheet("members", row, action="add"):
                    st.success(f"{new_name} 님이 {new_no}번으로 등록되었습니다!")
                    st.cache_data.clear()
                    st.rerun()


                    

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
                    st.session_state.show_res_modal = False
                    st.session_state.clicked_date = None
                    st.session_state.res_name_input = ""
                    st.cache_data.clear(); st.rerun()


@st.dialog("👤 회원 정보 및 매출 관리")
def show_detail(m_info, h_df):
    if "pop_id" not in st.session_state or st.session_state.pop_id != m_info['성함']:
        st.session_state.sel_items = []; st.session_state.pop_id = m_info['성함']
    t_v, t_s, t_e = st.tabs(["🔍 상세조회", "💰 매출등록", "✏️ 정보수정"])
    with t_v:
        st.markdown(f'<div style="background-color:#1E90FF; padding:12px; border-radius:8px; margin-bottom:20px; text-align:center;"><h3 style="margin:0; color:white;">👑 {m_info["성함"]} 회원님 상세 정보</h3></div>', unsafe_allow_html=True)
        st.markdown(f'<div style="background-color:#ffffff; padding:20px; border-radius:10px; border:1px solid #e1e4e8; box-shadow: 0 2px 4px rgba(0,0,0,0.05);"><div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;"><span style="color:#888; font-size:13px; display:block;">No. / 성함</span><b style="font-size:18px; color:#333;">{m_info["순번"]}번 / {m_info["성함"]}</b></div><div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;"><span style="color:#888; font-size:13px; display:block;">연락처 / 생년월일</span><b style="font-size:18px; color:#333;">{format_phone(m_info["연락처"])} / {format_birth(m_info["생년월일"])}</b></div><div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;"><span style="color:#888; font-size:13px; display:block;">주소</span><b style="font-size:16px; color:#333;">{m_info["주소"] if m_info["주소"] else "-"}</b></div><div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;"><span style="color:#888; font-size:13px; display:block;">담당 상담사 / 최초방문일</span><b style="font-size:16px; color:#333;">{m_info["상담사"]} / {m_info["최초방문일"]}</b></div></div>', unsafe_allow_html=True)
        st.write(""); st.markdown(f"📝 **비고(특이사항)**"); st.info(m_info['비고(특이사항)'] if m_info['비고(특이사항)'] else "내용 없음")
        st.divider(); st.write("#### 💰 최근 매출 내역")
        if not h_df.empty:
            for i, r in h_df.iterrows():
                ci, cd = st.columns([8, 2]); ci.write(f"📅 {r['날짜']} | 📦 {r['상품명']} | 💰 **{r['수가']}원**")
                if st.session_state.user_role == "admin" and cd.button("삭제", key=f"d_{i}"):
                    if manage_gsheet("schedules", action="delete_sales", key=m_info['성함'], extra={"date": r['날짜'], "item": r['상품명']}): st.cache_data.clear(); st.rerun()
        else: st.write("내역 없음")
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
    with t_e:
        with st.form("ef"):
            e_n = st.text_input("성함", value=m_info['성함']); e_p = st.text_input("연락처", value=m_info['연락처'])
            if st.form_submit_button("✅ 정보 수정 완료"):
                if manage_gsheet("members", [m_info['순번'], e_n, e_p, m_info['생년월일'], m_info['성별'], m_info['주소'], m_info['최초방문일'], m_info['상담사'], m_info['비고(특이사항)']], action="update", key=m_info['성함']): st.cache_data.clear(); st.rerun()


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


st.markdown(f'<style>[data-testid="stHeader"], header {{ visibility: hidden !important; height: 0 !important; }} .top-bar {{ display: flex; justify-content: space-between; align-items: center; margin-top: -45px; margin-bottom: 15px; }} .main-title {{ font-size: 22px !important; font-weight: 800 !important; color: #1E3A8A; }} .user-info {{ font-size: 14px; color: #6b7280; font-weight: 500; }} .stock-badge {{ font-size: 13px !important; font-weight: 700 !important; color: white; background: #ef4444; padding: 5px 12px; border-radius: 20px; }}</style><div class="top-bar"><div class="main-title">✨ K-View <span class="user-info">({st.session_state.user_name} 님)</span></div><div class="stock-badge">📦 HP: {get_stock_val("HP")} | S3: {get_stock_val("S3")}</div></div>', unsafe_allow_html=True)



# ==========================================
# #6. 메인 탭 및 콘텐츠 영역
# ==========================================


# 💡 [핵심] 탭 선택을 세션에 저장하여 팝업 실행 시점 제어 ㅋ
tab_list = ["📅 달력", "📋 예약", "👥 회원", "📊 매출", "📦 재고"]
tabs = st.tabs(tab_list)


# #6-1. [탭 1] 스케줄 달력 ㅋ
with tabs[0]:
    if "show_res_modal" not in st.session_state: st.session_state.show_res_modal = False
    events = []
    if not df_r.empty:
        for _, r in df_r.iterrows():
            try:
                res_date = str(r['날짜']).replace("'", "").replace(".", "-").strip()
                res_time = re.sub(r'[^0-9:]', '', str(r['시간']))
                events.append({"title": f"{r['성함']} ({r['상품명']})", "start": f"{res_date}T{res_time}:00", "backgroundColor": "#3D5AFE", "borderColor": "#3D5AFE"})
            except: continue
    cal_opt = {"headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"}, "initialView": "timeGridWeek", "locale": "ko", "allDaySlot": False, "slotMinTime": "10:00:00", "slotMaxTime": "19:00:00", "height": "auto", "selectable": True, "slotEventOverlap": False, "slotLabelFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False}}
    
    state = calendar(events=events, options=cal_opt, key="kview_final_cal_v6")
    
    if state.get("callback") == "dateClick":
        click_data = state["dateClick"]["date"]
        # 처리되지 않은 새로운 클릭일 때만 팝업 띄움 ㅋ
        if st.session_state.get("last_processed_click") != click_data:
            st.session_state.clicked_date = click_data
            st.session_state.last_processed_click = click_data
            st.session_state.show_res_modal = True
            st.rerun()

    # 💡 [이중 잠금] 달력 탭 안에 있을 때만 예약 팝업 실행 ㅋ
if st.session_state.show_res_modal and st.session_state.get("clicked_date"):
    st.session_state.show_res_modal = False # 👈 팝업창을 띄우자마자 스위치를 꺼버림!
    add_res_modal(st.session_state.clicked_date, df_m)

    

# #6-2. [탭 2] 예약 내역 관리 ㅋ
with tabs[1]:
    st.session_state.show_res_modal = False # 타 탭 진입 시 예약 팝업 강제 종료 ㅋ
    st.subheader("📋 예약 내역 관리")
    if not df_r.empty:
        c1, c2 = st.columns([2, 2]); today = datetime.now().date()
        f_type = c1.radio("📅 조회 기간", ["오늘", "이번 주", "이번 달", "전체"], horizontal=True, index=1)
        search = c2.text_input("🔍 예약 검색", key="res_search_tab2")
        f_df = df_r.copy(); f_df['날짜'] = pd.to_datetime(f_df['날짜']).dt.date
        if f_type == "오늘": f_df = f_df[f_df['날짜'] == today]
        elif f_type == "이번 주":
            start = today - timedelta(days=today.weekday()); end = start + timedelta(days=6)
            f_df = f_df[(f_df['날짜'] >= start) & (f_df['날짜'] <= end)]
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


# #6-3. [탭 3] 회원 관리 (모바일 최적화 한 줄 내비게이션) ㅋ
with tabs[2]:
    st.session_state.show_res_modal = False
    st.subheader("👥 회원 관리")


    # 💡 신규 등록 버튼 (상단 고정)
    if st.button("➕ 새 회원 등록", use_container_width=True): 
        st.session_state.clicked_date = None
        add_member_modal()


    st.divider()


    # 🔍 검색 및 표시 개수 설정
    search_col, size_col = st.columns([3, 1])
    s_m = search_col.text_input("👤 검색", key="mem_search_tab3")
    
    page_size_options = [10, 20, 50, "전체"]
    selected_size = size_col.selectbox("📄 표시 개수", options=page_size_options, index=0)


    if not df_m.empty:
        df_disp = df_m.copy()
        
        # 1. 검색 로직
        if s_m:
            df_disp = df_disp[df_disp['성함'].str.contains(s_m, na=False) | df_disp['연락처'].str.contains(s_m, na=False)]
        
        df_disp['연락처'] = df_disp['연락처'].apply(format_phone)
        total_rows = len(df_disp)


        # 2. 페이징 계산 (슬림 내비게이션 적용) ㅋ
        if "curr_page" not in st.session_state: st.session_state.curr_page = 1
        
        if selected_size == "전체":
            display_df = df_disp
        else:
            page_size = int(selected_size)
            total_pages = max((total_rows // page_size) + (1 if total_rows % page_size > 0 else 0), 1)
            
            # 💡 [모바일 최적화 한 줄 내비게이션]
            # 버튼 덩어리 대신 얇은 슬라이더나 숫자 입력기를 사용하여 한 줄로 고정 ㅋ
            st.write("")
            nav_col1, nav_col2 = st.columns([1, 4])
            
            # 페이지 직접 입력 (매우 작게 표시됨) ㅋ
            new_page = nav_col1.number_input(f"Page", min_value=1, max_value=total_pages, value=st.session_state.curr_page, step=1, key="nav_num")
            
            # 페이지 이동 가이드 ㅋ
            nav_col2.markdown(f" <br> <div style='font-size:14px; color:#666;'>총 **{total_pages}** 페이지 중 **{new_page}**pg (전체 {total_rows}명)</div>", unsafe_allow_html=True)
            
            if new_page != st.session_state.curr_page:
                st.session_state.curr_page = new_page
                st.rerun()


            start_idx = (st.session_state.curr_page - 1) * page_size
            display_df = df_disp.iloc[start_idx : start_idx + page_size]


        # 3. 데이터프레임 출력
        sel = st.dataframe(
            display_df, 
            use_container_width=True, 
            hide_index=True, 
            on_select="rerun", 
            selection_mode="single-row", 
            key="mem_table_mobile_v1"
        )


        # 4. 상세 정보 호출
        if sel.selection.rows:
            st.session_state.show_res_modal = False
            m_info = display_df.iloc[sel.selection.rows[0]]
            show_detail(m_info, df_s[df_s['성함'] == m_info['성함']])


    else:
        st.info("등록된 회원 정보가 없습니다. ㅋ")

        


# #6-4. [탭 4] 매출 통계 (페이징 및 시트 분리형 엑셀 다운로드 통합 버전) ㅋ
with tabs[3]:
    st.session_state.show_res_modal = False
    st.subheader("📊 매출 통계 및 데이터 추출")


    # 🔍 검색 및 표시 개수 설정 레이아웃 ㅋ
    search_col, size_col = st.columns([3, 1])
    s_s = search_col.text_input("🔍 매출 검색 (성함 또는 상품명)", key="sale_search_tab4_final")
    
    page_size_options = [10, 20, 50, "전체"]
    selected_size = size_col.selectbox("📄 표시 개수", options=page_size_options, index=0, key="sale_page_size_final")


    if not df_s.empty:
        df_disp = df_s.copy()
        
        # 1. 검색 필터링 ㅋ
        if s_s:
            df_disp = df_disp[df_disp['성함'].str.contains(s_s, na=False) | df_disp['상품명'].str.contains(s_s, na=False)]
        
        # 최신 매출이 위로 오게 정렬 ㅋ
        df_disp['날짜'] = pd.to_datetime(df_disp['날짜']).dt.date
        df_disp = df_disp.sort_values(by='날짜', ascending=False)
        total_rows = len(df_disp)


        # 2. 모바일 최적화 페이징 내비게이션 ㅋ
        if "sale_curr_page" not in st.session_state: st.session_state.sale_curr_page = 1
        
        if selected_size == "전체":
            display_df = df_disp
        else:
            page_size = int(selected_size)
            total_pages = max((total_rows // page_size) + (1 if total_rows % page_size > 0 else 0), 1)
            
            st.write("")
            nav_col1, nav_col2 = st.columns([1, 4])
            
            # 페이지 직접 입력 ㅋ
            new_page = nav_col1.number_input(f"Page  ", min_value=1, max_value=total_pages, value=st.session_state.sale_curr_page, step=1, key="sale_nav_num_final")
            
            # 정보 표시 ㅋ
            nav_col2.markdown(f" <br> <div style='font-size:14px; color:#666;'>총 **{total_pages}** 페이지 중 **{new_page}**pg (매출 {total_rows}건)</div>", unsafe_allow_html=True)
            
            if new_page != st.session_state.sale_curr_page:
                st.session_state.sale_curr_page = new_page
                st.rerun()

            start_idx = (st.session_state.sale_curr_page - 1) * page_size
            display_df = df_disp.iloc[start_idx : start_idx + page_size]


        # 3. 화면 데이터프레임 출력 ㅋ
        st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # 4. 매출 합계 (검색 결과 기준) ㅋ
        if st.session_state.user_role == "admin":
            total_rev = pd.to_numeric(df_disp['정산'].apply(lambda x: str(x).replace(',','')), errors='coerce').sum()
            st.metric("검색 결과 총 합계", f"{total_rev:,.0f}원")


        st.divider()


        # 5. [핵심] 엑셀 다운로드 로직 (회원명부/매출내역 시트 분리) ㅋ
        st.write("📥 **데이터 통합 내보내기**")
        
        try:
            import io
            output = io.BytesIO()
            
            # 💡 엑셀 엔진을 사용하여 파일 하나에 여러 시트 생성 ㅋ
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                # [시트 1] 전체 회원 명부 ㅋ
                df_m_export = df_m.copy()
                df_m_export['연락처'] = df_m_export['연락처'].apply(format_phone)
                df_m_export.to_excel(writer, index=False, sheet_name='1_회원명부')
                
                # [시트 2] 전체 매출 내역 (정렬된 상태로) ㅋ
                df_s_export = df_s.copy()
                df_s_export.to_excel(writer, index=False, sheet_name='2_일자별매출내역')
                
                # 엑셀 서식 살짝 입히기 ㅋ
                workbook = writer.book
                worksheet1 = writer.sheets['1_회원명부']
                worksheet2 = writer.sheets['2_일자별매출내역']
                header_format = workbook.add_format({'bold': True, 'bg_color': '#D7E4BC', 'border': 1})
            
            processed_data = output.getvalue()


            # 💡 최종 다운로드 버튼 ㅋ
            st.download_button(
                label="📁 [Excel] 회원정보 & 매출내역 통합본 다운로드",
                data=processed_data,
                file_name=f"K-View_통합데이터_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
                key="btn_excel_download_final"
            )
            st.caption("※ 엑셀 하단의 탭을 클릭하여 회원 명부와 매출 내역을 전환하며 확인하세요! ㅋ")
            
        except Exception as e:
            st.error(f"엑셀 생성 중 오류가 발생했습니다: {e}")


    else:
        st.info("데이터가 없어 엑셀을 추출할 수 없습니다. ㅋ")




# #6-5. [탭 5] 재고 관리 ㅋ
with tabs[4]:
    st.session_state.show_res_modal = False # 강제 종료 ㅋ
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
