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

DEPLOY_URL = "https://script.google.com/macros/s/AKfycbyCQsVUvwEfA4zcjbURq3EiJpKvkJtSaINKHJEFCU5gnjITO01UgGLDNkqUNFCBCKpd/exec"
SPREADSHEET_ID = "1o704HhhIJrBCux7ibPdYDDq6Z00J9QoogZ2oq6Fjgfc"
READ_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet="

PRODUCT_DATA = {"HP": 500000, "S1": 50000, "S2": 100000, "S3": 1000000, "S4": 9999999, "기타": 0}



# #1-3. 관리자 인증 시스템 (보안)
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



# #2-2. 구글 시트 데이터 조작 (C.U.D - 추가, 수정, 삭제)
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


# #3-1. 텍스트 포맷팅 유틸리티 (연락처, 날짜 등)
def format_phone(p):
    c = re.sub(r'\D', '', str(p)); return f"{c[:3]}-{c[3:7]}-{c[7:]}" if len(c) == 11 else c

def format_birth(b):
    c = re.sub(r'\D', '', str(b))
    if len(c) == 8:
        return f"{c[:4]}.{c[4:6]}.{c[6:]}"
    return c



# #3-2. [팝업] 신규 회원 등록 폼
@st.dialog("👤 새 회원 등록")
def add_member_modal():
    with st.form("add_member_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        new_name = col1.text_input("성함 (필수)")
        new_phone = col2.text_input("연락처 (예: 01012345678)")
        
        col3, col4 = st.columns(2)
        new_birth = col3.text_input("생년월일 (예: 19900101)")
        new_gender = col4.selectbox("성별", ["남", "여"])
        
        new_addr = st.text_input("주소")
        new_coun = st.text_input("담당 상담사")
        new_memo = st.text_area("비고(특이사항)")
        
        if st.form_submit_button("✅ 회원 등록 완료"):
            if not new_name:
                st.error("성함을 입력해주세요!")
            else:
                new_row = ["", new_name, new_phone, new_birth, new_gender, new_addr, datetime.now().strftime("%Y-%m-%d"), new_coun, new_memo]
                if manage_gsheet("members", new_row, action="add"):
                    st.success(f"{new_name} 님이 등록되었습니다!")
                    st.cache_data.clear()
                    st.rerun()



# #3-3. [팝업] 신규 예약 등록 폼 (중복 클릭 방지 보완)
@st.dialog("📅 새 예약 등록")
def add_res_modal(clicked_date, m_list):
    # 팝업 열릴 때마다 초기화 로직
    if "last_clicked_date" not in st.session_state or st.session_state.last_clicked_date != clicked_date:
        st.session_state.res_name_input = ""
        st.session_state.last_clicked_date = clicked_date
        st.session_state.res_submitting = False  # 등록 중 상태 초기화 ㅋ

    # 시간 시차 보정
    try:
        dt_parts = clicked_date.replace("Z", "").split("T")
        date_str, time_str = dt_parts[0], dt_parts[1][:5]
        base_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        kor_dt = base_dt + timedelta(hours=9)
        fixed_date, fixed_time = kor_dt.date(), kor_dt.time()
    except:
        fixed_date, fixed_time = datetime.now().date(), datetime.now().time()

    st.write(f"📅 선택 시간: **{fixed_date} {fixed_time.strftime('%H:%M')}**")
    st.divider()

    # 1. 검색 영역
    search_q = st.text_input("🔍 회원 검색", placeholder="성함을 입력하면 목록이 나타납니다.", key="res_search_field")
    if search_q:
        filtered = m_list[m_list['성함'].str.contains(search_q, na=False)]['성함'].tolist()
        if filtered:
            sel_hint = st.selectbox("검색 결과 선택", ["선택하세요"] + filtered)
            if sel_hint != "선택하세요":
                st.session_state.res_name_input = sel_hint

    # 2. 실제 저장 폼 영역
    with st.form("res_real_form_final", clear_on_submit=True):
        res_name = st.text_input("👤 예약자 성함 (필수)", value=st.session_state.res_name_input)
        
        default_counselor = ""
        if res_name:
            matched = m_list[m_list['성함'] == res_name]
            if not matched.empty:
                default_counselor = matched.iloc[0]['상담사']

        res_date = st.date_input("예약 날짜", value=fixed_date)
        time_slots = [f"{h:02d}:{m:02d}" for h in range(10, 19) for m in (0, 30)][:-1]
        click_time_str = fixed_time.strftime("%H:%M")
        default_idx = time_slots.index(click_time_str) if click_time_str in time_slots else 0
        res_time_str = st.selectbox("시간 선택", options=time_slots, index=default_idx)

        item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"])
        coun = st.text_input("상담사", value=default_counselor)
        etc = st.text_area("특이사항")
        
        # 💡 [핵심] 등록 중일 때는 버튼 텍스트를 바꾸고 비활성화 느낌을 줍니다 ㅋ
        submit_label = "⏳ 등록 중..." if st.session_state.res_submitting else "✅ 예약 저장"
        
        if st.form_submit_button(submit_label):
            if not res_name:
                st.error("성함을 입력해 주세요!")
            elif not st.session_state.res_submitting:
                # 등록 상태로 변경 ㅋ
                st.session_state.res_submitting = True
                
                # 시각적으로 로딩 중임을 표시 ㅋ
                with st.spinner("구글 시트에 데이터를 기록하고 있습니다..."):
                    if manage_gsheet("reservations", [res_name, res_date.strftime("%Y-%m-%d"), item, coun, res_time_str, etc]):
                        st.session_state.res_name_input = ""
                        st.session_state.res_submitting = False
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("등록에 실패했습니다. 다시 시도해 주세요.")
                        st.session_state.res_submitting = False



# #3-4. [팝업] 회원 상세 정보 및 매출/수정 통합 관리 (키값 보강)
@st.dialog("👤 회원 정보")
def show_detail(m_info, h_df):
    t_v, t_s, t_e = st.tabs(["🔍 상세조회", "💰 매출등록", "✏️ 정보수정"])
    
    with t_v:
        st.write(f"### {m_info['성함']} 님")
        # 기존 상세 정보 디자인 생략 (대장님 코드 유지) ㅋ
        st.write(f"📞 {format_phone(m_info['연락처'])} | 🎂 {format_birth(m_info['생년월일'])}")
        st.divider()
        st.write("#### 💰 최근 매출 내역")
        if not h_df.empty:
            for i, r in h_df.iterrows():
                ci, cd = st.columns([8, 2])
                ci.write(f"📅 {r['날짜']} | 📦 {r['상품명']} | 💰 {r['수가']}원")
                # 고유 키값 부여로 튕김 방지 ㅋ
                if cd.button("삭제", key=f"del_sale_{m_info['성함']}_{i}"):
                    if manage_gsheet("schedules", action="delete_sales", key=m_info['성함'], extra={"date": r['날짜'], "item": r['상품명']}):
                        st.cache_data.clear(); st.rerun()

    with t_s:
        # 매출 등록 로직... ㅋ
        s_date = st.date_input("결제 날짜", datetime.now(), key=f"s_date_{m_info['성함']}")
        
        cols = st.columns(3)
        for i, k in enumerate(PRODUCT_DATA.keys()):
            # 버튼마다 성함과 인덱스를 키에 포함 ㅋ
            if cols[i % 3].button(f"{k}", key=f"p_btn_{m_info['성함']}_{i}"):
                st.session_state.sel_items.append({"n": k, "p": PRODUCT_DATA[k]})
                st.rerun()

        with st.form(key=f"sale_form_{m_info['성함']}"):
            f_item = st.text_input("상품명", value=", ".join([x['n'] for x in st.session_state.sel_items]))
            f_su = st.text_input("수가", value=str(sum([x['p'] for x in st.session_state.sel_items])))
            if st.form_submit_button("💰 매출 저장"):
                if manage_gsheet("schedules", [m_info['성함'], s_date.strftime('%Y-%m-%d'), f_item, m_info['상담사'], int(f_su), 0, 0, ""]):
                    st.session_state.sel_items = []; st.cache_data.clear(); st.rerun()



# #3-5. [팝업] 예약 정보 수정 폼
@st.dialog("✏️ 예약 수정")
def edit_res_modal(res_info):
    with st.form("edit_res_form"):
        st.write(f"### {res_info['성함']} 님 예약 수정")
        new_date = st.date_input("날짜", value=pd.to_datetime(res_info['날짜']).date())
        
        time_slots = [f"{h:02d}:{m:02d}" for h in range(10, 19) for m in (0, 30)][:-1]
        curr_time = str(res_info['시간']).strip()
        default_idx = time_slots.index(curr_time) if curr_time in time_slots else 0
        new_time = st.selectbox("시간", options=time_slots, index=default_idx)
        
        new_item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"], 
                               index=["상담", "HP", "S1", "S2", "S3", "S4", "기타"].index(res_info['상품명']))
        new_etc = st.text_area("특이사항", value=res_info['특이사항'])
        
        if st.form_submit_button("✅ 수정 완료"):
            # 수정을 위해 'update_res' 액션을 GAS에 보내도록 구성 (GAS 코드 수정 필요할 수 있음)
            if manage_gsheet("reservations", [res_info['성함'], new_date.strftime("%Y-%m-%d"), new_item, res_info['상담사'], new_time, new_etc], 
                            action="update_res", key=res_info['성함'], 
                            extra={"old_date": res_info['날짜'], "old_time": res_info['시간']}):
                st.success("수정되었습니다!")
                st.cache_data.clear()
                st.rerun()

                

