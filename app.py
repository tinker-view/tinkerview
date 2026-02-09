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

DEPLOY_URL = "https://script.google.com/macros/s/AKfycbxK_qwgL2BPZHWuCMfTa7clW1qfL_ipHAVg_dOdV3NoTHeCRe5oTFAwkqMBP8E0AxcX/exec"
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



# #3-3. [팝업] 신규 예약 등록 폼 (시차 보정 & 중복 방지 완벽 반영)
@st.dialog("📅 새 예약 등록")
def add_res_modal(clicked_date, m_list):
    # 💡 1. 팝업 열릴 때마다 초기화 로직 (날짜 바뀌면 입력값 리셋)
    if "last_clicked_date" not in st.session_state or st.session_state.last_clicked_date != clicked_date:
        st.session_state.res_name_input = ""
        st.session_state.last_clicked_date = clicked_date
        st.session_state.res_submitting = False  # 등록 상태 초기화

    # 💡 2. 한국 시간 시차 보정 (이거 누락되면 안 됨!)
    try:
        dt_parts = clicked_date.replace("Z", "").split("T")
        date_str, time_str = dt_parts[0], dt_parts[1][:5]
        base_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        kor_dt = base_dt + timedelta(hours=9) # 한국 시차 +9시간 적용 ㅋ
        fixed_date, fixed_time = kor_dt.date(), kor_dt.time()
    except:
        fixed_date, fixed_time = datetime.now().date(), datetime.now().time()

    st.write(f"📅 선택 시간: **{fixed_date} {fixed_time.strftime('%H:%M')}**")
    st.divider()

    # 💡 3. 회원 검색 및 자동 매칭 영역
    search_q = st.text_input("🔍 회원 검색", placeholder="성함을 입력하면 목록이 나타납니다.", key="res_search_field")
    if search_q:
        filtered = m_list[m_list['성함'].str.contains(search_q, na=False)]['성함'].tolist()
        if filtered:
            sel_hint = st.selectbox("검색 결과 선택", ["선택하세요"] + filtered)
            if sel_hint != "선택하세요":
                st.session_state.res_name_input = sel_hint

    # 💡 4. 실제 저장 폼 영역
    with st.form("res_real_form_final", clear_on_submit=True):
        res_name = st.text_input("👤 예약자 성함 (필수)", value=st.session_state.res_name_input)
        
        # 이름 입력 시 기존 상담사 자동 매칭 로직 유지 ㅋ
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
        
        # 💡 5. 중복 클릭 방지 버튼 (등록 중일 때 잠금) ㅋ
        submit_label = "⏳ 등록 중..." if st.session_state.res_submitting else "✅ 예약 저장"
        
        if st.form_submit_button(submit_label):
            if not res_name:
                st.error("성함을 입력해 주세요!")
            elif not st.session_state.res_submitting:
                st.session_state.res_submitting = True # 중복 클릭 방지 ON ㅋ
                
                with st.spinner("구글 시트에 데이터를 기록하고 있습니다..."):
                    # 데이터 저장 (manage_gsheet 호출)
                    if manage_gsheet("reservations", [res_name, res_date.strftime("%Y-%m-%d"), item, coun, res_time_str, etc]):
                        # 💡 성공 시 모바일 팝업 유지 스위치 해제 및 세션 초기화
                        st.session_state.show_res_modal = False # 4-2용 스위치 ㅋ
                        st.session_state.res_name_input = ""
                        st.session_state.res_submitting = False
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("등록에 실패했습니다. 다시 시도해 주세요.")
                        st.session_state.res_submitting = False



