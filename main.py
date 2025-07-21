import os
from dotenv import load_dotenv
from binance.client import Client
from binance.enums import * # Untuk interval seperti KLINE_INTERVAL_5MINUTE
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import datetime

# --- 1. Konfigurasi dan Inisialisasi API ---
load_dotenv() # Muat variabel lingkungan dari .env

API_KEY = os.environ.get("BINANCE_API_KEY")
API_SECRET = os.environ.get("BINANCE_API_SECRET")

if not API_KEY or not API_SECRET:
    raise ValueError("API Key atau API Secret tidak ditemukan di file .env. Pastikan sudah diatur.")

client = Client(API_KEY, API_SECRET)

# --- 2. Fungsi Pengambilan Data ---
def get_klines_data(symbol, interval, start_str, end_str=None):
    """Mengambil data Klines (OHLCV) historis."""
    print(f"Mengambil data Klines untuk {symbol} ({interval})...")
    klines = client.get_historical_klines(symbol, interval, start_str, end_str)
    df = pd.DataFrame(klines, columns=[
        'Open time', 'Open', 'High', 'Low', 'Close', 'Volume',
        'Close time', 'Quote asset volume', 'Number of trades',
        'Taker buy base asset volume', 'Taker buy quote asset volume', 'Ignore'
    ])
    df['Open time'] = pd.to_datetime(df['Open time'], unit='ms')
    df['Close time'] = pd.to_datetime(df['Close time'], unit='ms')
    df = df[['Open time', 'Open', 'High', 'Low', 'Close', 'Volume', 'Taker buy base asset volume', 'Taker buy quote asset volume']]
    df[['Open', 'High', 'Low', 'Close', 'Volume', 'Taker buy base asset volume', 'Taker buy quote asset volume']] = \
        df[['Open', 'High', 'Low', 'Close', 'Volume', 'Taker buy base asset volume', 'Taker buy quote asset volume']].astype(float)
    df.set_index('Open time', inplace=True)
    return df