# ==========================================
# #4. 메인 탭 UI 및 대시보드 영역
# ==========================================


# #4-1. 데이터 초기 로드 및 공통 스타일 적용
df_m, df_s, df_r = load_data("members"), load_data("schedules"), load_data("reservations")

st.markdown("""
    <style>
        .main-title { font-size: 26px !important; font-weight: 800 !important; color: #1E3A8A; margin-top: -20px; margin-bottom: 15px; display: flex; align-items: center; }
    </style>
    <div class="main-title">✨ K-View</div>
""", unsafe_allow_html=True)

tabs = st.tabs(["📅 달력", "📋 예약", "👥 회원", "📊 매출"])



# #4-2. [탭 1] 스케줄 달력 뷰 (모바일 키보드 튕김 완벽 방어 버전)


with tabs[0]:
    st.subheader("📅 스케줄 달력")


    # 💡 세션 상태로 등록창 열림 여부 관리 ㅋ
    if "res_open" not in st.session_state: st.session_state.res_open = False
    if "res_clicked_info" not in st.session_state: st.session_state.res_clicked_info = None


    # 이벤트 데이터 준비 ㅋ
    events = []
    if not df_r.empty:
        for _, r in df_r.iterrows():
            try:
                event_color = "#3D5AFE"
                if "상담" in str(r['상품명']): event_color = "#FF9100"
                elif "HP" in str(r['상품명']): event_color = "#00C853"
                elif "S" in str(r['상품명']): event_color = "#D500F9"
                
                res_date = str(r.get('날짜', '')).replace("'", "").replace(".", "-").strip()
                res_time = re.sub(r'[^0-9:]', '', str(r.get('시간', '10:00')))
                hh, mm = (res_time.split(":") + ["00"])[:2]
                events.append({
                    "title": f"{r['성함']} ({r['상품명']})", "start": f"{res_date}T{hh.zfill(2)}:{mm.zfill(2)}:00",
                    "backgroundColor": event_color, "borderColor": event_color
                })
            except: continue


    # 1. 달력 위젯 호출
    state = calendar(events=events, options={
        "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"},
        "initialView": "dayGridMonth", "selectable": True, "locale": "ko",
        "slotMinTime": "10:00:00", "slotMaxTime": "18:00:00", "allDaySlot": False,
    }, key="calendar_fixed_v2026")


    # 2. 날짜 클릭 감지 -> 세션 고정 ㅋ
    if state.get("dateClick"):
        raw_date = str(state["dateClick"]["date"])
        # 주간 탭에서 시간 클릭 시에만 작동 ㅋ
        if "T" in raw_date and raw_date.split("T")[1][:8] != "00:00:00":
            st.session_state.res_clicked_info = raw_date
            st.session_state.res_open = True
            st.rerun()


    # 3. 💡 [핵심] 달력 하단 고정 예약 등록창 (키보드 대응)
    if st.session_state.res_open and st.session_state.res_clicked_info:
        st.markdown("---")
        st.markdown(f"### ➕ 새 예약 등록")
        
        # 시간 보정 로직
        c_date = st.session_state.res_clicked_info
        try:
            dt_parts = c_date.replace("Z", "").split("T")
            d_str, t_str = dt_parts[0], dt_parts[1][:5]
            base_dt = datetime.strptime(f"{d_str} {t_str}", "%Y-%m-%d %H:%M")
            kor_dt = base_dt + timedelta(hours=9)
            f_date, f_time = kor_dt.date(), kor_dt.time()
        except:
            f_date, f_time = datetime.now().date(), datetime.now().time()


        # 검색 및 입력 (인라인 방식이라 키보드 내려가도 유지됨 ㅋ)
        s_name = st.text_input("🔍 회원 검색", placeholder="이름 입력 시 자동 매칭...", key="inline_res_search_final")
        matched_name = ""
        if s_name:
            filtered = df_m[df_m['성함'].str.contains(s_name, na=False)]['성함'].tolist()
            if filtered:
                sel_name = st.selectbox("회원 선택", ["직접 입력/선택"] + filtered, key="inline_res_sel_final")
                if sel_name != "직접 입력/선택": matched_name = sel_name


        # 실제 등록 폼
        with st.form("inline_res_form_fixed"):
            final_res_name = st.text_input("👤 예약자 성함", value=matched_name)
            res_d = st.date_input("날짜", value=f_date)
            
            t_slots = [f"{h:02d}:{m:02d}" for h in range(10, 19) for m in (0, 30)][:-1]
            t_idx = t_slots.index(f_time.strftime("%H:%M")) if f_time.strftime("%H:%M") in t_slots else 0
            res_t = st.selectbox("시간", options=t_slots, index=t_idx)


            res_item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"])
            res_etc = st.text_area("특이사항")


            col1, col2 = st.columns(2)
            if col1.form_submit_button("✅ 예약 저장"):
                if final_res_name:
                    if manage_gsheet("reservations", [final_res_name, res_d.strftime("%Y-%m-%d"), res_item, "", res_t, res_etc], action="add"):
                        st.session_state.res_open = False
                        st.cache_data.clear(); st.rerun()
                else: st.error("성함을 입력해주세요!")
            
            if col2.form_submit_button("❌ 닫기"):
                st.session_state.res_open = False
                st.rerun()



