from flask import Flask, render_template, request, redirect, url_for
import numpy as np
import pandas as pd
import os
from datetime import datetime, timedelta, date
import pytz
import pandas_market_calendars as mcal
import traceback
import webbrowser
import threading
import subprocess

app = Flask(__name__)

@app.errorhandler(Exception)
def handle_exception(e):
    print("[ERROR]", e)
    traceback.print_exc()
    return "🚨 에러가 발생했습니다. 잠시 후 다시 시도해주세요.", 500

def get_latest_us_trading_day():
    nyse = mcal.get_calendar("NYSE")
    now = datetime.now(pytz.timezone("America/New_York"))
    kor_now = datetime.now(pytz.timezone("Asia/Seoul"))
    today = now.date()
    kor_today = kor_now.date()
    schedule = nyse.schedule(start_date=today - timedelta(days=10), end_date=today)
    trading_days = schedule.index.date
    latest_trading_day = max([d for d in trading_days if d <= today])
    return kor_today.strftime("%Y-%m-%d"), latest_trading_day.strftime("%Y-%m-%d")

def load_data():
    today, us_last_day = get_latest_us_trading_day()
    filename = f"예측데이터/({today})예측.csv"
    filename_news = f"뉴스데이터/({today})뉴스.csv"
    if not os.path.exists(filename) or not os.path.exists(filename_news):
        return pd.DataFrame(), pd.DataFrame()
    df = pd.read_csv(filename)
    df_news = pd.read_csv(filename_news)
    return df, df_news
def load_news():
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    today = now_kst.strftime("%Y-%m-%d")
    filename = f"뉴스_요약데이터/({today})뉴스_요약.csv"
    if not os.path.exists(filename):
        return pd.DataFrame()
    df = pd.read_csv(filename)
    df = df[["회사","제목","URL","본문","날짜"]]
    return df
def us_trading_calendar():
    import pandas as pd
    from datetime import datetime, timedelta
    import pytz
    import pandas_market_calendars as mcal

    # 1. 오늘 날짜(한국시간 기준 → 미국 동부로 변환)
    kor_now = datetime.now(pytz.timezone("Asia/Seoul"))
    tday = kor_now.astimezone(pytz.timezone("America/New_York")).date()

    # 2. 한 달 전 ~ 한 달 후 범위
    start_date = tday - timedelta(days=30)
    end_date = tday + timedelta(days=30)

    # 3. NYSE 거래일 스케줄
    nyse = mcal.get_calendar("NYSE")
    schedule = nyse.schedule(start_date=start_date, end_date=end_date)
    trading_days = set(schedule.index.date)

    # 4. 달력 데이터프레임 생성 (시간 제거)
    date_range = pd.date_range(start=start_date, end=end_date)
    calender = pd.DataFrame({"날짜": date_range.date})  # .date로 시간 제거
    calender["요일"] = pd.to_datetime(calender["날짜"]).dt.strftime("%a")
    calender["거래여부"] = calender["날짜"].apply(
        lambda d: "🟢 거래일" if d in trading_days else "🔴 휴장"
    )

    # 5. 오늘이면 True, 아니면 False 컬럼 추가
    calender["is_today"] = calender["날짜"] == tday

    return calender

def get_next_us_trading_day_kst_from(date_str):
    """한국 날짜 기준 date_str 포함 이후의 가장 가까운 미국 거래일"""
    date_dt = datetime.strptime(date_str, "%Y-%m-%d").date()
    nyse = mcal.get_calendar("NYSE")
    # 최소한 15일 후까지 탐색
    schedule = nyse.schedule(start_date=date_dt, end_date=date_dt + timedelta(days=15))
    for d in schedule.index.date:
        if d > date_dt:
            return d.strftime("%Y-%m-%d")
    return None

def get_recommend(df, df_news):
    try:
        df_trimmed = df[["종목", "상승확률"]].copy()
        news_trimmed = df_news[["종목", "감정점수"]].copy()
        merged = pd.merge(df_trimmed, news_trimmed, on="종목", how="inner")
        merged["상승확률"] = pd.to_numeric(merged["상승확률"], errors="coerce").fillna(0.0)
        merged["감정점수"] = pd.to_numeric(merged["감정점수"], errors="coerce").fillna(0.0)
        merged["감정점수"] = ((merged["감정점수"] + 1) / 2) * 100
        merged["종합점수"] = merged["상승확률"] + merged["감정점수"]
        top = merged.sort_values("종합점수", ascending=False)
        return top[["종목", "상승확률", "감정점수", "종합점수"]].reset_index(drop=True)
    except Exception as e:
        return pd.DataFrame()