# *** PERBAIKAN DI SINI ***
def get_open_interest_data(symbol, interval_str, start_str): # Tambahkan start_str
    """Mengambil data Open Interest. Perhatikan interval yang digunakan."""
    print(f"Mengambil data Open Interest untuk {symbol} ({interval_str})...")
    # futures_open_interest_hist mengharapkan interval dalam string ('5m', '1h', dll.)
    # dan juga memerlukan startTime.
    # kita akan mengkonversi start_str ke milidetik
    # Ini juga bisa menjadi masalah jika start_str terlalu jauh ke belakang,
    # karena API memiliki batasan max data points per request

    # Konversi start_str ke milidetik
    start_ms = int(datetime.datetime.strptime(start_str, "%d %b %Y %H:%M:%S").timestamp() * 1000) if " " in start_str else client.get_server_time() - 2 * 24 * 60 * 60 * 1000


    oi_data = client.futures_open_interest_hist(symbol=symbol, period=interval_str, startTime=start_ms)
    df = pd.DataFrame(oi_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df['sumOpenInterest'] = df['sumOpenInterest'].astype(float)
    df.set_index('timestamp', inplace=True)
    return df[['sumOpenInterest']]

# *** PERBAIKAN DI SINI ***
# Fungsi Long/Short Ratio juga perlu interval string dan startTime
def get_long_short_ratio_data(symbol, period_str, start_str): # Tambahkan start_str
    """Mengambil data Long/Short Ratio (Accounts dan Positions)."""
    print(f"Mengambil data Long/Short Ratio untuk {symbol} ({period_str})...")
    start_ms = int(datetime.datetime.strptime(start_str, "%d %b %Y %H:%M:%S").timestamp() * 1000) if " " in start_str else client.get_server_time() - 2 * 24 * 60 * 60 * 1000

    # Top Trader Account Ratio
    ls_accounts = client.futures_top_longshort_account_ratio(symbol=symbol, period=period_str, startTime=start_ms)
    df_accounts = pd.DataFrame(ls_accounts)
    df_accounts['timestamp'] = pd.to_datetime(df_accounts['timestamp'], unit='ms')
    df_accounts['longShortRatio'] = df_accounts['longShortRatio'].astype(float)
    df_accounts.set_index('timestamp', inplace=True)

    # Top Trader Position Ratio
    ls_positions = client.futures_top_longshort_position_ratio(symbol=symbol, period=period_str, startTime=start_ms)
    df_positions = pd.DataFrame(ls_positions)
    df_positions['timestamp'] = pd.to_datetime(df_positions['timestamp'], unit='ms')
    df_positions['longShortRatio'] = df_positions['longShortRatio'].astype(float)
    df_positions.set_index('timestamp', inplace=True)

    # Overall Long/Short Ratio
    ls_overall = client.futures_global_longshort_account_ratio(symbol=symbol, period=period_str, startTime=start_ms)
    df_overall = pd.DataFrame(ls_overall)
    df_overall['timestamp'] = pd.to_datetime(df_overall['timestamp'], unit='ms')
    df_overall['longShortRatio'] = df_overall['longShortRatio'].astype(float)
    df_overall.set_index('timestamp', inplace=True)

    return df_accounts[['longShortRatio']].rename(columns={'longShortRatio': 'LSR_Accounts'}), \
           df_positions[['longShortRatio']].rename(columns={'longShortRatio': 'LSR_Positions'}), \
           df_overall[['longShortRatio']].rename(columns={'longShortRatio': 'LSR_Overall'})


# ... (Fungsi perform_complex_analysis dan plot_dashboard tidak berubah) ...
def perform_complex_analysis(df):
    """
    Melakukan analisis kompleks pada data yang digabungkan.
    Mengembalikan dictionary hasil analisis dan DataFrame akhir.
    """
    df_final = df.copy()

    # 1. Menghitung Perubahan Persentase (ROC - Rate of Change)
    df_final['Price_ROC'] = df_final['Close'].pct_change() * 100
    df_final['OI_ROC'] = df_final['sumOpenInterest'].pct_change() * 100
    df_final['TakerBuyVolume_ROC'] = df_final['TakerBuyVolume'].pct_change() * 100
    df_final['TakerSellVolume_ROC'] = df_final['TakerSellVolume'].pct_change() * 100

    # 2. Menganalisis Hubungan Harga dan Open Interest
    price_up = df_final['Price_ROC'] > 0
    price_down = df_final['Price_ROC'] < 0
    oi_up = df_final['OI_ROC'] > 0
    oi_down = df_final['OI_ROC'] < 0

    # Skenario
    longs_opening = (price_up & oi_up).sum()
    shorts_closing = (price_up & oi_down).sum()
    shorts_opening = (price_down & oi_up).sum()
    longs_closing = (price_down & oi_down).sum()

    total_periods = len(df_final)
    analysis = {
        "Sinyal Bullish (Longs Opening)": f"{(longs_opening / total_periods) * 100:.2f}%",
        "Sinyal Bullish (Shorts Closing)": f"{(shorts_closing / total_periods) * 100:.2f}%",
        "Sinyal Bearish (Shorts Opening)": f"{(shorts_opening / total_periods) * 100:.2f}%",
        "Sinyal Bearish (Longs Closing)": f"{(longs_closing / total_periods) * 100:.2f}%",
    }

    # 3. Analisis Volume Taker
    avg_taker_buy = df_final['TakerBuyVolume'].mean()
    avg_taker_sell = df_final['TakerSellVolume'].mean()
    analysis['Rata-rata Taker Buy Volume'] = f"{avg_taker_buy:,.2f}"
    analysis['Rata-rata Taker Sell Volume'] = f"{avg_taker_sell:,.2f}"
    if avg_taker_buy > avg_taker_sell:
        analysis['Dominasi Volume Taker'] = f"Beli ({(avg_taker_buy / (avg_taker_buy + avg_taker_sell)) * 100:.2f}%)"
    else:
        analysis['Dominasi Volume Taker'] = f"Jual ({(avg_taker_sell / (avg_taker_buy + avg_taker_sell)) * 100:.2f}%)"

    # 4. Analisis Long/Short Ratio
    last_lsr_accounts = df_final['LSR_Accounts'].iloc[-1]
    last_lsr_positions = df_final['LSR_Positions'].iloc[-1]
    last_lsr_overall = df_final['LSR_Overall'].iloc[-1]
    analysis['L/S Ratio (Top Accounts) Terkini'] = f"{last_lsr_accounts:.2f}"
    analysis['L/S Ratio (Top Positions) Terkini'] = f"{last_lsr_positions:.2f}"
    analysis['L/S Ratio (Overall) Terkini'] = f"{last_lsr_overall:.2f}"

    # 5. Analisis Basis (jika ada)
    if 'Basis' in df_final and not df_final['Basis'].isnull().all():
        last_basis = df_final['Basis'].iloc[-1]
        avg_basis = df_final['Basis'].mean()
        analysis['Basis Terkini'] = f"{last_basis:.4f}"
        analysis['Rata-rata Basis'] = f"{avg_basis:.4f}"
        if last_basis > 0:
            analysis['Interpretasi Basis'] = "Contango (Harga Futures > Harga Spot) - Potensi sentimen bullish."
        else:
            analysis['Interpretasi Basis'] = "Backwardation (Harga Futures < Harga Spot) - Potensi sentimen bearish."

    return analysis, df_final

def plot_dashboard(df, symbol):
    """Membuat dan menampilkan dashboard Plotly."""
    fig = make_subplots(
        rows=5, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        subplot_titles=(
            f"Harga & Open Interest - {symbol}",
            "Volume Taker Buy vs Sell",
            "Basis (Futures Price - Index Price)",
            "Long/Short Ratio (Top Traders)",
            "Long/Short Ratio (Overall)"
        ),
        row_heights=[0.4, 0.15, 0.15, 0.15, 0.15]
    )

    # 1. Candlestick dan Open Interest
    fig.add_trace(go.Candlestick(
        x=df.index,
        open=df['Open'],
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        name='Harga'
    ), row=1, col=1)
    fig.add_trace(go.Scatter(
        x=df.index,
        y=df['sumOpenInterest'],
        name='Open Interest',
        yaxis='y2'
    ), row=1, col=1)

    # 2. Volume Taker
    fig.add_trace(go.Bar(
        x=df.index,
        y=df['TakerBuyVolume'],
        name='Taker Buy Vol',
        marker_color='green'
    ), row=2, col=1)
    fig.add_trace(go.Bar(
        x=df.index,
        y=df['TakerSellVolume'],
        name='Taker Sell Vol',
        marker_color='red'
    ), row=2, col=1)

    # 3. Basis
    if 'Basis' in df:
        fig.add_trace(go.Scatter(
            x=df.index, y=df['Basis'], name='Basis',
            line=dict(color='purple')
        ), row=3, col=1)
        fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="grey", row=3, col=1)


    # 4. Long/Short Ratios (Top Traders)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['LSR_Accounts'], name='L/S Ratio (Accounts)',
        line=dict(color='blue')
    ), row=4, col=1)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['LSR_Positions'], name='L/S Ratio (Positions)',
        line=dict(color='orange')
    ), row=4, col=1)
    fig.add_hline(y=1, line_width=1, line_dash="dash", line_color="grey", row=4, col=1)


    # 5. Long/Short Ratio (Overall)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['LSR_Overall'], name='L/S Ratio (Overall)',
        line=dict(color='cyan')
    ), row=5, col=1)
    fig.add_hline(y=1, line_width=1, line_dash="dash", line_color="grey", row=5, col=1)


    # Update Layout
    fig.update_layout(
        height=1200,
        title_text=f"Dashboard Analisis Komprehensif untuk {symbol}",
        xaxis_rangeslider_visible=False,
        yaxis=dict(title='Harga (USDT)'),
        yaxis2=dict(title='Open Interest', overlaying='y', side='right'),
        yaxis3=dict(title='Volume'),
        yaxis4=dict(title='Basis'),
        yaxis5=dict(title='L/S Ratio'),
        yaxis6=dict(title='L/S Ratio'),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_yaxes(title_text="Volume", row=2, col=1)
    fig.update_yaxes(title_text="Basis", row=3, col=1)
    fig.update_yaxes(title_text="L/S Ratio", row=4, col=1)
    fig.update_yaxes(title_text="L/S Ratio", row=5, col=1)


    fig.show()

def get_mark_and_index_price(symbol, interval):
    """Mengambil harga Mark dan Index saat ini."""
    print(f"Mengambil data harga Mark & Index untuk {symbol}...")
    try:
        # Ambil data premium index
        premium_index_data = client.futures_premium_index(symbol=symbol)
        mark_price = float(premium_index_data['markPrice'])
        index_price = float(premium_index_data['indexPrice'])
        return mark_price, index_price
    except Exception as e:
        print(f"Gagal mengambil data Mark/Index untuk {symbol}: {e}")
        return None, None

# --- Fungsi Utama untuk Menjalankan Analisis ---
def run_full_analysis(symbol, klines_interval, ls_period_str, start_time_str): # ls_period_str sekarang string
    """Menjalankan seluruh proses analisis."""
    print(f"\nMemulai analisis untuk {symbol}...")

    # 1. Ambil Data
    df_klines = get_klines_data(symbol, klines_interval, start_time_str)
    # *** PERBAIKAN DI SINI ***
    # Pastikan interval untuk OI juga string dan sertakan start_time_str
    df_oi = get_open_interest_data(symbol, ls_period_str, start_time_str)
    df_ls_accounts, df_ls_positions, df_ls_overall = get_long_short_ratio_data(symbol, ls_period_str, start_time_str)

    # Gabungkan semua DataFrame berdasarkan indeks waktu
    # Gunakan outer join untuk memastikan semua timestamp ada, lalu fillna jika perlu
    df_merged = df_klines.merge(df_oi, left_index=True, right_index=True, how='outer')
    df_merged = df_merged.merge(df_ls_accounts, left_index=True, right_index=True, how='outer')
    df_merged = df_merged.merge(df_ls_positions, left_index=True, right_index=True, how='outer')
    df_merged = df_merged.merge(df_ls_overall, left_index=True, right_index=True, how='outer')

    # Hitung Taker Buy/Sell Volume (dari klines)
    df_merged['TakerBuyVolume'] = df_merged['Taker buy base asset volume']
    df_merged['TakerSellVolume'] = df_merged['Volume'] - df_merged['Taker buy base asset volume']

    # Hitung Basis (perlu harga Mark dan Index historis, jika tidak ada, ini akan menjadi tantangan)
    # Untuk demo, kita akan menggunakan harga Close sebagai proxy untuk futures price dan mengasumsikan index price sama
    # Implementasi nyata: Anda perlu mencari cara untuk mendapatkan data historis mark price dan index price
    # Jika tidak ada API langsung, Anda mungkin perlu mengambil klines dari pair MARK/USDT dan INDEX/USDT jika tersedia.

    # *** PERBAIKAN DI SINI ***
    # Untuk mendapatkan basis yang relevan, kita butuh harga markPriceHistory dan indexPriceHistory.
    # Binance tidak menyediakan endpoint historical untuk ini secara langsung dalam format interval.
    # Sebagai solusi sementara (tidak sempurna):
    # Asumsikan mark_price dan index_price saat ini relevan untuk basis terbaru
    current_mark_price, current_index_price = get_mark_and_index_price(symbol)
    if current_mark_price is not None and current_index_price is not None:
        # Hitung basis saat ini
        current_basis = current_mark_price - current_index_price

        # Buat kolom 'Basis' dan isi dengan NaN
        df_merged['Basis'] = np.nan

        # Set nilai basis terakhir dalam DataFrame
        if not df_merged.empty:
            df_merged.loc[df_merged.index[-1], 'Basis'] = current_basis

        print(f"Basis saat ini dihitung: {current_basis:.4f}")
        print("PERINGATAN: Perhitungan Basis historis tidak tersedia. Hanya nilai basis terakhir yang ditampilkan.")
    else:
        df_merged['Basis'] = np.nan # Jika gagal ambil data saat ini, isi NaN
        print("PERINGATAN: Gagal mengambil data harga Mark/Index. Kolom Basis akan kosong.")


    # Hapus baris dengan NaN yang dihasilkan dari penggabungan atau rolling window di awal
    df_merged.dropna(inplace=True)

    if df_merged.empty:
        print("Tidak ada data yang cukup setelah penggabungan dan pembersihan. Coba rentang waktu yang lebih luas atau periksa parameter API.")
        return

    # 2. Lakukan Analisis Kompleks
    analysis_results, df_final_data = perform_complex_analysis(df_merged.copy()) # Gunakan copy agar tidak mengubah df_merged asli

    # 3. Visualisasi
    plot_dashboard(df_final_data, symbol)

    # 4. Tampilkan Hasil Analisis
    print("\n--- Hasil Analisis Kompleks ---")
    for key, value in analysis_results.items():
        print(f"{key}: {value}")
    print("-------------------------------")

# --- Jalankan Aplikasi ---
if __name__ == "__main__":
    target_symbol = "SOLUSDT" # Ganti dengan aset yang ingin Anda analisis
    data_klines_interval = KLINE_INTERVAL_5MINUTE # Interval data Klines
    ls_ratio_period_str = "5m" # Interval untuk Long/Short Ratio (HARUS STRING: '5m', '15m', '1h', dll.)
    start_date = "2 days ago UTC" # Ambil data dari 2 hari yang lalu

    try:
        run_full_analysis(target_symbol, data_klines_interval, ls_ratio_period_str, start_date)
    except ValueError as e:
        print(f"Error konfigurasi: {e}")
    except Exception as e:
        print(f"Terjadi kesalahan: {e}")
        # Tambahkan detail error untuk debugging
        import traceback
        traceback.print_exc()
        print("Pastikan Anda memiliki koneksi internet dan API key/secret yang valid. Periksa juga parameter interval dan periode.")
