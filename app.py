import streamlit as st
import pandas as pd
import requests
import json
import time
import re
from datetime import datetime, timedelta
from streamlit_calendar import calendar

# 1. 페이지 설정 및 보안
st.set_page_config(page_title="K-View", layout="wide")

DEPLOY_URL = "https://script.google.com/macros/s/AKfycbyy-bnPp9gZvvOSlFUFsvkGcYaTrIoR4Pyg7h6-9iDPOvIvvKHP2iqX79VCtpRUMfUz/exec"
SPREADSHEET_ID = "1o704HhhIJrBCux7ibPdYDDq6Z00J9QoogZ2oq6Fjgfc"
READ_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet="

PRODUCT_DATA = {"HP": 500000, "S1": 50000, "S2": 100000, "S3": 1000000, "S4": 9999999, "기타": 0}

# 로그인 유지
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

# 2. 데이터 로드 및 시트 관리
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

def manage_gsheet(sheet, row=None, action="add", key=None, extra=None):
    try:
        f_row = []
        for v in (row or []):
            val = str(v).strip()
            
            # 💡 [핵심 로직] 
            # 1. 값이 비어있으면 그냥 빈값
            if not val:
                f_row.append("")
            # 2. '0'으로 시작하는 숫자(연락처 등)는 무조건 따옴표 붙임 (0 보존)
            elif val.isdigit() and val.startswith("0"):
                f_row.append(f"'{val}")
            # 3. 그 외의 순수 숫자(순번, 생년월일 등)는 따옴표 없이 숫자로 보냄
            elif val.isdigit():
                f_row.append(val)
            # 4. 문자가 섞인 경우 따옴표 붙여서 텍스트로 보호
            else:
                f_row.append(f"'{val}")
        
        params = {"sheet": sheet, "values": json.dumps(f_row), "action": action, "key": key}
        if extra: params.update(extra)
        
        r = requests.get(DEPLOY_URL, params=params, timeout=15)
        return "Success" in r.text
    except: 
        return False
    
# 3. 유틸리티 및 팝업
def format_phone(p):
    c = re.sub(r'\D', '', str(p)); return f"{c[:3]}-{c[3:7]}-{c[7:]}" if len(c) == 11 else c

def format_birth(b):
    c = re.sub(r'\D', '', str(b).split('.')[0]); return f"{c[:4]}.{c[4:6]}.{c[6:]}" if len(c) == 8 else c

# 👤 새 회원 등록 팝업
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

# 📅 예약 등록 팝업
@st.dialog("📅 새 예약 등록")
def add_res_modal(clicked_date, m_list):
    # 1. 시간 추출 및 시차 보정
    try:
        dt_parts = clicked_date.replace("Z", "").split("T")
        date_str = dt_parts[0]
        time_str = dt_parts[1][:5]
        base_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        kor_dt = base_dt + timedelta(hours=9)
        fixed_date, fixed_time = kor_dt.date(), kor_dt.time()
    except:
        fixed_date, fixed_time = datetime.now().date(), datetime.now().time()

    st.write(f"📅 선택된 시간: **{fixed_date} {fixed_time.strftime('%H:%M')}**")
    st.divider()

    # --- ✍️ [개선] 검색과 입력을 하나로! ---
    # 세션 상태를 이용해 선택된 이름을 관리합니다 ㅋ
    if "selected_member_name" not in st.session_state:
        st.session_state.selected_member_name = ""

    # 1. 회원 검색창
    search_q = st.text_input("🔍 회원 검색", placeholder="이름을 입력하면 목록이 나타납니다.", key="res_search_q")
    
    # 2. 검색 결과 드롭다운
    name_to_set = ""
    if search_q:
        filtered = m_list[m_list['성함'].str.contains(search_q, na=False)]['성함'].tolist()
        if filtered:
            selected_hint = st.selectbox("검색 결과 (선택 시 자동 입력) ㅋ", ["선택하세요"] + filtered, key="search_hint_select")
            if selected_hint != "선택하세요":
                st.session_state.selected_member_name = selected_hint # 선택한 이름을 세션에 저장!

    # 3. 최종 성함 칸 (직접 입력도 되고, 위에서 선택하면 자동으로 바뀜!)
    res_name = st.text_input(
        "👤 예약자 성함 (직접 수정 가능)", 
        value=st.session_state.selected_member_name, 
        placeholder="손님1 등 직접 입력도 가능합니다.",
        key="res_name_final_input"
    )

    # 상담사 자동 매칭
    default_counselor = ""
    if res_name:
        matched = m_list[m_list['성함'] == res_name]
        if not matched.empty:
            default_counselor = matched.iloc[0]['상담사']

    with st.form("res_real_form", clear_on_submit=True):
        res_date = st.date_input("예약 날짜", value=fixed_date)
        
        # 시간 선택
        time_slots = [f"{h:02d}:{m:02d}" for h in range(10, 19) for m in (0, 30)][:-1]
        click_time_str = fixed_time.strftime("%H:%M")
        default_idx = time_slots.index(click_time_str) if click_time_str in time_slots else 0
        res_time_str = st.selectbox("시간 선택", options=time_slots, index=default_idx)

        item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"])
        coun = st.text_input("상담사", value=default_counselor)
        etc = st.text_area("특이사항")
        
        if st.form_submit_button("✅ 예약 저장"):
            if not res_name:
                st.error("성함을 입력해 주세요!")
            else:
                if manage_gsheet("reservations", [res_name, res_date.strftime("%Y-%m-%d"), item, coun, res_time_str, etc]):
                    # 저장 성공 시 세션 초기화 ㅋ
                    st.session_state.selected_member_name = ""
                    st.cache_data.clear()
                    st.rerun()