@app.route('/start')
def start():
    return render_template("base.html")

# 홈, 뉴스, 데이터, 고객센터 등 메인탭
@app.route('/')
def home():
    tab = request.args.get('tab', 'home')
    return render_template('home.html', tab=tab)

# 주식탭 및 섭탭
@app.route('/index')
def index():
    df, df_news = load_data()
    tab = request.args.get('tab', 'stock')
    subtab = request.args.get('subtab', 'company')
    recommended = None
    message = None
    companies = []
    selected = None
    row = pd.DataFrame()
    checked = request.args.getlist("favorites")

    if not df.empty and not df_news.empty:
        companies = sorted(df["종목"].tolist())
        selected = request.args.get('company', companies[0] if companies else None)

    if tab == 'stock':
        if subtab == 'company':
            if selected:
                row = df[df["종목"] == selected] if not df.empty else pd.DataFrame()
            return render_template('index.html', tab=tab, subtab=subtab, companies=companies, selected=selected, row=row, checked=checked)
        elif subtab == 'news':
            if selected:
                row = df_news[df_news["종목"] == selected].copy() if not df_news.empty else pd.DataFrame()
                if not row.empty:
                    row["감정점수"] = ((row["감정점수"] + 1) / 2) * 100
            return render_template('index.html', tab=tab, subtab=subtab, companies=companies, selected=selected, row=row, checked=checked)
        elif subtab == 'recommend':
            recommended = get_recommend(df, df_news)
            companies_sorted = checked + [c for c in companies if c not in checked]
            return render_template('index.html', tab=tab, subtab=subtab, recommended=recommended, companies=companies_sorted, checked=checked)
        else:
            message = "알 수 없는 섭탭입니다."
            return render_template('index.html', tab=tab, subtab=subtab, message=message)
    else:
        # 주식 외의 탭은 home 라우트로 리다이렉트
        return redirect(url_for('home', tab=tab))

    return render_template('index.html', tab=tab, message="알 수 없는 요청입니다.")
@app.route('/news')
def news():
    df_news = load_news()  # 반드시 괄호 필요!!
    companies = sorted(df_news['회사'].dropna().unique().tolist())
    selected_company = request.args.get('company', companies[0] if companies else None)

    if selected_company:
        filtered_news = df_news[df_news['회사'] == selected_company]
    else:
        filtered_news = pd.DataFrame()

    return render_template(
        'news.html',
        tab='news',
        companies=companies,
        selected_company=selected_company,
        news=filtered_news
    )