# #3-4. [팝업] 회원 상세 정보 및 매출/수정 통합 관리
@st.dialog("👤 회원 정보 및 매출 관리")
def show_detail(m_info, h_df):
    if "pop_id" not in st.session_state or st.session_state.pop_id != m_info['성함']:
        st.session_state.sel_items = []
        st.session_state.pop_id = m_info['성함']

    t_v, t_s, t_e = st.tabs(["🔍 상세조회", "💰 매출등록", "✏️ 정보수정"])
    
    with t_v:
        st.markdown(f"""
            <div style="background-color:#1E90FF; padding:12px; border-radius:8px; margin-bottom:20px; text-align:center;">
                <h3 style="margin:0; color:white;">👑 {m_info['성함']} <span style="font-size:14px; opacity:0.8;">회원님 상세 정보</span></h3>
            </div>
        """, unsafe_allow_html=True)

        st.markdown(f"""
            <div style="background-color:#ffffff; padding:20px; border-radius:10px; border:1px solid #e1e4e8; box-shadow: 0 2px 4px rgba(0,0,0,0.05);">
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">No.</span>
                    <b style="font-size:18px; color:#333;">{m_info['순번']}번</b>
                </div>
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">성함</span>
                    <b style="font-size:18px; color:#333;">{m_info['성함']}</b>
                </div>
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">연락처</span>
                    <b style="font-size:18px; color:#333;">{format_phone(m_info['연락처'])}</b>
                </div>
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">생년월일</span>
                    <b style="font-size:18px; color:#333;">{format_birth(m_info['생년월일'])}</b>
                </div>
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">주소</span>
                    <b style="font-size:16px; color:#333;">{m_info['주소'] if m_info['주소'] else '-'}</b>
                </div>
                <div style="margin-bottom:12px; border-bottom:1px solid #f0f2f5; padding-bottom:8px;">
                    <span style="color:#888; font-size:13px; display:block;">담당 상담사</span>
                    <b style="font-size:16px; color:#333;">{m_info['상담사']}</b>
                </div>
                <div style="margin-bottom:5px;">
                    <span style="color:#888; font-size:13px; display:block;">최초방문일</span>
                    <b style="font-size:16px; color:#333;">{m_info['최초방문일']}</b>
                </div>
            </div>
        """, unsafe_allow_html=True)
        
        st.write("") 
        st.markdown(f"📝 **비고(특이사항)**")
        st.info(m_info['비고(특이사항)'] if m_info['비고(특이사항)'] else "내용 없음")
        
        st.divider()
        st.write("#### 💰 최근 매출 내역")
        if not h_df.empty:
            for i, r in h_df.iterrows():
                ci, cd = st.columns([8, 2])
                ci.write(f"📅 {r['날짜']} | 📦 {r['상품명']} | 💰 **{r['수가']}원**")
                if cd.button("삭제", key=f"d_{i}"):
                    if manage_gsheet("schedules", action="delete_sales", key=m_info['성함'], extra={"date": r['날짜'], "item": r['상품명']}):
                        st.cache_data.clear(); st.rerun()
        else: st.write("내역 없음")

    with t_s:
        s_date = st.date_input("결제 날짜", datetime.now())
        c_head, c_reset = st.columns([7, 3])
        c_head.write("**상품 선택 (자동 합산)**")
        if c_reset.button("🔄 초기화", key="reset_items", use_container_width=True):
            st.session_state.sel_items = []; st.rerun()
            
        cols = st.columns(3)
        for k in PRODUCT_DATA.keys():
            if cols[list(PRODUCT_DATA.keys()).index(k) % 3].button(f"{k}\n({PRODUCT_DATA[k]:,}원)", key=f"pbtn_{k}"):
                st.session_state.sel_items.append({"n": k, "p": PRODUCT_DATA[k]})
        
        calc_total = sum([x['p'] for x in st.session_state.sel_items])
        with st.form("sale_f"):
            f_item = st.text_input("상품명", value=", ".join([x['n'] for x in st.session_state.sel_items]))
            f_coun = st.text_input("상담사", value=m_info['상담사'])
            c1, c2, c3 = st.columns(3)
            v_su = c1.text_input("수가", value=str(calc_total))
            v_te = c2.text_input("특가", value="0")
            v_ju = c3.text_input("정산", value="0")
            f_memo = st.text_area("매출 비고", placeholder="특이사항 입력", height=100)
            if st.form_submit_button("💰 매출 저장"):
                vs, vt, vj = int(re.sub(r'\D', '', v_su or "0")), int(re.sub(r'\D', '', v_te or "0")), int(re.sub(r'\D', '', v_ju or "0"))
                if manage_gsheet("schedules", [m_info['성함'], s_date.strftime('%Y-%m-%d'), f_item, f_coun, vs, vt, vj, f_memo]):
                    st.session_state.sel_items = []; st.cache_data.clear(); st.rerun()

    with t_e:
        with st.form("ef"):
            st.write("#### ⚙️ 회원 정보 수정")
            c1, c2, c3 = st.columns([1, 2, 2])
            e_no = c1.text_input("순번", value=str(m_info['순번']))
            e_n = c2.text_input("성함", value=m_info['성함'])
            e_v = c3.text_input("최초방문일", value=m_info['최초방문일'])
            
            c4, c5 = st.columns(2)
            e_p = re.sub(r'\D', '', c4.text_input("연락처", value=m_info['연락처']))
            e_b = re.sub(r'\D', '', c5.text_input("생년월일", value=m_info['생년월일']))
            
            c6, c7 = st.columns([1, 3])
            g_opt = ["남자", "여자"]
            curr_g = "남자" if "남" in str(m_info['성별']) else "여자"
            e_g = c6.selectbox("성별", options=g_opt, index=g_opt.index(curr_g))
            e_a = c7.text_input("주소", value=m_info['주소'])
            
            e_c = st.text_input("상담사", value=m_info['상담사'])
            e_m = st.text_area("비고", value=m_info['비고(특이사항)'])
            
            if st.form_submit_button("✅ 정보 수정 완료"):
                clean_v = re.sub(r'[^0-9.-]', '', e_v)
                up_row = [e_no.strip(), e_n, e_p, e_b, e_g, e_a, clean_v, e_c, e_m]
                if manage_gsheet("members", up_row, action="update", key=m_info['성함']):
                    st.cache_data.clear(); st.rerun()

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
# #4. 메인 탭 UI 및 대시보드 영역 (데이터 연동 보강 버전)
# ==========================================

