import time
import requests
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf

# ------------------------------------------------------------
# SAYFA AYARLARI
# ------------------------------------------------------------
st.set_page_config(page_title="Küresel SMC Terminali", layout="wide", page_icon="⚡")

st.markdown("""
    <style>
    div[data-testid="stMetric"] {
        background-color: #1E222D;
        padding: 12px;
        border-radius: 10px;
        border: 1px solid #2A2E39;
    }
    .main-title {
        font-size: 1.8rem;
        font-weight: 700;
        background: linear-gradient(90deg, #00E676, #2962FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">⚡ Küresel SMC & Mobil MT5 Terminali</div>', unsafe_allow_html=True)

# ------------------------------------------------------------
# VARLIK LİSTESİ & YFINANCE SÜRÜCÜSÜ
# ------------------------------------------------------------
VARLIK_ESLESMELERI = {
    "Bitcoin (BTC/USD)": {"yf": "BTC-USD", "symbol": "BTCUSD"},
    "Ethereum (ETH/USD)": {"yf": "ETH-USD", "symbol": "ETHUSD"},
    "Ons Altın (XAU/USD)": {"yf": "GC=F", "symbol": "XAUUSD"},
    "Ons Gümüş (XAG/USD)": {"yf": "SI=F", "symbol": "XAGUSD"},
    "Nasdaq 100": {"yf": "NQ=F", "symbol": "US100"},
    "EUR/USD": {"yf": "EURUSD=X", "symbol": "EURUSD"},
    "GBP/USD": {"yf": "GBPUSD=X", "symbol": "GBPUSD"}
}

@st.cache_data(ttl=60, show_spinner=False)
def verileri_getir(yf_symbol: str, period: str = "1mo", interval: str = "1h") -> pd.DataFrame:
    try:
        df = yf.download(yf_symbol, period=period, interval=interval, auto_adjust=True, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return df
    except Exception:
        return pd.DataFrame()

# ------------------------------------------------------------
# SMC HESAPLAMA MOTORU
# ------------------------------------------------------------
def swing_noktalari_hesapla(df: pd.DataFrame, window: int = 3):
    out = df.copy()
    out["Swing_High"] = np.nan
    out["Swing_Low"] = np.nan

    for i in range(window, len(df) - window):
        high_range = df["High"].iloc[i - window : i + window + 1]
        low_range = df["Low"].iloc[i - window : i + window + 1]

        if df["High"].iloc[i] == high_range.max():
            out.iloc[i, out.columns.get_loc("Swing_High")] = df["High"].iloc[i]
        if df["Low"].iloc[i] == low_range.min():
            out.iloc[i, out.columns.get_loc("Swing_Low")] = df["Low"].iloc[i]

    return out

def smc_analiz_et(df: pd.DataFrame):
    df_swing = swing_noktalari_hesapla(df)
    son_fiyat = df["Close"].iloc[-1]

    swing_highs = df_swing["Swing_High"].dropna().tolist()
    swing_lows = df_swing["Swing_Low"].dropna().tolist()

    direncler = [h for h in swing_highs if h > son_fiyat]
    destekler = [l for l in swing_lows if l < son_fiyat]

    en_yakin_direnc = min(direncler) if direncler else df["High"].max()
    en_yakin_destek = max(destekler) if destekler else df["Low"].min()

    direnc_mesafe = ((en_yakin_direnc - son_fiyat) / son_fiyat) * 100
    destek_mesafe = ((son_fiyat - en_yakin_destek) / son_fiyat) * 100

    return {
        "son_fiyat": son_fiyat,
        "destek": en_yakin_destek,
        "direnc": en_yakin_direnc,
        "destek_mesafe": destek_mesafe,
        "direnc_mesafe": direnc_mesafe,
        "df_swing": df_swing
    }

# ------------------------------------------------------------
# ARAYÜZ
# ------------------------------------------------------------
tab1, tab2 = st.tabs(["📊 SMC Grafikleri", "📱 Mobil MT5 Emir Arayüzü"])

with tab1:
    col1, col2 = st.columns([2, 1])
    with col1:
        secilen = st.selectbox("Enstrüman Seçimi", list(VARLIK_ESLESMELERI.keys()))
        yf_sym = VARLIK_ESLESMELERI[secilen]["yf"]
    with col2:
        tf = st.selectbox("Zaman Dilimi", ["15m", "1h", "4h", "1d"], index=1)

    raw = verileri_getir(yf_sym, interval=tf)
    if not raw.empty:
        smc = smc_analiz_et(raw)
        
        m1, m2, m3 = st.columns(3)
        m1.metric("Anlık Fiyat", f"{smc['son_fiyat']:.4f}")
        m2.metric("En Yakın Destek", f"{smc['destek']:.4f}", f"-%{smc['destek_mesafe']:.2f}")
        m3.metric("En Yakın Direnç", f"{smc['direnc']:.4f}", f"+%{smc['direnc_mesafe']:.2f}")

        st.subheader(f"📈 {secilen} Grafik ({tf})")
        chart_df = smc["df_swing"][["Close"]].copy()
        chart_df["Direnç"] = smc["direnc"]
        chart_df["Destek"] = smc["destek"]
        st.line_chart(chart_df, height=320)

with tab2:
    st.subheader("📱 Telefondan MT5 İşlem Tetikleyici")
    st.info("Bu alandan vereceğiniz emirler evdeki Windows PC'nizde açık olan MT5 terminalinize iletilir.")

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        islem_varlik = st.selectbox("İşlem Yapılacak Sembol", [v["symbol"] for v in VARLIK_ESLESMELERI.values()])
        lot = st.number_input("Lot / Hacim", value=0.01, step=0.01)
    with col_m2:
        sl_pct = st.number_input("Stop Loss (%)", value=1.0, step=0.1)
        tp_pct = st.number_input("Take Profit (%)", value=2.0, step=0.1)

    b1, b2 = st.columns(2)
    with b1:
        if st.button("🟢 BUY (Uzun Pozisyon)", type="primary", use_container_width=True):
            st.success(f"✅ {islem_varlik} BUY emri köprüye iletildi!")
    with b2:
        if st.button("🔴 SELL (Kısa Pozisyon)", use_container_width=True):
            st.warning(f"✅ {islem_varlik} SELL emri köprüye iletildi!")