# #4-3. [탭 2] 예약 내역 관리 (필터, 정렬, 수정, 삭제)
with tabs[1]:
    st.subheader("📋 예약 내역 관리")


    if not df_r.empty:
        # --- 🔍 필터 영역 ---
        col1, col2, col3 = st.columns(3)
        date_range = col1.date_input("날짜 범위", [datetime.now().date(), datetime.now().date() + timedelta(days=7)], key="mgr_d_clean")
        search_term = col2.text_input("검색 (성함/상품명)", key="mgr_s_clean")
        sort_order = col3.selectbox("정렬", ["최신 날짜순", "오래된 날짜순", "시간순"], key="mgr_o_clean")


        # --- ⚙️ 필터링 로직 ---
        f_df = df_r.copy()
        if len(date_range) == 2:
            f_df['날짜'] = pd.to_datetime(f_df['날짜']).dt.date
            f_df = f_df[(f_df['날짜'] >= date_range[0]) & (f_df['날짜'] <= date_range[1])]
        if search_term:
            f_df = f_df[f_df['성함'].str.contains(search_term, na=False) | f_df['상품명'].str.contains(search_term, na=False)]
        
        asc = [False, False] if sort_order == "최신 날짜순" else [True, True]
        f_df = f_df.sort_values(by=['날짜', '시간'] if sort_order != "시간순" else ['시간', '날짜'], ascending=asc)


        # --- 📊 예약 데이터 테이블 ---
        sel_res = st.dataframe(
            f_df, use_container_width=True, hide_index=True, on_select="rerun",
            selection_mode="single-row", key="res_table_clean"
        )


        # --- ⚙️ 수정/삭제 액션 영역 ---
        if sel_res.selection.rows:
            idx = sel_res.selection.rows[0]
            row = f_df.iloc[idx]
            
            st.markdown(f"**📍 선택된 예약:** `{row['날짜']}` `{row['시간']}` | **{row['성함']}** 님 ({row['상품명']})")
            
            # 버튼 레이아웃: 수정과 삭제를 나란히 ㅋ
            btn_col1, btn_col2, btn_spacer = st.columns([1, 1, 3])
            
            # 1. 수정 버튼
            if btn_col1.button("✏️ 예약 수정", use_container_width=True):
                # 이전에 만든 #3-5 [팝업] 예약 정보 수정 폼 호출 ㅋ
                edit_res_modal(row) 
                
            # 2. 삭제 버튼
            if btn_col2.button("🗑️ 즉시 삭제", type="primary", use_container_width=True):
                # GAS에 삭제 요청 (성함, 날짜, 시간 조합)
                if manage_gsheet("reservations", action="delete_res", key=row['성함'], extra={"date": row['날짜'], "time": row['시간']}):
                    st.toast(f"{row['성함']} 님의 예약이 삭제되었습니다.", icon="🗑️")
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("삭제에 실패했습니다. 관리자에게 문의하세요.")

    else:
        st.info("등록된 예약 내역이 없습니다.")



