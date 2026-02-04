import streamlit as st
import pandas as pd
import requests
import json
import time
import re
from datetime import datetime, timedelta
from streamlit_calendar import calendar

# 1. 페이지 설정 및 보안
st.set_page_config(page_title="Tinker-View Pro", layout="wide")

DEPLOY_URL = "https://script.google.com/macros/s/AKfycbwl55ojHpZtu5Ue2V3EOnq58po9Xc2UxrdlF7-_FtTIWweHikNrj8d1N3S334OLWXit/exec"
SPREADSHEET_ID = "1o704HhhIJrBCux7ibPdYDDq6Z00J9QoogZ2oq6Fjgfc"
READ_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/gviz/tq?tqx=out:csv&sheet="

PRODUCT_DATA = {"HP": 500000, "S1": 50000, "S2": 100000, "S3": 1000000, "S4": 9999999, "기타": 0}

# 로그인 유지
if "authenticated" not in st.session_state:
    st.session_state.authenticated = True if st.query_params.get("auth") == "true" else False

if not st.session_state.authenticated:
    st.title("🔐 Tinker-View 접속")
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
        "reservations": ["성함", "날짜", "상품명", "상담사", "기타"]
    }
    try:
        url = f"{READ_URL}{sheet_name}&t={int(time.time())}"
        data = pd.read_csv(url, dtype=object).fillna("")
        if not data.empty: data.columns = expected[sheet_name]
        return data
    except: return pd.DataFrame(columns=expected.get(sheet_name, []))

def manage_gsheet(sheet, row=None, action="add", key=None, extra=None):
    try:
        f_row = [f"'{str(v)}" for v in (row or [])]
        params = {"sheet": sheet, "values": json.dumps(f_row), "action": action, "key": key}
        if extra: params.update(extra)
        r = requests.get(DEPLOY_URL, params=params, timeout=15)
        return "Success" in r.text
    except: return False
    
# 3. 유틸리티 및 팝업
def format_phone(p):
    c = re.sub(r'\D', '', str(p)); return f"{c[:3]}-{c[3:7]}-{c[7:]}" if len(c) == 11 else c

def format_birth(b):
    c = re.sub(r'\D', '', str(b).split('.')[0]); return f"{c[:4]}.{c[4:6]}.{c[6:]}" if len(c) == 8 else c

# 📅 예약 등록 팝업 (회원 검색 및 날짜 보정 완료)
@st.dialog("📅 새 예약 등록")
def add_res_modal(clicked_date, m_list):
    # 💡 어떤 형식이 와도 안전하게 날짜/시간 추출
    try:
        # T를 기준으로 날짜와 시간 분리
        dt_parts = clicked_date.replace("Z", "").split("T")
        date_str = dt_parts[0]
        time_str = dt_parts[1][:5] # "10:00:00"이든 "10:00"이든 앞에서 5글자만!
        
        # 일단 기준 시간을 만들고
        base_dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
        
        # 🌏 시차 보정: 주간 클릭 시 9시간 밀리는 현상 해결 (+9시간)
        kor_dt = base_dt + timedelta(hours=9)
        
        fixed_date = kor_dt.date()
        fixed_time = kor_dt.time()
    except Exception as e:
        # 혹시라도 에러 나면 오늘 날짜/시간으로 비상 대피 ㅋ
        fixed_date = datetime.now().date()
        fixed_time = datetime.now().time()

    st.write(f"📅 선택된 시간: **{fixed_date} {fixed_time.strftime('%H:%M')}**")

    # --- 회원 검색 로직 ---
    search_q = st.text_input("👤 회원 검색", placeholder="성함 입력")
    filtered_members = m_list[m_list['성함'].str.contains(search_q, na=False)] if search_q else m_list
    name_options = ["선택하세요"] + filtered_members['성함'].tolist()
    name = st.selectbox(f"회원 선택", options=name_options, key="res_name_select")
    
    default_counselor = ""
    if name != "선택하세요":
        matched = m_list[m_list['성함'] == name]
        if not matched.empty: default_counselor = matched.iloc[0]['상담사']

    with st.form("res_real_form", clear_on_submit=True):
        res_date = st.date_input("예약 날짜", value=fixed_date)
        res_time = st.time_input("시간", value=fixed_time) # 클릭한 시간이 자동으로 들어감! ㅋ
        
        item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"])
        coun = st.text_input("상담사", value=default_counselor)
        etc = st.text_area("특이사항")
        
        if st.form_submit_button("✅ 예약 저장"):
            if name == "선택하세요":
                st.error("회원을 선택해 주세요!")
            else:
                if manage_gsheet("reservations", [name, res_date.strftime("%Y-%m-%d"), item, coun, f"[{res_time.strftime('%H:%M')}] {etc}"]):
                    st.cache_data.clear()
                    st.rerun()