# #4-1. 데이터 로드 및 상단 레이아웃 설정 ㅋ
try:
    df_m = load_data("members")
    df_s = load_data("schedules")
    df_r = load_data("reservations")
    # 💡 stocks 시트 로드 (캐시 문제 방지를 위해 로직 보강 ㅋ)
    df_stock = load_data("stocks")
except:
    df_stock = None

# 💡 실시간 재고 계산 함수 (예외 처리 강화형 ㅋ)
def get_stock_val(item_name):
    if df_stock is None or df_stock.empty:
        return 0
    try:
        # 컬럼명 공백 제거 후 '항목' 매칭 ㅋ
        temp_df = df_stock.copy()
        temp_df.columns = temp_df.columns.str.strip()
        row = temp_df[temp_df['항목'].astype(str).str.strip() == item_name]
        if not row.empty:
            val = pd.to_numeric(row['현재고'].values[0], errors='coerce')
            return int(val) if not pd.isna(val) else 0
    except:
        return 0
    return 0

# 상단 바 스타일 및 재고 현황판 ㅋ
st.markdown(f"""
    <style>
        [data-testid="stHeader"], header {{ visibility: hidden !important; height: 0 !important; }}
        .top-bar {{
            display: flex; justify-content: space-between; align-items: center;
            margin-top: -45px; margin-bottom: 15px; padding: 0 5px;
        }}
        .main-title {{ font-size: 22px !important; font-weight: 800 !important; color: #1E3A8A; }}
        .stock-badge {{
            font-size: 13px !important; font-weight: 700 !important;
            color: #ef4444; background: #fee2e2; padding: 4px 10px;
            border-radius: 8px; border: 1px solid #fecaca;
        }}
        /* 달력 공통 스타일 ㅋ */
        .fc-event-main {{ display: flex !important; align-items: center !important; justify-content: center !important; padding: 2px !important; }}
        .fc-event-title {{ font-weight: 800 !important; color: #ffffff !important; text-align: center !important; }}
        @media screen and (max-width: 600px) {{
            .fc-event-title {{ font-size: 12px !important; white-space: nowrap !important; }}
            .fc-event-time {{ display: none !important; }}
            .fc-day-sun {{ width: 3% !important; background-color: #fcfcfc !important; }}
        }}
        @media screen and (min-width: 601px) {{ .fc-event-title {{ font-size: 13px !important; white-space: normal !important; }} }}
        .fc .fc-timegrid-slot {{ height: 55px !important; }}
    </style>
    
    <div class="top-bar">
        <div class="main-title">✨ K-View</div>
        <div class="stock-badge">📦 HP: {get_stock_val("HP")} | S3: {get_stock_val("S3")}</div>
    </div>
""", unsafe_allow_html=True)