@st.dialog("👤 회원 정보 및 매출 관리")
def show_detail(m_info, h_df):
    if "pop_id" not in st.session_state or st.session_state.pop_id != m_info['성함']:
        st.session_state.sel_items = []
        st.session_state.pop_id = m_info['성함']

    t_v, t_s, t_e = st.tabs(["🔍 상세조회", "💰 매출등록", "✏️ 정보수정"])
    
    with t_v:
        # 1. 👑 이름 강조 타이틀 (배경 빼고 깔끔하게)
        st.markdown(f"### 👑 <span style='color:#1E90FF;'>{m_info['성함']}</span> <span style='font-size:16px; color:#666;'>회원님 프로필</span>", unsafe_allow_html=True)
        
        # 2. 📋 핵심 정보 한 줄 요약 (metric 대신 깔끔한 텍스트로)
        st.markdown(f"""
            <div style="background-color:#f8f9fa; padding:10px; border-radius:5px; border-left:5px solid #1E90FF;">
                <b>🔢 순번:</b> {m_info['순번']}번 | 
                <b>🚻 성별:</b> {m_info['성별']} | 
                <b>🎂 생년:</b> {format_birth(m_info['생년월일'])} | 
                <b>📅 최초방문:</b> {m_info['최초방문일']}
            </div>
        """, unsafe_allow_html=True)
        
        st.write("") # 간격 조절

        # 3. 상세 정보
        col_l, col_r = st.columns(2)
        with col_l:
            st.write(f"**📞 연락처:** {format_phone(m_info['연락처'])}")
            st.write(f"**🏠 주소:** {m_info['주소']}")
        with col_r:
            st.write(f"**👨‍🏫 담당:** {m_info['상담사']}")
            # 방문일이 여기서도 보이면 좋겠죠 ㅋ
            st.write(f"**🗓️ 등록일:** {m_info['최초방문일']}")
            
        st.info(f"**📝 비고(특이사항):**\n\n{m_info['비고(특이사항)']}")
        
        st.divider()
        st.write("#### 💰 최근 매출 내역")
        if not h_df.empty:
            for i, r in h_df.iterrows():
                ci, cd = st.columns([8, 2])
                ci.write(f"📅 {r['날짜']} | 📦 {r['상품명']} | 💰 **{r['수가']}원**")
                if cd.button("삭제", key=f"d_{i}"):
                    if manage_gsheet("schedules", action="delete_sales", key=m_info['성함'], extra={"date": r['날짜'], "item": r['상품명']}):
                        st.cache_data.clear(); st.rerun()
        else: 
            st.write("내역 없음")

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
            e_v = c3.text_input("최초방문일", value=m_info['최초방문일']) # ✅ 최초방문일 추가!
            
            c4, c5 = st.columns(2)
            raw_p = c4.text_input("연락처", value=m_info['연락처'])
            e_p = re.sub(r'\D', '', raw_p) 
            
            raw_b = c5.text_input("생년월일", value=m_info['생년월일'])
            e_b = re.sub(r'\D', '', raw_b) 
            
            c6, c7 = st.columns([1, 3])
            gender_options = ["남자", "여자"]
            # 성별 매칭 (남/여 -> 남자/여자)
            curr_g = "남자" if "남" in m_info['성별'] else "여자"
            e_g = c6.selectbox("성별", options=gender_options, index=gender_options.index(curr_g))
            e_a = c7.text_input("주소", value=m_info['주소'])
            
            e_c = st.text_input("상담사", value=m_info['상담사'])
            e_m = st.text_area("비고", value=m_info['비고(특이사항)'])
            
            if st.form_submit_button("✅ 정보 수정 완료"):
                # 최초방문일(e_v)을 포함하여 시트 순서대로 저장!
                up_row = [e_no.strip(), e_n, e_p, e_b, e_g, e_a, e_v, e_c, e_m]
                
                if manage_gsheet("members", up_row, action="update", key=m_info['성함']):
                    st.success("정보가 완벽하게 수정되었습니다!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"수정 중 오류 발생: {e}")

# 4. 메인 UI
df_m, df_s, df_r = load_data("members"), load_data("schedules"), load_data("reservations")

st.markdown("""
    <style>
        .main-title { font-size: 26px !important; font-weight: 800 !important; color: #1E3A8A; margin-top: -20px; margin-bottom: 15px; display: flex; align-items: center; }
    </style>
    <div class="main-title">✨ K-View</div>
""", unsafe_allow_html=True)

tabs = st.tabs(["📅 달력", "📋 예약", "👥 회원", "📊 매출"])

with tabs[0]:
    st.subheader("📅 스케줄 달력")
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
                start_iso = f"{res_date}T{hh.zfill(2)}:{mm.zfill(2)}:00"
                
                events.append({
                    "title": f"{r['성함']} ({r['상품명']})", "start": start_iso, "allDay": False,
                    "backgroundColor": event_color, "borderColor": event_color,
                    "extendedProps": {"memo": r.get('특이사항', '')}
                })
            except: continue

    state = calendar(events=events, options={
        "headerToolbar": {"left": "prev,next today", "center": "title", "right": "dayGridMonth,timeGridWeek"},
        "initialView": "dayGridMonth", "selectable": True, "locale": "ko",
        "slotMinTime": "10:00:00", "slotMaxTime": "18:00:00", "allDaySlot": False,
    }, key="calendar_v13_final")

    if state.get("dateClick"):
        raw_date = str(state["dateClick"]["date"])
        if "T" in raw_date and raw_date.split("T")[1][:8] != "00:00:00": add_res_modal(raw_date, df_m)
        else: st.toast("예약 등록은 '주간' 탭에서 시간을 클릭해 주세요!", icon="📅")
            
with tabs[1]:
    st.subheader("📋 예약 내역 관리")

    if not df_r.empty:
        # --- 🔍 필터 영역 (상단 고정) ---
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

        # --- 🗑️ 선택 삭제 버튼 (선택 시에만 등장! ㅋ) ---
        # 💡 on_select="rerun"을 활용해 선택된 행 정보를 가져옵니다.
        sel_res = st.dataframe(
            f_df,
            use_container_width=True,
            hide_index=True,
            on_select="rerun", # 행 선택 시 즉시 반응 ㅋ
            selection_mode="single-row", # 깔끔하게 한 줄씩만!
            key="res_table_clean"
        )

        # 행이 선택되었을 때만 삭제 버튼 노출 ㅋ
        if sel_res.selection.rows:
            idx = sel_res.selection.rows[0]
            row = f_df.iloc[idx]
            
            st.warning(f"⚠️ **{row['성함']}** 님의 예약을 삭제하시겠습니까?")
            c1, c2 = st.columns([1, 4])
            if c1.button("🗑️ 즉시 삭제", type="primary", use_container_width=True):
                # GAS에 삭제 요청 (성함, 날짜, 시간 조합)
                if manage_gsheet("reservations", action="delete_res", key=row['성함'], extra={"date": row['날짜'], "time": row['시간']}):
                    st.toast("예약이 삭제되었습니다.", icon="🗑️")
                    st.cache_data.clear()
                    st.rerun()
            if c2.button("❌ 취소", use_container_width=True):
                st.rerun() # 선택 해제 효과 ㅋ

    else:
        st.info("등록된 예약 내역이 없습니다.")

with tabs[2]:
    st.subheader("👥 회원 관리")
    if st.button("➕ 새 회원 등록", use_container_width=True): add_member_modal()
    st.divider()
    search_m = st.text_input("👤 회원 검색 (성함 또는 연락처)", placeholder="검색어 입력...", key="m_search_main")
    
    df_m = load_data("members")
    if not df_m.empty:
        df_disp = df_m.copy()
        if search_m:
            df_disp = df_disp[df_disp['성함'].str.contains(search_m, na=False) | df_disp['연락처'].str.contains(search_m, na=False)]
        
        df_disp['연락처'] = df_disp['연락처'].apply(format_phone)
        df_disp['생년월일'] = df_disp['생년월일'].apply(format_birth)
        
        sel = st.dataframe(df_disp, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="member_table_v5")
        if sel.selection.rows:
            m_info = df_disp.iloc[sel.selection.rows[0]]
            show_detail(m_info, df_s[df_s['성함'] == m_info['성함']])
    else: st.warning("데이터 없음")
        
with tabs[3]:
    if not df_s.empty:
        calc_df = df_s.copy()
        for c in ['수가', '특가', '정산']: 
            calc_df[c] = pd.to_numeric(calc_df[c].apply(lambda x: str(x).replace(',', '')), errors='coerce').fillna(0)
        st.dataframe(df_s, use_container_width=True, hide_index=True)
        st.metric("총 정산 합계", f"{calc_df['정산'].sum():,.0f}원")

if st.sidebar.button("로그아웃"): st.query_params.clear(); st.session_state.authenticated = False; st.rerun()
