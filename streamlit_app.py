import base64
import hashlib
import hmac
import json
import re
import secrets as pysecrets
from datetime import datetime

import requests
import streamlit as st
import yfinance as yf
import pandas as pd

# ============================================================
# 設定
# ============================================================
st.set_page_config(page_title="AI Smart Trader", layout="wide")

# 公開リポジトリ（コード・管理者の watchlist.json / LINE と連動）
MAIN_REPO = "yuuma0822rin0809-hub/ai-fund"
MAIN_WATCHLIST_RAW = f"https://raw.githubusercontent.com/{MAIN_REPO}/main/watchlist.json"

# 非公開リポジトリ（ユーザー一覧・各人の銘柄リスト）
DATA_REPO = "yuuma0822rin0809-hub/ai-fund-data"
USERS_PATH = "users.json"


def secret(name: str) -> str:
    try:
        return str(st.secrets[name])
    except Exception:
        return ""


# ============================================================
# GitHub（非公開データリポジトリ）読み書き
# ============================================================
def gh_headers() -> dict:
    token = secret("DATA_REPO_TOKEN")
    if not token:
        raise RuntimeError("DATA_REPO_TOKEN が Secrets に設定されていません。")
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}


def gh_read(path: str, fallback):
    """非公開リポジトリの JSON を読む。無ければ fallback と sha=None を返す。"""
    url = f"https://api.github.com/repos/{DATA_REPO}/contents/{path}?ref=main"
    res = requests.get(url, headers=gh_headers(), timeout=15)
    if res.status_code == 404:
        return json.loads(json.dumps(fallback)), None
    if res.status_code != 200:
        raise RuntimeError(f"{path} を読めませんでした（{res.status_code}）")
    meta = res.json()
    text = base64.b64decode(meta["content"]).decode("utf-8")
    return json.loads(text), meta["sha"]


def gh_write(path: str, data, sha, message: str):
    url = f"https://api.github.com/repos/{DATA_REPO}/contents/{path}"
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    payload = {
        "message": message,
        "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        "branch": "main",
    }
    if sha:
        payload["sha"] = sha
    res = requests.put(url, headers=gh_headers(), json=payload, timeout=15)
    if res.status_code >= 300:
        raise RuntimeError(f"{path} を保存できませんでした（{res.status_code}）")


def load_users():
    data, sha = gh_read(USERS_PATH, {"users": {}})
    data.setdefault("users", {})
    return data, sha


def save_users(data, sha, message):
    gh_write(USERS_PATH, data, sha, message)


def user_watchlist_path(user_id: str) -> str:
    return f"users/{user_id}/watchlist.json"


# ============================================================
# パスワード（元の文字は保存しない。ハッシュだけ保存）
# ============================================================
def make_hash(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 120000).hex()


def check_password(password: str, salt: str, expected: str) -> bool:
    return hmac.compare_digest(make_hash(password, salt), expected)


# ============================================================
# 銘柄名・コード
# ============================================================
def currency_symbol(code: str) -> str:
    return "¥" if code.upper().endswith(".T") else "$"


def normalize_code(text: str) -> str:
    """LINE と同じルール：4桁の数字（285A のような英数字も）なら .T を自動で付ける。"""
    code = (text or "").strip().upper()
    code = "".join(chr(ord(c) - 0xFEE0) if "０" <= c <= "９" or "Ａ" <= c <= "Ｚ" else c for c in code)
    if re.fullmatch(r"\d{4}", code) or re.fullmatch(r"\d{3}[A-Z]", code):
        code += ".T"
    return code