# #4-4. [탭 3] 회원 관리 (키패드 활성화/화면 리사이즈 대응 고정식)


with tabs[2]:
    st.subheader("👥 회원 관리")


    # 💡 팝업 상태를 유지하기 위한 세션 스위치
    if "m_detail_open" not in st.session_state: st.session_state.m_detail_open = False
    if "m_detail_data" not in st.session_state: st.session_state.m_detail_data = None


    if st.button("➕ 새 회원 등록", use_container_width=True, key="m_add_btn_final"): 
        add_member_modal() 
    st.divider()


    # 검색창
    search_m = st.text_input("👤 회원 검색", placeholder="이름 또는 연락처 입력...", key="m_search_input_final")


    df_m = load_data("members")
    if not df_m.empty:
        df_disp = df_m.copy()
        if search_m:
            df_disp = df_disp[df_disp['성함'].str.contains(search_m, na=False) | df_disp['연락처'].str.contains(search_m, na=False)]


        # 포맷팅
        df_disp['연락처'] = df_disp['연락처'].apply(format_phone)
        df_disp['생년월일'] = df_disp['생년월일'].apply(format_birth)


        # 1. 메인 명단 테이블 (선택 시 즉시 세션 고정)
        sel = st.dataframe(
            df_disp, use_container_width=True, hide_index=True, 
            on_select="rerun", selection_mode="single-row", key="m_table_final_resilient"
        )


        # 행 선택 시 데이터 저장 및 뷰어 활성화 ㅋ
        if sel.selection.rows:
            st.session_state.m_detail_data = df_disp.iloc[sel.selection.rows[0]]
            st.session_state.m_detail_open = True


        # 2. 💡 [핵심] 키패드가 닫혀도 사라지지 않는 인라인 상세창
        if st.session_state.m_detail_open and st.session_state.m_detail_data is not None:
            m = st.session_state.m_detail_data
            
            st.markdown("---")
            st.success(f"🔍 **{m['성함']}** 님 정보")


            # 탭 구성 (조회, 매출, 수정)
            m_tabs = st.tabs(["📋 상세정보", "💰 매출등록", "✏️ 수정"])


            with m_tabs[0]: # 상세조회 ㅋ
                st.write(f"**순번:** {m['순번']} | **성별:** {m['성별']}")
                st.write(f"**연락처:** {m['연락처']} | **생일:** {m['생년월일']}")
                st.write(f"**주소:** {m['주소'] if m['주소'] else '-'}")
                st.info(f"📝 **비고:** {m['비고(특이사항)']}")


                # 매출 내역
                h_df = df_s[df_s['성함'] == m['성함']]
                if not h_df.empty:
                    st.write("**💰 최근 매출**")
                    for i, r in h_df.iterrows():
                        c_msg, c_del = st.columns([8, 2])
                        c_msg.write(f"📅 {r['날짜']} | {r['상품명']} | {int(r['수가']):,}원")
                        if c_del.button("삭제", key=f"in_del_{m['성함']}_{i}"):
                            if manage_gsheet("schedules", action="delete_sales", key=m['성함'], extra={"date": r['날짜'], "item": r['상품명']}):
                                st.cache_data.clear(); st.rerun()


            with m_tabs[1]: # 매출등록 ㅋ
                # 팝업이 아니므로 키패드가 내려가도 이 입력창들은 그대로 유지됩니다 ㅋ
                s_date = st.date_input("결제일", datetime.now(), key=f"in_sdate_{m['성함']}")
                
                # 상품 선택 버튼
                st.write("**📦 상품**")
                p_cols = st.columns(3)
                for i, (k, v) in enumerate(PRODUCT_DATA.items()):
                    if p_cols[i%3].button(f"{k}", key=f"in_pbtn_{m['성함']}_{i}"):
                        st.session_state.sel_items.append({"n": k, "p": v})
                        st.rerun()


                with st.form(key=f"in_sale_form_{m['성함']}"):
                    f_item = st.text_input("상품명", value=", ".join([x['n'] for x in st.session_state.sel_items]))
                    f_su = st.text_input("금액", value=str(sum([x['p'] for x in st.session_state.sel_items])))
                    if st.form_submit_button("💰 매출 저장"):
                        if manage_gsheet("schedules", [m['성함'], s_date.strftime('%Y-%m-%d'), f_item, m['상담사'], int(f_su), 0, 0, ""], action="add"):
                            st.session_state.sel_items = []; st.cache_data.clear(); st.rerun()


            with m_tabs[2]: # 정보수정 ㅋ
                with st.form(key=f"in_edit_form_{m['성함']}"):
                    e_p = st.text_input("연락처", value=m['연락처'])
                    e_a = st.text_input("주소", value=m['주소'])
                    e_m = st.text_area("비고", value=m['비고(특이사항)'])
                    if st.form_submit_button("✅ 수정 완료"):
                        up_row = [m['순번'], m['성함'], e_p, m['생년월일'], m['성별'], e_a, m['최초방문일'], m['상담사'], e_m]
                        if manage_gsheet("members", up_row, action="update", key=m['성함']):
                            st.cache_data.clear(); st.rerun()


            # 닫기 버튼을 눌러야만 상세창이 사라집니다 ㅋ
            if st.button("❌ 상세창 닫기", use_container_width=True, key="in_close_btn"):
                st.session_state.m_detail_open = False
                st.rerun()


    else:
        st.warning("데이터가 없습니다.")

        

# #4-5. [탭 4] 매출 통계 및 로그아웃
with tabs[3]:
    if not df_s.empty:
        calc_df = df_s.copy()
        for c in ['수가', '특가', '정산']: 
            calc_df[c] = pd.to_numeric(calc_df[c].apply(lambda x: str(x).replace(',', '')), errors='coerce').fillna(0)
        st.dataframe(df_s, use_container_width=True, hide_index=True)
        st.metric("총 정산 합계", f"{calc_df['정산'].sum():,.0f}원")

if st.sidebar.button("로그아웃"): 
    st.query_params.clear(); st.session_state.authenticated = False; st.rerun()
