import os
import streamlit as st
from dotenv import load_dotenv
import requests
import json
import ollama

# ─── Load environment variables ───
load_dotenv()

# ─── Configuration ───
CRYPTO_PANIC_API_KEY  = os.getenv("CRYPTO_PANIC_API_KEY")
COINMARKETCAP_API_KEY = os.getenv("COINMARKETCAP_API_KEY")
BINANCE_API_URL       = "https://api.binance.com/api/v3"
COINMARKETCAP_API_URL = "https://pro-api.coinmarketcap.com/v1"
CRYPTO_PANIC_API_URL  = "https://cryptopanic.com/api/v1"
OLLAMA_HOST           = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
OLLAMA_MODEL          = os.getenv("OLLAMA_MODEL", "llama2")

# Initialize Ollama client
ollama_client = ollama.Client(host=OLLAMA_HOST)

# Manual overrides for known tickers
TICKER_OVERRIDES = {
    "bitcoin":  "BTC",
    "ethereum": "ETH",
    "solana":   "SOL",
    # add more as needed
}


def extract_coin(query: str) -> str:
    """
    Extract a coin identifier from the user query.
    Supports full names, uppercase tickers, and handles curly apostrophes.
    """
    # normalize quotes and lowercase
    q = query.lower().replace("’", "'").replace("‘", "'")
    # remove common noise words
    noise = [
        "tell me about", "what's", "what is", "what’s", "latest", "news",
        "price", "and", "market cap", "about", "?", "please"
    ]
    for w in noise:
        q = q.replace(w, "")
    q = q.strip()
    # split and strip punctuation
    token = q.split()[0] if q else ''
    token = token.strip(" .,!?'")
    # if it's an uppercase ticker (3-5 letters) in original query, accept it
    if token.isupper() and 3 <= len(token) <= 5:
        return token.lower()
    return token.lower()