@st.cache_data(ttl=60, show_spinner=False)
def load_main_watchlist() -> dict:
    """管理者の watchlist.json（LINE と連動）を GitHub から読む。"""
    try:
        res = requests.get(MAIN_WATCHLIST_RAW, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return {"tickers": data.get("tickers", []) or [], "names": data.get("names", {}) or {}}
    except Exception:
        pass
    return {"tickers": [], "names": {}}


@st.cache_data(ttl=86400, show_spinner=False)
def yahoo_name(code: str) -> str:
    """Yahoo!ファイナンス（日本版）のページタイトルから銘柄名を取る。日本株・米国株どちらも可。"""
    try:
        res = requests.get(
            f"https://finance.yahoo.co.jp/quote/{code}",
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            timeout=8,
        )
        if res.status_code != 200:
            return ""
        m = re.search(r"<title>([^<]+)</title>", res.text)
        if not m or "【" not in m.group(1):
            return ""
        name = m.group(1).split("【")[0].replace("(株)", "").replace("株式会社", "").strip()
        return name if 0 < len(name) <= 24 else ""
    except Exception:
        return ""


def lookup_name(code: str, names=None) -> str:
    if names and names.get(code):
        return names[code]
    main_names = load_main_watchlist()["names"]
    if main_names.get(code):
        return main_names[code]
    return yahoo_name(code)


def display_name(code: str, names=None) -> str:
    name = lookup_name(code, names)
    return f"{name}（{code}）" if name else code


# ============================================================
# 株価データ・指標
# ============================================================
@st.cache_data(ttl=300, show_spinner=False)
def fetch_history(code: str, term: str) -> pd.DataFrame:
    df = yf.Ticker(code).history(period=term, auto_adjust=True)
    if df is None or df.empty:
        return pd.DataFrame()
    return df.dropna(subset=["Close"])


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["MA20"] = out["Close"].rolling(window=20).mean()
    out["MA200"] = out["Close"].rolling(window=200).mean()
    delta = out["Close"].diff()
    gain = delta.clip(lower=0).rolling(window=14).mean()
    loss = (-delta.clip(upper=0)).rolling(window=14).mean()
    rs = gain / loss.replace(0, pd.NA)
    out["RSI"] = 100 - (100 / (1 + rs))
    return out


# ============================================================
# ログイン状態
# ============================================================
def current_user():
    return st.session_state.get("user")


def logout(message: str = ""):
    for key in ["user", "data", "ticker", "name", "last_pick"]:
        st.session_state.pop(key, None)
    if message:
        st.session_state["flash"] = message
    st.rerun()


def enforce_status():
    """ログイン中でも、管理者が利用停止にしたら次の操作から見られなくする。"""
    user = current_user()
    if not user or user["role"] == "admin":
        return
    try:
        users, _ = load_users()
    except Exception:
        return
    rec = users["users"].get(user["id"])
    if not rec or rec.get("status") != "active":
        logout("利用停止中です。管理者にお問い合わせください。")


def try_login(user_id: str, password: str):
    user_id = user_id.strip()
    admin_id = secret("ADMIN_ID")
    admin_pw = secret("ADMIN_PASSWORD")
    if admin_id and user_id == admin_id:
        if admin_pw and hmac.compare_digest(password, admin_pw):
            st.session_state.user = {"id": admin_id, "name": "管理者", "role": "admin"}
            st.rerun()
        return "ID またはパスワードが違います。"

    users, _ = load_users()
    rec = users["users"].get(user_id)
    if not rec or not check_password(password, rec["salt"], rec["hash"]):
        return "ID またはパスワードが違います。"
    if rec["status"] == "pending":
        return "承認待ちです。管理者の承認が完了するとログインできます。"
    if rec["status"] == "stopped":
        return "利用停止中です。管理者にお問い合わせください。"
    st.session_state.user = {"id": user_id, "name": rec["name"], "role": "user"}
    st.rerun()


def register(user_id: str, name: str, password: str, confirm: str):
    user_id = user_id.strip()
    name = name.strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{3,20}", user_id):
        return "ID は半角の英数字（アンダーバー可）3〜20文字で入力してください。"
    if not name:
        return "表示名を入力してください。"
    if len(password) < 6:
        return "パスワードは6文字以上にしてください。"
    if password != confirm:
        return "パスワード（確認）が一致しません。"
    if user_id == secret("ADMIN_ID"):
        return "この ID は使えません。"

    users, sha = load_users()
    if user_id in users["users"]:
        return "この ID はすでに使われています。"
    salt = pysecrets.token_hex(16)
    users["users"][user_id] = {
        "name": name,
        "salt": salt,
        "hash": make_hash(password, salt),
        "status": "pending",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    save_users(users, sha, f"register {user_id}")
    return None


# ============================================================
# 画面：ログイン前
# ============================================================
def render_auth():
    st.title("🎯 AI Smart Trader")
    if st.session_state.get("flash"):
        st.warning(st.session_state.pop("flash"))

    if not secret("DATA_REPO_TOKEN") or not secret("ADMIN_ID") or not secret("ADMIN_PASSWORD"):
        st.error("初期設定が終わっていません。Streamlit Cloud の Secrets に DATA_REPO_TOKEN / ADMIN_ID / ADMIN_PASSWORD を設定してください。")
        return

    tab_login, tab_signup = st.tabs(["🔑 ログイン", "📝 新規登録"])

    with tab_login:
        with st.form("login_form"):
            uid = st.text_input("ID")
            pw = st.text_input("パスワード", type="password")
            if st.form_submit_button("ログイン", use_container_width=True):
                try:
                    err = try_login(uid, pw)
                except Exception as e:
                    err = f"エラーが起きました：{e}"
                if err:
                    st.error(err)

    with tab_signup:
        st.caption("登録後、管理者が承認するとログインできるようになります。")
        with st.form("signup_form"):
            uid = st.text_input("ID（半角英数字 3〜20文字）")
            name = st.text_input("表示名（ニックネーム）")
            pw = st.text_input("パスワード（6文字以上）", type="password")
            pw2 = st.text_input("パスワード（確認）", type="password")
            if st.form_submit_button("登録を申請する", use_container_width=True):
                try:
                    err = register(uid, name, pw, pw2)
                except Exception as e:
                    err = f"エラーが起きました：{e}"
                if err:
                    st.error(err)
                else:
                    st.success("申請しました。管理者の承認をお待ちください（承認後にログインできます）。")


# ============================================================
# 画面：マイページ（銘柄リスト）
# ============================================================
def my_watchlist(user):
    if user["role"] == "admin":
        return load_main_watchlist(), None
    data, sha = gh_read(user_watchlist_path(user["id"]), {"tickers": [], "names": {}})
    data.setdefault("tickers", [])
    data.setdefault("names", {})
    return data, sha


def render_mypage(user):
    st.subheader(f"📋 {user['name']} さんの登録銘柄")
    if user["role"] == "admin":
        st.info("管理者の銘柄リストは LINE（株シグナル通知）と連動しています。追加・削除は LINE で「追加 7203」「削除 7203」と送ってください。")
        wl = load_main_watchlist()
        for code in wl["tickers"]:
            st.write("■ " + display_name(code, wl["names"]))
        return

    try:
        wl, sha = my_watchlist(user)
    except Exception as e:
        st.error(f"銘柄リストを読めませんでした：{e}")
        return

    with st.form("add_ticker_form", clear_on_submit=True):
        c1, c2 = st.columns([2, 3])
        code_in = c1.text_input("銘柄コード（例：7203 / AAPL）")
        name_in = c2.text_input("銘柄名（空欄なら自動で調べます）")
        if st.form_submit_button("➕ 追加"):
            code = normalize_code(code_in)
            if not code:
                st.error("銘柄コードを入力してください。")
            elif code in wl["tickers"]:
                st.warning(f"{display_name(code, wl['names'])} はすでに登録されています。")
            else:
                with st.spinner("銘柄名を調べています..."):
                    name = name_in.strip() or lookup_name(code)
                wl["tickers"].append(code)
                if name:
                    wl["names"][code] = name
                try:
                    gh_write(user_watchlist_path(user["id"]), wl, sha, f"{user['id']}: add {code}")
                    st.success(f"追加しました：{display_name(code, wl['names'])}")
                    st.rerun()
                except Exception as e:
                    st.error(f"保存できませんでした：{e}")

    if not wl["tickers"]:
        st.info("まだ銘柄が登録されていません。上のフォームから追加してください。")
        return

    st.write(f"登録中：{len(wl['tickers'])} 銘柄")
    for code in list(wl["tickers"]):
        c1, c2 = st.columns([5, 1])
        c1.write("■ " + display_name(code, wl["names"]))
        if c2.button("削除", key=f"del_{code}"):
            wl["tickers"].remove(code)
            wl["names"].pop(code, None)
            try:
                gh_write(user_watchlist_path(user["id"]), wl, sha, f"{user['id']}: remove {code}")
                st.rerun()
            except Exception as e:
                st.error(f"保存できませんでした：{e}")


# ============================================================
# 画面：管理（管理者のみ）
# ============================================================
def render_admin():
    st.subheader("👑 ユーザー管理")
    try:
        users, sha = load_users()
    except Exception as e:
        st.error(f"ユーザー一覧を読めませんでした：{e}")
        return

    if not users["users"]:
        st.info("登録ユーザーはまだいません。")
        return

    def update(uid, new_status, msg):
        users["users"][uid]["status"] = new_status
        if new_status == "active" and not users["users"][uid].get("approved_at"):
            users["users"][uid]["approved_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_users(users, sha, msg)
        st.rerun()

    def label(uid, rec):
        sub = rec.get("sub_name", "")
        text = f"**{rec['name']}**（{uid}）"
        if sub:
            text += f"　｜　サブ名：**{sub}**"
        return text

    def sub_name_editor(uid, rec):
        """管理者だけが見られるサブ名（本人には表示されない）。"""
        c1, c2 = st.columns([4, 1])
        new_sub = c1.text_input(
            "サブ名（管理用・本人には見えません）",
            value=rec.get("sub_name", ""),
            key=f"sub_{uid}",
            placeholder="例：本名、店名、誰か分かるメモ",
            label_visibility="collapsed",
        )
        if c2.button("保存", key=f"save_sub_{uid}"):
            users["users"][uid]["sub_name"] = new_sub.strip()
            save_users(users, sha, f"sub_name {uid}")
            st.rerun()

    def password_reset_editor(uid, rec):
        """管理者がその人のパスワードを新しいものに置き換える。"""
        c1, c2 = st.columns([4, 1])
        new_pw = c1.text_input(
            "新しいパスワード（6文字以上）",
            key=f"pw_{uid}",
            placeholder="新しいパスワード（6文字以上）を入れて「再設定」",
            label_visibility="collapsed",
        )
        if c2.button("再設定", key=f"reset_pw_{uid}"):
            if len(new_pw) < 6:
                st.error("パスワードは6文字以上にしてください。")
            else:
                salt = pysecrets.token_hex(16)
                users["users"][uid]["salt"] = salt
                users["users"][uid]["hash"] = make_hash(new_pw, salt)
                users["users"][uid]["pw_reset_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                save_users(users, sha, f"reset password {uid}")
                st.success(f"{rec['name']}（{uid}）のパスワードを再設定しました。本人に新しいパスワードを伝えてください。")

    pending = {k: v for k, v in users["users"].items() if v["status"] == "pending"}
    others = {k: v for k, v in users["users"].items() if v["status"] != "pending"}

    if pending:
        st.markdown("#### 🆕 承認待ち")
        for uid, rec in pending.items():
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([3, 2, 1.2, 1.2])
                c1.markdown(label(uid, rec))
                c2.caption(f"申請 {rec.get('created', '')}")
                if c3.button("✅ 承認", key=f"approve_{uid}", type="primary"):
                    update(uid, "active", f"approve {uid}")
                if c4.button("🗑 却下", key=f"reject_{uid}"):
                    del users["users"][uid]
                    save_users(users, sha, f"reject {uid}")
                    st.rerun()
                sub_name_editor(uid, rec)
                password_reset_editor(uid, rec)
        st.divider()

    st.markdown("#### 利用可否")
    if not others:
        st.caption("承認済みのユーザーはまだいません。")
    for uid, rec in others.items():
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3, 2, 1.2, 1.2])
            c1.markdown(label(uid, rec))
            active = rec["status"] == "active"
            c2.write("🟢 利用許可" if active else "⛔ 利用停止")
            if c3.button("✔ 利用許可", key=f"on_{uid}", disabled=active, type="primary" if not active else "secondary"):
                update(uid, "active", f"enable {uid}")
            if c4.button("✔ 利用停止", key=f"off_{uid}", disabled=not active, type="primary" if active else "secondary"):
                update(uid, "stopped", f"stop {uid}")
            sub_name_editor(uid, rec)
            password_reset_editor(uid, rec)


# ============================================================
# 画面：ログイン後
# ============================================================
def render_app(user):
    enforce_status()

    st.title("🎯 AI Smart Trader - インテリジェント投資判定システム")

    st.sidebar.markdown(f"👤 **{user['name']}**（{user['id']}）")
    if st.sidebar.button("ログアウト", use_container_width=True):
        logout()
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ 設定")
    risk_percent = st.sidebar.slider("損失許容率 (%)", 0.5, 5.0, 1.0, 0.1)
    profit_target = st.sidebar.slider("利確目標 (%)", 1.0, 10.0, 3.0, 0.5)
    period = st.sidebar.selectbox("分析期間", ["1mo", "3mo", "6mo", "1y", "2y"], index=3)
    st.sidebar.markdown("---")
    st.sidebar.info("💡 このアプリは投資判定の参考です。最終判断はご自身の責任でお願いします。")

    tab_names = ["📊 銘柄分析", "🎯 シグナル判定", "📈 テクニカル指標", "📋 マイページ"]
    if user["role"] == "admin":
        tab_names.append("👑 管理")
    tabs = st.tabs(tab_names)

    # ---------- 銘柄分析 ----------
    with tabs[0]:
        st.subheader("銘柄を選ぶ")
        try:
            wl, _ = my_watchlist(user)
        except Exception:
            wl = {"tickers": [], "names": {}}

        placeholder = "（コードを手入力する）"
        labels = [display_name(c, wl["names"]) for c in wl["tickers"]]
        code_by_label = dict(zip(labels, wl["tickers"]))

        pick = st.selectbox("登録銘柄から選ぶ（選ぶとすぐ分析します）", [placeholder] + labels, key="pick_box")
        ticker = st.text_input("または銘柄コードを入力", value="", placeholder="例：7974 / 285A / AAPL（日本株は4桁だけでOK）")
        run_manual = st.button("📥 分析開始")

        code_to_run = None
        if run_manual and ticker.strip():
            code_to_run = normalize_code(ticker)
        elif pick != placeholder and pick != st.session_state.get("last_pick"):
            code_to_run = code_by_label[pick]
            st.session_state.last_pick = pick

        if code_to_run:
            with st.spinner(f"{code_to_run} のデータを取得中..."):
                data = fetch_history(code_to_run, period)
                shown = display_name(code_to_run, wl["names"])
            if data.empty:
                st.error(f"❌ {code_to_run} のデータが見つかりません。銘柄コードを確認してください。")
                for key in ["data", "ticker", "name"]:
                    st.session_state.pop(key, None)
            else:
                st.session_state.ticker = code_to_run
                st.session_state.name = shown
                st.session_state.data = data

        if "data" in st.session_state:
            code = st.session_state.ticker
            data = st.session_state.data
            sym = currency_symbol(code)
            latest_price = float(data["Close"].iloc[-1])
            prev_close = float(data["Close"].iloc[-2]) if len(data) > 1 else latest_price
            change_percent = ((latest_price - prev_close) / prev_close * 100) if prev_close else 0.0

            st.markdown(f"## 🏷️ {st.session_state.name}")
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("現在値", f"{sym}{latest_price:,.2f}")
            col2.metric("前日比", f"{change_percent:+.2f}%")
            col3.metric("データ期間", f"{len(data)}日")
            col4.metric("取得日時", datetime.now().strftime("%Y-%m-%d %H:%M"))
            st.subheader("📈 株価推移")
            st.line_chart(data["Close"])
            st.success(f"✅ {st.session_state.name} の分析準備完了（他のタブで判定を確認できます）")

    # ---------- シグナル判定 ----------
    with tabs[1]:
        st.subheader("🎯 買い・売りシグナル")
        if "data" in st.session_state:
            code = st.session_state.ticker
            st.markdown(f"#### 🏷️ {st.session_state.name}")
            sym = currency_symbol(code)
            df = add_indicators(st.session_state.data)
            latest = df.iloc[-1]
            current_price = float(latest["Close"])

            signals = []
            confidence = 0
            ma20, ma200, rsi = latest["MA20"], latest["MA200"], latest["RSI"]

            if pd.notna(ma20) and pd.notna(ma200):
                if ma20 > ma200:
                    signals.append("🟢 MA: 上昇トレンド（MA20 > MA200）")
                    confidence += 30
                else:
                    signals.append("🔴 MA: 下降トレンド（MA20 < MA200）")
                    confidence -= 30
            else:
                signals.append("⚪ MA: データ不足（分析期間を長くしてください）")

            if pd.notna(rsi):
                if rsi < 30:
                    signals.append(f"🟢 RSI: 売られ過ぎ・買いシグナル（{rsi:.1f}）")
                    confidence += 40
                elif rsi > 70:
                    signals.append(f"🔴 RSI: 買われ過ぎ・売りシグナル（{rsi:.1f}）")
                    confidence -= 40
                else:
                    signals.append(f"🟡 RSI: 中立（{rsi:.1f}）")
            else:
                signals.append("⚪ RSI: データ不足")

            if confidence >= 60:
                recommendation = "🟢 **買い推奨**"
            elif confidence <= -60:
                recommendation = "🔴 **売り推奨**"
            else:
                recommendation = "🟡 **様子見**"

            st.markdown(f"### {recommendation}")
            st.metric("信頼度スコア", f"{confidence}/100")
            st.write("**テクニカルシグナル**")
            for signal in signals:
                st.write(signal)
            st.write("**リスク管理レベル**")
            col1, col2 = st.columns(2)
            col1.write(f"🛑 損切りレベル：{sym}{current_price * (1 - risk_percent / 100):,.2f}")
            col2.write(f"💰 利確レベル：{sym}{current_price * (1 + profit_target / 100):,.2f}")
        else:
            st.info("「📊 銘柄分析」タブで銘柄を選んでから、このタブを開いてください")

    # ---------- テクニカル指標 ----------
    with tabs[2]:
        st.subheader("📊 テクニカル指標詳細")
        if "data" in st.session_state:
            st.markdown(f"#### 🏷️ {st.session_state.name}")
            df = add_indicators(st.session_state.data)
            col1, col2 = st.columns(2)
            with col1:
                st.write("**移動平均線（MA）**")
                st.line_chart(df[["Close", "MA20", "MA200"]].tail(100))
            with col2:
                st.write("**相対力指数（RSI）**")
                st.line_chart(df[["RSI"]].tail(100))
        else:
            st.info("「📊 銘柄分析」タブで銘柄を選んでから、このタブを開いてください")

    # ---------- マイページ ----------
    with tabs[3]:
        render_mypage(user)

    # ---------- 管理 ----------
    if user["role"] == "admin":
        with tabs[4]:
            render_admin()


# ============================================================
# エントリーポイント
# ============================================================
if current_user():
    render_app(current_user())
else:
    render_auth()
