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
    # ✨ 시트 구조 패치: '기타' 대신 '시간', '특이사항' 반영! ㅋ
    expected = {
        "members": ["순번", "성함", "연락처", "생년월일", "성별", "주소", "최초방문일", "상담사", "비고(특이사항)"],
        "schedules": ["성함", "날짜", "상품명", "상담사", "수가", "특가", "정산", "비고"],
        "reservations": ["성함", "날짜", "상품명", "상담사", "시간", "특이사항"] # ✅ 6칸 정확히 매칭!
    }
    try:
        url = f"{READ_URL}{sheet_name}&t={int(time.time())}"
        data = pd.read_csv(url, dtype=object).fillna("")
        if not data.empty:
            # 가져온 시트의 열 개수가 설정과 맞을 때 이름표를 새로 붙입니다 ㅋ
            if len(data.columns) == len(expected[sheet_name]):
                data.columns = expected[sheet_name]
        return data
    except:
        return pd.DataFrame(columns=expected.get(sheet_name, []))

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
        
        # --- ⏰ 시간 선택 드롭다운 (10:00 ~ 18:00 제한) ---
        # 1. 10시부터 18시까지 30분 단위 리스트 생성
        time_slots = []
        for hour in range(10, 19): # 10시부터 18시까지
            time_slots.append(f"{hour:02d}:00")
            if hour != 18: # 18:30은 제외하고 싶다면 조건 추가
                time_slots.append(f"{hour:02d}:30")
        
        # 2. 현재 클릭한 시간이 리스트에 있으면 해당 시간을 기본값으로, 없으면 10:00으로 설정
        click_time_str = fixed_time.strftime("%H:%M")
        if click_time_str not in time_slots:
            default_index = 0 # 10:00
        else:
            default_index = time_slots.index(click_time_str)
            
        res_time_str = st.selectbox("시간 선택 (10:00~18:00)", options=time_slots, index=default_index)
        # ----------------------------------------------

        item = st.selectbox("상품명", ["상담", "HP", "S1", "S2", "S3", "S4", "기타"])
        coun = st.text_input("상담사", value=default_counselor)
        etc = st.text_area("특이사항")
        
        if st.form_submit_button("✅ 예약 저장"):
            if name == "선택하세요":
                st.error("회원을 선택해 주세요!")
            else:
                # 저장할 때 res_time_str(문자열)을 그대로 사용하면 됩니다.
                if manage_gsheet("reservations", [name, res_date.strftime("%Y-%m-%d"), item, coun, f"[{res_time_str}] {etc}"]):
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

# ✨ 상단 타이틀 모바일 최적화 버전 ㅋ
st.markdown("""
    <style>
        .main-title {
            font-size: 26px !important;
            font-weight: 800 !important;
            color: #1E3A8A;
            margin-top: -20px;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
        }
    </style>
    <div class="main-title">
        ✨ Tinker-View
    </div>
""", unsafe_allow_html=True)

# 탭 이름에서도 Pro 느낌을 빼고 더 심플하게 갈 수도 있어요 ㅋ
tabs = st.tabs(["📅 달력", "📋 예약", "👥 회원", "📊 매출"])