# 기타 라우트 예시 (추가 필요시)
@app.route('/info', methods=['GET', 'POST'])
def info():
    info_tabs = ["거래일 정보", "데이터 검색", "정보2"]
    selected_info_tab = request.args.get("info_tab", info_tabs[0])
    info_subtab = request.args.get("info_subtab", "날짜로 검색하기")  # 🔥 하위탭 추가
    calender = None
    merged = None
    message = None
    companies = []
    selected_date = ""
    selected_company = ""
    accuracy_message = None
    from datetime import datetime, timedelta, date
    min_date = date(2025,5,26).strftime("%Y-%m-%d")
    max_date = (datetime.today()).strftime("%Y-%m-%d")

    if selected_info_tab == "거래일 정보":
        calender = us_trading_calendar()

    elif selected_info_tab == "데이터 검색":
        if request.method == "POST":
            form_type = request.form.get("form_type")
            selected_date = request.form.get("selected_date", "")
            selected_company = request.form.get("company", "")

            try:
                # 날짜 검색 처리
                if form_type == "date_search" and selected_date:
                    path1 = f"예측데이터/({selected_date})예측.csv"
                    path2 = f"뉴스데이터/({selected_date})뉴스.csv"
                    검증날짜 = get_next_us_trading_day_kst_from(selected_date)
                    print(검증날짜)
                    path3 = f"검증데이터/({검증날짜})검증.csv"
                    
                    df1 = pd.read_csv(path1)
                    df2 = pd.read_csv(path2)
                    if df1.empty or df2.empty:
                        message = "해당 날짜의 데이터가 비어 있습니다."
                    else:
                        merged = pd.merge(df1, df2, on="종목", how="inner")
                        try:
                            df3 = pd.read_csv(path3)
                            df3 = df3.rename(columns={"상승여부": "실제상승여부"})
                            merged = pd.merge(merged, df3, on="종목", how="left")
                        except FileNotFoundError:
                            message = "🔍 검증 데이터는 없습니다."
                        
                        if not merged.empty:
                            merged["상승확률"] = pd.to_numeric(merged["상승확률"], errors="coerce").fillna(0.0)
                            merged["감정점수"] = pd.to_numeric(merged["감정점수"], errors="coerce").fillna(0.0)
                            merged["종합점수"] = 0.8 * merged["상승확률"] + merged["감정점수"]

                            merged["예측상승"] = np.where(merged["상승확률"] > 50, "상승", "하락")
                            merged["종합상승"] = np.where(merged["종합점수"] > 50, "상승", "하락")

                            merged = merged.sort_values(by="종합점수", ascending=False).reset_index(drop=True)
                            companies = sorted(merged["종목"].drop_duplicates().tolist())

                            # 검증 데이터가 있을 경우만 정확도 계산
                            if "실제상승여부" in merged.columns:
                                예측_상승 = merged[merged["예측상승"] == "상승"]
                                정답_상승 = 예측_상승[예측_상승["실제상승여부"] == "상승"].shape[0]
                                전체_예측_상승 = 예측_상승.shape[0]

                                종합_상승 = merged[merged["종합상승"] == "상승"]
                                종합_정답_상승 = 종합_상승[종합_상승["실제상승여부"] == "상승"].shape[0]
                                전체_종합_상승 = 종합_상승.shape[0]

                                if 전체_예측_상승 > 0:
                                    예측상승정확도 = 정답_상승 / 전체_예측_상승
                                    종합상승정확도 = 종합_정답_상승 / 전체_종합_상승
                                    accuracy_message = f"📈 예측이 '상승'인 종목 중 실제로도 상승한 비율: {예측상승정확도:.4f}    종합예측이 '상승'인 종목 중 실제로도 상승한 비율: {종합상승정확도:.4f}"
                                else:
                                    accuracy_message = "예측이 '상승'인 종목이 없습니다."
                                                

                # 회사 검색 처리 (오늘 날짜 기준)
                elif form_type == "company_search" and selected_company:
                    today = datetime.today().strftime("%Y-%m-%d")
                    path1 = f"예측데이터/({today})예측.csv"
                    path2 = f"뉴스데이터/({today})뉴스.csv"
                    path3 = f"검증데이터/({today})검증.csv"
                    df1 = pd.read_csv(path1)
                    df2 = pd.read_csv(path2)
                    merged = pd.merge(df1, df2, on="종목", how="inner")
                    merged["상승확률"] = pd.to_numeric(merged["상승확률"], errors="coerce").fillna(0.0)
                    merged["감정점수"] = pd.to_numeric(merged["감정점수"], errors="coerce").fillna(0.0)
                    merged["종합점수"] = merged["상승확률"] + merged["감정점수"]
                    companies = sorted(merged["종목"].drop_duplicates().tolist())
                    merged = merged[merged["종목"] == selected_company]
                    try:
                        df3 = pd.read_csv(path3)
                        df3 = df3[["종목", "상승여부"]]
                        merged = pd.merge(merged, df3, on="종목", how="left")
                    except FileNotFoundError:
                        message = "🔍 검증 데이터는 없습니다."

            except FileNotFoundError:
                message = "❌ 데이터 파일이 없습니다."
            

    return render_template(
        "info.html",
        info_tabs=info_tabs,
        selected_info_tab=selected_info_tab,
        info_subtab=info_subtab,  
        calender=calender,
        merged=merged,
        message=message,
        selected_date=selected_date,
        selected_company=selected_company,
        companies=companies,
        accuracy_message=accuracy_message,
        min_date=min_date,
        max_date=max_date
    )

@app.route('/support')
def support():
    return render_template("support.html")

@app.route('/shutdown')
def shutdown():
    func = request.environ.get('werkzeug.server.shutdown')
    func()
    return "서버가 종료되었습니다. 창을 닫아주세요."

# Flask 실행
if __name__ == '__main__':
    def open_browser():
        url = "http://127.0.0.1:5001/start"
        chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        subprocess.Popen([chrome_path, '--start-fullscreen', url])
    import threading
    threading.Timer(1, open_browser).start()
    app.run(host='127.0.0.1', port=5001, debug=True, use_reloader=True)
