import time
import pandas as pd
import numpy as np
import streamlit as st
import MetaTrader5 as mt5
import yfinance as yf

# ------------------------------------------------------------
# SAYFA AYARLARI
# ------------------------------------------------------------
st.set_page_config(page_title="MT5 Canlı SMC Terminali", layout="wide", page_icon="⚡")

st.markdown("""
    <style>
    div[data-testid="stMetric"] {
        background-color: #1E222D;
        padding: 15px;
        border-radius: 10px;
        border: 1px solid #2A2E39;
    }
    .main-title {
        font-size: 2.0rem;
        font-weight: 700;
        background: linear-gradient(90deg, #00E676, #2962FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">⚡ MT5 Doğrudan Veri Beslemeli SMC Terminali</div>', unsafe_allow_html=True)

# ------------------------------------------------------------
# MT5 BAĞLANTI SÜRÜCÜSÜ VE VERİ ÇEKME
# ------------------------------------------------------------
def mt5_baglan():
    if not mt5.initialize():
        return False
    return True

TIMEFRAME_MAP = {
    "15m": mt5.TIMEFRAME_M15 if hasattr(mt5, "TIMEFRAME_M15") else "15m",
    "1h": mt5.TIMEFRAME_H1 if hasattr(mt5, "TIMEFRAME_H1") else "1h",
    "4h": mt5.TIMEFRAME_H4 if hasattr(mt5, "TIMEFRAME_H4") else "4h",
    "1d": mt5.TIMEFRAME_D1 if hasattr(mt5, "TIMEFRAME_D1") else "1d",
}

VARLIK_ESLESMELERI = {
    "EURUSD": {"mt5": "EURUSD", "yf": "EURUSD=X"},
    "GBPUSD": {"mt5": "GBPUSD", "yf": "GBPUSD=X"},
    "BTCUSD": {"mt5": "BTCUSD", "yf": "BTC-USD"},
    "XAUUSD (Altın)": {"mt5": "XAUUSD", "yf": "GC=F"},
    "NASDAQ (US100)": {"mt5": "US100", "yf": "NQ=F"},
}

def mt5_veri_cek(symbol: str, timeframe_str: str, count: int = 300) -> pd.DataFrame:
    if mt5_baglan():
        tf = TIMEFRAME_MAP.get(timeframe_str, mt5.TIMEFRAME_H1)
        mt5.symbol_select(symbol, True)
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, count)
        if rates is not None and len(rates) > 0:
            df = pd.DataFrame(rates)
            df['time'] = pd.to_datetime(df['time'], unit='s')
            df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'tick_volume': 'Volume'}, inplace=True)
            return df

    yf_symbol = VARLIK_ESLESMELERI.get(symbol, {}).get("yf", symbol)
    df_yf = yf.download(yf_symbol, period="1mo", interval=timeframe_str, auto_adjust=True, progress=False)
    if isinstance(df_yf.columns, pd.MultiIndex):
        df_yf.columns = df_yf.columns.get_level_values(0)
    return df_yf

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
col1, col2, col3 = st.columns([2, 2, 1])

with col1:
    secilen_varlik = st.selectbox("Varlık Seçimi (MT5 Sembolü)", list(VARLIK_ESLESMELERI.keys()))
    mt5_symbol = VARLIK_ESLESMELERI[secilen_varlik]["mt5"]

with col2:
    tf_selection = st.selectbox("Zaman Dilimi", ["15m", "1h", "4h", "1d"], index=1)

with col3:
    st.write("###")
    if mt5_baglan():
        st.success("🟢 MT5 Bağlı")
    else:
        st.error("🔴 MT5 Kapalı (YFinance Modu)")

raw_data = mt5_veri_cek(mt5_symbol, tf_selection)

if not raw_data.empty:
    smc = smc_analiz_et(raw_data)
    
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("MT5 Canlı Fiyat", f"{smc['son_fiyat']:.5f}")
    m2.metric("MT5 Destek (Swing Low)", f"{smc['destek']:.5f}", f"-%{smc['destek_mesafe']:.2f}")
    m3.metric("MT5 Direnç (Swing High)", f"{smc['direnc']:.5f}", f"+%{smc['direnc_mesafe']:.2f}")
    m4.metric("Veri Kaynağı", "MetaTrader 5 API" if mt5_baglan() else "Yahoo Finance")

    st.subheader(f"📈 {mt5_symbol} — MT5 Canlı Grafiği ({tf_selection})")
    chart_df = smc["df_swing"][["Close"]].copy()
    chart_df["MT5 Direnç"] = smc["direnc"]
    chart_df["MT5 Destek"] = smc["destek"]
    st.line_chart(chart_df, height=360)
else:
    st.warning("Veri alınamadı. MT5 terminalinizde ilgili sembolün Market Watch penceresinde ekli olduğundan emin olun.")