# 💡 탭 구성
tabs = st.tabs(["📅 달력", "📋 예약", "👥 회원", "📊 매출", "📦 재고"])

# #4-2. [탭 1] 스케줄 달력 뷰
with tabs[0]:
    if "show_res_modal" not in st.session_state: st.session_state.show_res_modal = False
    if "clicked_res_info" not in st.session_state: st.session_state.clicked_res_info = None
    events = []
    if not df_r.empty:
        for _, r in df_r.iterrows():
            try:
                res_date = str(r.get('날짜', '')).replace("'", "").replace(".", "-").strip()
                res_time = re.sub(r'[^0-9:]', '', str(r.get('시간', '10:00')))
                display_title = f"{r['성함']} ({r['상품명']})"
                events.append({"title": display_title, "start": f"{res_date}T{res_time}:00", "backgroundColor": "#3D5AFE", "borderColor": "#3D5AFE"})
            except: continue
    cal_opt = {
        "headerToolbar": {"left": "prev,next", "center": "title", "right": "dayGridMonth,timeGridWeek"},
        "initialView": "timeGridWeek", "selectable": True, "locale": "ko", "allDaySlot": False,
        "slotMinTime": "10:00:00", "slotMaxTime": "19:00:00", "height": "auto", "expandRows": True,
        "slotLabelFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False},
        "views": {"timeGridWeek": {"dayHeaderFormat": {"weekday": "short", "day": "numeric"}}, "dayGridMonth": {"dayHeaderFormat": {"weekday": "short"}}},
        "displayEventTime": True, "firstDay": 1, "hiddenDays": [0]
    }
    state = calendar(events=events, options=cal_opt, key="kview_integrated_cal")
    if state.get("callback") == "dateClick":
        raw_date = str(state["dateClick"]["date"])
        if "T" in raw_date and raw_date.split("T")[1][:8] != "00:00:00":
            if st.session_state.clicked_res_info != raw_date:
                st.session_state.clicked_res_info = raw_date; st.session_state.show_res_modal = True; st.rerun()
    elif state.get("callback") and state.get("callback") != "dateClick": st.session_state.show_res_modal = False
    if st.session_state.show_res_modal and st.session_state.clicked_res_info: add_res_modal(st.session_state.clicked_res_info, df_m)