@st.cache_data(ttl=300)
def get_crypto_news(coin_name: str):
    try:
        params = {
            "auth_token": CRYPTO_PANIC_API_KEY,
            "public": "true",
            "filter": "rising",
            "currencies": coin_name.upper(),
        }
        r = requests.get(f"{CRYPTO_PANIC_API_URL}/posts/", params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("results", [])[:5]
    except Exception as e:
        st.error(f"Error fetching news: {e}")
        return []


@st.cache_data(ttl=60)
def get_price_from_binance(symbol: str):
    try:
        for pair in [f"{symbol}USDT", f"{symbol}BTC"]:
            try:
                r = requests.get(f"{BINANCE_API_URL}/ticker/price", params={"symbol": pair}, timeout=5)
                r.raise_for_status()
                data = r.json()
                if pair.endswith("BTC"):
                    btc = requests.get(f"{BINANCE_API_URL}/ticker/price", params={"symbol": "BTCUSDT"}, timeout=5)
                    btc.raise_for_status()
                    return float(data["price"]) * float(btc.json()["price"])
                return float(data["price"])
            except:
                continue
        raise Exception("No valid trading pair found")
    except Exception as e:
        st.error(f"Error fetching price: {e}")
        return None


@st.cache_data(ttl=300)
def get_market_data(coin_name: str):
    try:
        headers = {
            "Accepts": "application/json",
            "X-CMC_PRO_API_KEY": COINMARKETCAP_API_KEY,
        }
        params = {"start": "1", "limit": "50", "convert": "USD"}
        r = requests.get(f"{COINMARKETCAP_API_URL}/cryptocurrency/listings/latest",
                         headers=headers, params=params, timeout=10)
        r.raise_for_status()
        for coin in r.json().get("data", []):
            if coin["name"].lower() == coin_name.lower() or coin["symbol"].lower() == coin_name.lower():
                return {
                    "name":       coin["name"],
                    "symbol":     coin["symbol"],
                    "price":      coin["quote"]["USD"]["price"],
                    "market_cap": coin["quote"]["USD"]["market_cap"],
                    "rank":       coin["cmc_rank"],
                    "change_24h": coin["quote"]["USD"]["percent_change_24h"],
                }
        return None
    except Exception as e:
        st.error(f"Error fetching market data: {e}")
        return None


def generate_ai_response(coin_name, news, price_data, market_data):
    # Pre-format metrics
    if market_data:
        rank_str   = f"#{market_data['rank']}"
        cap_str    = f"${market_data['market_cap']:,.0f}"
        change_str = f"{market_data['change_24h']:.2f}%"
    else:
        rank_str = cap_str = change_str = "N/A"

    price_str = f"{price_data['price']}" if price_data else "N/A"
    news_str  = json.dumps([n["title"] for n in news], indent=2) if news else "No recent news"

    prompt = f"""
Analyze this cryptocurrency data and provide a concise summary:

Coin: {coin_name.capitalize()}

Current Price: {price_str}

Market Data:
- Rank: {rank_str}
- Market Cap: {cap_str}
- 24h Change: {change_str}

Latest News:
{news_str}

Provide key insights and trends in 150-200 words.
"""

    try:
        resp = ollama_client.generate(
            model=OLLAMA_MODEL,
            prompt=prompt,
            options={"temperature": 0.7}
        )
        return resp.get("response", "")
    except requests.exceptions.ConnectionError:
        st.error("Не удалось подключиться к серверу Ollama. Проверьте, запущен ли ollama serve.")
        return ""
    except ollama.OllamaError as e:
        st.error(f"Ollama вернул ошибку: {e}")
        return ""
    except Exception as e:
        st.error(f"Ошибка AI-анализа: {e}")
        return ""


# ─── Streamlit UI ───
st.set_page_config(page_title="AI Crypto Assistant", layout="wide")
st.title("🔮 AI Crypto Assistant")
st.markdown("Get real-time cryptocurrency data with AI-powered analysis")

query = st.text_input(
    "Ask about any cryptocurrency (e.g., 'Tell me about Bitcoin'):",
    placeholder="Bitcoin, ETH, Solana..."
)

if query:
    coin_name   = extract_coin(query)
    news        = get_crypto_news(coin_name)
    market_data = get_market_data(coin_name)

    # Unsupported coin
    if not market_data and not news:
        st.warning(f"К сожалению, монета ‘{coin_name}’ не поддерживается.")
        st.stop()

    # Determine symbol for price lookup
    if market_data and market_data.get("symbol"):
        symbol = market_data["symbol"]
    elif coin_name in TICKER_OVERRIDES:
        symbol = TICKER_OVERRIDES[coin_name]
    else:
        symbol = coin_name.upper()

    price = get_price_from_binance(symbol)

    with st.spinner(f"Analyzing {coin_name.capitalize()}..."):
        col1, col2 = st.columns([2, 1])

        # Left column: AI analysis
        with col1:
            st.subheader(f"{coin_name.capitalize()} Analysis")
            ai_text = generate_ai_response(
                coin_name,
                news,
                {"price": price} if price else None,
                market_data
            )
            st.markdown(ai_text)

        # Right column: metrics & news
        with col2:
            st.subheader("Detailed Metrics")
            if market_data:
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Current Price", f"${market_data['price']:,.2f}")
                    st.metric("Market Rank", f"#{market_data['rank']}")
                with c2:
                    st.metric("Market Cap", f"${market_data['market_cap']:,.0f}")
                    st.metric("24h Change", f"{market_data['change_24h']:.2f}%", delta_color="inverse")
            else:
                st.warning("No market data available.")

            if price and not market_data:
                st.metric("Current Price (Binance)", f"${price:,.2f}")

            if news:
                st.subheader("Top News Headlines")
                for item in news[:3]:
                    with st.expander(item["title"]):
                        st.caption(f"Source: {item.get('source', {}).get('title','Unknown')}")
                        st.write(item.get("url", "No link available"))