@st.dialog("👤 회원 정보 및 매출 관리")
def show_detail(m_info, h_df):
    # ✨ 핵심: 팝업이 열릴 때마다 '선택된 아이템' 리스트를 완전히 비웁니다.
    if "pop_id" not in st.session_state or st.session_state.pop_id != m_info['성함']:
        st.session_state.sel_items = []
        st.session_state.pop_id = m_info['성함']

    t_v, t_s, t_e = st.tabs(["🔍 상세조회", "💰 매출등록", "✏️ 정보수정"])
    
    with t_v:
        st.write(f"### {m_info['성함']} 님 프로필")
        c1, c2 = st.columns(2)
        c1.write(f"**📞 연락처:** {format_phone(m_info['연락처'])}\n\n**🎂 생년:** {format_birth(m_info['생년월일'])}")
        c2.write(f"**🏠 주소:** {m_info['주소']}\n\n**👨‍🏫 담당:** {m_info['상담사']}")
        st.info(f"**📝 비고:** {m_info['비고(특이사항)']}")
        st.divider()
        if not h_df.empty:
            for i, r in h_df.iterrows():
                ci, cd = st.columns([8, 2])
                # ✨ 💰 {r['정산']}원 -> 💰 {r['수가']}원 으로 수정 완료! ㅋ
                ci.write(f"📅 {r['날짜']} | 📦 {r['상품명']} | 💰 **{r['수가']}원**")
                if cd.button("삭제", key=f"d_{i}"):
                    if manage_gsheet("schedules", action="delete_sales", key=m_info['성함'], extra={"date": r['날짜'], "item": r['상품명']}):
                        st.cache_data.clear(); st.rerun()
        else: st.write("내역 없음")

    with t_s:
        s_date = st.date_input("결제 날짜", datetime.now())
        
        # 1. 헤더와 초기화 버튼 영역 비율 조정 ([7, 3]으로 버튼 칸을 넓힘)
        c_head, c_reset = st.columns([7, 3])
        c_head.write("**상품 선택 (자동 합산)**")
        
        # 2. 버튼 너비를 칸에 꽉 채워(True) 좌우로 넉넉하게 만듦
        if c_reset.button("🔄 초기화", key="reset_items", use_container_width=True):
            st.session_state.sel_items = []
            st.rerun()
            
        cols = st.columns(3)
        pk = list(PRODUCT_DATA.keys())
        for idx, k in enumerate(pk):
            if cols[idx % 3].button(f"{k}\n({PRODUCT_DATA[k]:,}원)", key=f"pbtn_{k}"):
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
                    st.session_state.sel_items = []
                    st.cache_data.clear(); st.rerun()

    with t_e:
        with st.form("ef"):
            st.write("#### 회원 정보 수정")
            e_n = st.text_input("성함", value=m_info['성함'])
            e_p = st.text_input("연락처", value=m_info['연락처'])
            e_b = st.text_input("생년월일", value=m_info['생년월일'])
            e_a = st.text_input("주소", value=m_info['주소'])
            e_c = st.text_input("상담사", value=m_info['상담사'])
            e_m = st.text_area("비고", value=m_info['비고(특이사항)'])
            if st.form_submit_button("✅ 정보 수정 완료"):
                up_row = [m_info['순번'], e_n, e_p, e_b, m_info['성별'], e_a, m_info['최초방문일'], e_c, e_m]
                if manage_gsheet("members", up_row, action="update", key=m_info['성함']):
                    st.cache_data.clear(); st.rerun()

# 4. 메인 UI
df_m, df_s, df_r = load_data("members"), load_data("schedules"), load_data("reservations")
st.title("🛠️ Tinker-View Pro")

tabs = st.tabs(["📅 스케줄 달력", "📋 예약 관리", "👥 회원 관리", "📊 매출 현황"])