# #4-3. [탭 2] 예약 내역 관리
with tabs[1]:
    st.subheader("📋 예약 내역 관리")
    if not df_r.empty:
        c1, c2, c3 = st.columns(3)
        date_range = c1.date_input("날짜 범위", [datetime.now().date(), datetime.now().date() + timedelta(days=7)])
        search_term = c2.text_input("검색 (성함/상품명)")
        sort_order = c3.selectbox("정렬", ["최신 날짜순", "오래된 날짜순", "시간순"])
        f_df = df_r.copy()
        if len(date_range) == 2:
            f_df['날짜'] = pd.to_datetime(f_df['날짜']).dt.date
            f_df = f_df[(f_df['날짜'] >= date_range[0]) & (f_df['날짜'] <= date_range[1])]
        if search_term: f_df = f_df[f_df['성함'].str.contains(search_term, na=False) | f_df['상품명'].str.contains(search_term, na=False)]
        asc = [False, False] if sort_order == "최신 날짜순" else [True, True]
        f_df = f_df.sort_values(by=['날짜', '시간'] if sort_order != "시간순" else ['시간', '날짜'], ascending=asc)
        sel_res = st.dataframe(f_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        if sel_res.selection.rows:
            row = f_df.iloc[sel_res.selection.rows[0]]
            st.markdown(f"**📍 선택:** `{row['날짜']} {row['시간']}` | **{row['성함']}** ({row['상품명']})")
            b1, b2, _ = st.columns([1, 1, 3])
            if b1.button("✏️ 수정"): edit_res_modal(row)
            if b2.button("🗑️ 삭제", type="primary"):
                if manage_gsheet("reservations", action="delete_res", key=row['성함'], extra={"date": row['날짜'], "time": row['시간']}): st.cache_data.clear(); st.rerun()
    else: st.info("예약 내역이 없습니다.")

# #4-4. [탭 3] 회원 관리
with tabs[2]:
    st.subheader("👥 회원 관리")
    if st.button("➕ 새 회원 등록", use_container_width=True): add_member_modal()
    st.divider(); search_m = st.text_input("👤 회원 검색", placeholder="성함 또는 연락처 입력...")
    if not df_m.empty:
        df_disp = df_m.copy()
        if search_m: df_disp = df_disp[df_disp['성함'].str.contains(search_m, na=False) | df_disp['연락처'].str.contains(search_m, na=False)]
        df_disp['연락처'] = df_disp['연락처'].apply(format_phone)
        sel = st.dataframe(df_disp, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
        if sel.selection.rows:
            m_info = df_disp.iloc[sel.selection.rows[0]]
            show_detail(m_info, df_s[df_s['성함'] == m_info['성함']])
    else: st.warning("데이터 없음")

# #4-5. [탭 4] 매출 통계
with tabs[3]:
    st.subheader("📊 매출 통계")
    if not df_s.empty:
        calc_df = df_s.copy()
        for c in ['수가', '특가', '정산']: calc_df[c] = pd.to_numeric(calc_df[c].apply(lambda x: str(x).replace(',', '')), errors='coerce').fillna(0)
        st.dataframe(df_s, use_container_width=True, hide_index=True)
        st.metric("총 정산 합계", f"{calc_df['정산'].sum():,.0f}원")

# #4-6. [탭 5] 재고 관리 (연동 보강 완료! ㅋ)
with tabs[4]:
    st.subheader("📦 필수 재고 관리")
    col1, col2 = st.columns(2)
    items = ["HP", "S3"]
    for i, item in enumerate(items):
        with [col1, col2][i % 2]:
            current = get_stock_val(item)
            st.metric(f"{item} 현재고", f"{current}개")
            new_qty = st.number_input(f"{item} 증감량 (+/-)", value=0, key=f"adj_{item}")
            if st.button(f"{item} 반영", key=f"btn_{item}"):
                if manage_gsheet("stocks", action="update_stock", key=item, extra={"new_total": str(current + new_qty)}):
                    st.success(f"{item} 반영 완료!"); st.cache_data.clear(); st.rerun()

    st.divider(); st.write("📋 **전체 재고 현황**")
    if df_stock is not None and not df_stock.empty:
        st.dataframe(df_stock, use_container_width=True, hide_index=True)
    else:
        st.warning("⚠️ 'stocks' 시트 연결 확인이 필요합니다!")
        if st.button("🔄 데이터 강제 새로고침"): st.cache_data.clear(); st.rerun()

if st.sidebar.button("로그아웃"): st.query_params.clear(); st.session_state.authenticated = False; st.rerun()