with tabs[0]:
    st.subheader("📅 스케줄 달력")
    
    events = []
    if not df_r.empty:
        # 🧪 [디버깅] 데이터가 몇 건 있는지 확인용 (잘 나오면 나중에 지우세요 ㅋ)
        # st.caption(f"시스템이 읽어온 예약 수: {len(df_r)}건") 

        for _, r in df_r.iterrows():
            try:
                # 1. 색상 로직
                event_color = "#3D5AFE"
                p_name = str(r.get('상품명', ''))
                if "상담" in p_name: event_color = "#FF9100"
                elif "HP" in p_name: event_color = "#00C853"
                elif "S" in p_name: event_color = "#D500F9"
                
                # 2. 날짜 정제 (가장 까다로운 부분 ㅋ)
                # '2026-02-04' 형태인지 확인하고 점(.)이나 공백 제거
                res_date = str(r.get('날짜', '')).replace("'", "").replace(".", "-").strip()
                
                # 3. 시간 정제
                # 구글 시트에서 '10:00'이 '10:00:00'으로 올 수도 있고 '[10:00]'일 수도 있음 ㅋ
                res_time_raw = str(r.get('시간', '')).replace("'", "").strip()
                # 숫자와 콜론(:)만 남기기
                res_time = re.sub(r'[^0-9:]', '', res_time_raw)
                
                if ":" not in res_time:
                    res_time = "10:00"
                
                # HH:MM 형식 맞추기 (예: 9:00 -> 09:00)
                time_parts = res_time.split(":")
                hh = time_parts[0].zfill(2)
                mm = time_parts[1].zfill(2) if len(time_parts) > 1 else "00"
                res_time_final = f"{hh}:{mm}"

                # 4. 달력이 좋아하는 ISO 형식 완성 ("2026-02-04T10:00:00")
                start_iso = f"{res_date}T{res_time_final}:00"
                
                events.append({
                    "title": f"{r.get('성함', '무명')} ({p_name})",
                    "start": start_iso,
                    "allDay": False,
                    "backgroundColor": event_color,
                    "borderColor": event_color,
                    # 특이사항도 달력 이벤트 데이터에 슬쩍 넣어두기 ㅋ
                    "extendedProps": {"memo": r.get('특이사항', '')}
                })
            except Exception as e:
                # 특정 행에서 에러나면 무시하고 다음 행으로! ㅋ
                continue

    # 5. 달력 옵션 (변화 없음)
    calendar_options = {
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek"
        },
        "initialView": "dayGridMonth",
        "selectable": True,
        "locale": "ko",
        "buttonText": {"today": "오늘", "month": "월간", "week": "주간"},
        "slotMinTime": "10:00:00",
        "slotMaxTime": "18:00:00",
        "slotLabelFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False},
        "eventTimeFormat": {"hour": "2-digit", "minute": "2-digit", "hour12": False},
        "allDaySlot": False,
    }
    
    # 6. 달력 위젯 호출 (key를 바꿔서 완전히 새로 그리게 함 ㅋ)
    state = calendar(
        events=events, 
        options=calendar_options, 
        key="calendar_v12_final_fix"
    )

    # 7. 날짜 클릭 처리
    if state.get("dateClick"):
        raw_date = str(state["dateClick"]["date"])
        clicked_time = raw_date.split("T")[1][:8] if "T" in raw_date else "00:00:00"
        
        if clicked_time == "00:00:00" or not "T" in raw_date:
            st.toast("예약 등록은 '주간' 탭에서 시간을 클릭해 주세요!", icon="📅")
        else:
            add_res_modal(raw_date, df_m)
            
with tabs[1]:
    st.subheader("📋 전체 예약 내역 관리")

    if not df_r.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            date_range = st.date_input("날짜 범위 선택", [datetime.now().date(), datetime.now().date() + timedelta(days=7)], key="mgr_date_range")
        with col2:
            search_term = st.text_input("검색 (성함/상품명)", placeholder="검색어 입력...", key="mgr_search")
        with col3:
            sort_order = st.selectbox("정렬 기준", ["최신 날짜순", "오래된 날짜순", "시간순"], key="mgr_sort")

        filtered_df = df_r.copy()

        # 날짜 필터 적용
        if len(date_range) == 2:
            start_date, end_date = date_range
            filtered_df['날짜'] = pd.to_datetime(filtered_df['날짜']).dt.date
            filtered_df = filtered_df[(filtered_df['날짜'] >= start_date) & (filtered_df['날짜'] <= end_date)]

        # 검색 필터 적용
        if search_term:
            filtered_df = filtered_df[filtered_df['성함'].str.contains(search_term, na=False) | filtered_df['상품명'].str.contains(search_term, na=False)]

        # --- ⏰ 정렬 로직 (새로운 '시간' 컬럼 활용) ---
        if sort_order == "최신 날짜순":
            filtered_df = filtered_df.sort_values(by=['날짜', '시간'], ascending=[False, False])
        elif sort_order == "오래된 날짜순":
            filtered_df = filtered_df.sort_values(by=['날짜', '시간'], ascending=[True, True])
        else: # 시간순
            filtered_df = filtered_df.sort_values(by=['시간', '날짜'], ascending=[True, True])

        st.dataframe(filtered_df, use_container_width=True, hide_index=True)
        st.write(f"💡 총 **{len(filtered_df)}건**의 예약이 검색되었습니다.")
    else:
        st.info("등록된 예약 내역이 없습니다.")

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