with tabs[0]:
    st.subheader("📅 스케줄 달력")
    
    if not df_r.empty:
        # 1. 달력 이벤트 데이터 생성
        events = []
        for _, r in df_r.iterrows():
            # 색상 지정 로직
            event_color = "#3D5AFE"
            if "상담" in str(r['상품명']): event_color = "#FF9100"
            elif "HP" in str(r['상품명']): event_color = "#00C853"
            elif "S" in str(r['상품명']): event_color = "#D500F9"
            
            # ✨ 중요: '기타' 열에 저장된 [10:00] 형태의 시간 정보를 추출
            # 주간 시간표(timeGrid)는 시간이 있어야 해당 칸에 표시됩니다. ㅋ
            res_time = "10:00" # 기본값
            time_match = re.search(r'\[(\d{2}:\d{2})\]', str(r['기타']))
            if time_match:
                res_time = time_match.group(1)
            
            events.append({
                "title": f"{r['성함']} ({r['상품명']})",
                "start": f"{r['날짜']}T{res_time}:00", # 날짜와 시간을 합쳐서 전달 ㅋ
                "allDay": False, # 주간 시간표 칸에 들어가려면 False여야 합니다 ㅋ
                "backgroundColor": event_color,
                "borderColor": event_color,
            })

        # 2. 달력 옵션 설정 (한글화 + 24시간제 + 근무시간)
        calendar_options = {
            "headerToolbar": {
                "left": "prev,next today",
                "center": "title",
                "right": "dayGridMonth,timeGridWeek"
            },
            "initialView": "dayGridMonth",
            "selectable": True,
            "locale": "ko",
            "buttonText": {
                "today": "오늘",
                "month": "월간",
                "week": "주간",
            },
            # ⏰ 시간 표시 설정 (24시간제 & 근무시간)
            "slotMinTime": "10:00:00", # 시작 시간 (오전 10시)
            "slotMaxTime": "18:00:00", # 종료 시간 (오후 6시)
            "slotLabelFormat": {
                "hour": "2-digit",
                "minute": "2-digit",
                "hour12": False # ✅ 오전/오후 표시 없이 깔끔하게 ㅋ
            },
            "eventTimeFormat": { # 이벤트 내 시간 표시도 24시간제
                "hour": "2-digit",
                "minute": "2-digit",
                "hour12": False
            },
            "allDaySlot": False,
        }
        
        # 3. 달력 위젯 호출
        state = calendar(
            events=events,
            options=calendar_options,
            key="calendar_main_v4" # 캐시 꼬임 방지를 위해 키 변경 ㅋ
        )

        # 4. 날짜 클릭 시 처리 (시차 보정 버전)
    if state.get("dateClick"):
        raw_date = str(state["dateClick"]["date"]) # 예: "2026-02-04T11:00:00Z"
        
        # 💡 T 뒤에 오는 시간을 확인 (시차 때문에 꼬인 시간 그대로 가져옴)
        # 보통 월간은 "T00:00:00" 혹은 시차 보정된 "T09:00:00", "T13:00:00" 등으로 옴
        # 주간은 클릭한 시간 그대로 옴
        
        # 시간 부분만 추출 (T 뒤의 8글자)
        clicked_time = raw_date.split("T")[1][:8] if "T" in raw_date else "00:00:00"
        
        # 1. 월간 클릭 차단: 시간이 정각(00시)이거나 특정 기본값이면 월간으로 간주
        if clicked_time == "00:00:00" or not "T" in raw_date:
            st.toast("예약 등록은 '주간' 탭에서 시간을 클릭해 주세요!", icon="📅")
        else:
            # 2. 주간 클릭: 시차 계산하지 말고 '보이는 글자 그대로' 전달!
            # 11:00 클릭 -> 서버에 02:00로 전달됨 -> 이걸 다시 11:00로 복원하는 마법 ㅋ
            
            # 주간 뷰에서는 클릭한 칸의 '정확한 시간'이 데이터에 포함되어 있습니다.
            # 이 데이터를 add_res_modal에 그대로 넘겨서 처리합니다.
            add_res_modal(raw_date, df_m)
            
with tabs[1]:
    st.dataframe(df_r, use_container_width=True, hide_index=True)

with tabs[2]: # 회원 관리 탭
    st.subheader("👥 회원 관리")
    # 최신 데이터를 다시 로드하여 1번이 있는지 확인
    df_m = load_data("members") 
    
    if not df_m.empty:
        df_disp = df_m.copy()
        df_disp['연락처'] = df_disp['연락처'].apply(format_phone)
        df_disp['생년월일'] = df_disp['생년월일'].apply(format_birth)
        
        # 💡 테스트용: 데이터 개수 확인 (배포 후 상단에 뜰 겁니다)
        st.write(f"현재 등록된 회원 수: {len(df_disp)}명")

        sel = st.dataframe(
            df_disp,
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="member_table_final_v3"
        )

        if sel.selection.rows:
            idx = sel.selection.rows[0]
            m_info = df_m.iloc[idx] # 0번 인덱스가 곧 1번 데이터입니다!
            show_detail(m_info, df_s[df_s['성함'] == m_info['성함']])
            
            # 팝업 후 선택 해제
            st.session_state["member_table_final_v3"]["selection"]["rows"] = []
    else:
        st.warning("회원 데이터가 없습니다. 구글 시트를 확인해주세요!")
        
with tabs[3]:
    if not df_s.empty:
        calc_df = df_s.copy()
        for c in ['수가', '특가', '정산']: 
            calc_df[c] = pd.to_numeric(calc_df[c].apply(lambda x: str(x).replace(',', '').replace('\'', '')), errors='coerce').fillna(0)
        st.dataframe(df_s, use_container_width=True, hide_index=True)
        st.metric("총 정산 합계", f"{calc_df['정산'].sum():,.0f}원")

if st.sidebar.button("로그아웃"): st.query_params.clear(); st.session_state.authenticated = False; st.rerun()
