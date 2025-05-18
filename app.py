import os
import streamlit as st
from dotenv import load_dotenv
import requests
import json
from datetime import datetime
import ollama  # or you can use openai package for GPT models

# Load environment variables
load_dotenv()

# Configuration
CRYPTO_PANIC_API_KEY = os.getenv('CRYPTO_PANIC_API_KEY')
COINMARKETCAP_API_KEY = os.getenv('COINMARKETCAP_API_KEY')
BINANCE_API_URL = "https://api.binance.com/api/v3"
COINMARKETCAP_API_URL = "https://pro-api.coinmarketcap.com/v1"
CRYPTO_PANIC_API_URL = "https://cryptopanic.com/api/v1"

# Initialize Ollama
# Make sure you have Ollama running locally with your preferred model
# e.g., ollama pull llama3  # or mistral, etc.

# Cache functions to avoid repeated API calls
@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_crypto_news(coin_name):
    """Fetch news from CryptoPanic"""
    try:
        params = {
            'auth_token': CRYPTO_PANIC_API_KEY,
            'public': 'true',
            'filter': 'rising',
            'currencies': coin_name.upper()
        }
        response = requests.get(f"{CRYPTO_PANIC_API_URL}/posts/", params=params)
        response.raise_for_status()
        news_data = response.json()
        return news_data['results'][:5]  # Return top 5 news items
    except Exception as e:
        st.error(f"Error fetching news: {e}")
        return []

@st.cache_data(ttl=60)  # Cache for 1 minute
def get_price_from_binance(symbol):
    """Fetch price from Binance"""
    try:
        response = requests.get(f"{BINANCE_API_URL}/ticker/price", params={'symbol': f"{symbol}USDT"})
        response.raise_for_status()
        return float(response.json()['price'])
    except:
        try:
            # Try with BTC pair if USDT fails
            response = requests.get(f"{BINANCE_API_URL}/ticker/price", params={'symbol': f"{symbol}BTC"})
            response.raise_for_status()
            btc_price = float(response.json()['price'])
            # Get BTC/USDT price to convert
            btc_usdt = requests.get(f"{BINANCE_API_URL}/ticker/price", params={'symbol': 'BTCUSDT'})
            btc_usdt.raise_for_status()
            return btc_price * float(btc_usdt.json()['price'])
        except Exception as e:
            st.error(f"Error fetching price from Binance: {e}")
            return None

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_market_data(coin_name):
    """Fetch market data from CoinMarketCap"""
    try:
        headers = {
            'Accepts': 'application/json',
            'X-CMC_PRO_API_KEY': COINMARKETCAP_API_KEY,
        }
        params = {
            'start': '1',
            'limit': '50',
            'convert': 'USD'
        }
        response = requests.get(f"{COINMARKETCAP_API_URL}/cryptocurrency/listings/latest", 
                              headers=headers, params=params)
        response.raise_for_status()
        
        data = response.json()
        for coin in data['data']:
            if coin['name'].lower() == coin_name.lower() or coin['symbol'].lower() == coin_name.lower():
                return {
                    'name': coin['name'],
                    'symbol': coin['symbol'],
                    'price': coin['quote']['USD']['price'],
                    'market_cap': coin['quote']['USD']['market_cap'],
                    'rank': coin['cmc_rank'],
                    'change_24h': coin['quote']['USD']['percent_change_24h']
                }
        return None
    except Exception as e:
        st.error(f"Error fetching market data: {e}")
        return None

def generate_ai_response(coin_name, news, price_data, market_data):
    """Generate a response using Ollama LLM"""
    prompt = f"""
    You are a helpful AI Crypto Assistant. Provide a concise and informative response based on the following data:
    
    User asked about: {coin_name}
    
    Latest News:
    {json.dumps(news, indent=2) if news else 'No news found'}
    
    Price Data:
    {json.dumps(price_data, indent=2) if price_data else 'No price data found'}
    
    Market Data:
    {json.dumps(market_data, indent=2) if market_data else 'No market data found'}
    
    Please summarize the information in a clear, professional manner, highlighting:
    - Current price and price change
    - Market cap and ranking
    - Key recent news developments
    - Any notable trends or insights
    
    Keep the response under 200 words.
    """
    
    try:
        response = ollama.generate(
            model='llama3',  # or whatever model you have
            prompt=prompt
        )
        return response['response']
    except Exception as e:
        st.error(f"Error generating AI response: {e}")
        return "I couldn't generate a response. Please try again later."

# Streamlit UI
st.title("🔮 AI Crypto Assistant")
st.markdown("Get live crypto market data, news, and AI-powered insights")

# User input
coin_query = st.text_input("Ask about any cryptocurrency (e.g., 'What's the latest news about Ethereum?')", 
                          placeholder="Ask about Bitcoin, Ethereum, etc.")

if coin_query:
    # Extract coin name from query
    coin_name = coin_query.split()[-1].lower()  # Simple extraction - could be improved
    
    with st.spinner(f"Fetching data for {coin_name}..."):
        # Get data from all sources
        news = get_crypto_news(coin_name)
        price = get_price_from_binance(coin_name.upper())
        market_data = get_market_data(coin_name)
        
        # Prepare price data
        price_data = {
            'price': price,
            'source': 'Binance',
            'timestamp': datetime.now().isoformat()
        } if price else None
        
        # Generate AI response
        ai_response = generate_ai_response(coin_name, news, price_data, market_data)
        
        # Display results
        st.subheader(f"Results for {coin_name.capitalize()}")
        
        if ai_response:
            st.markdown("### AI Summary")
            st.write(ai_response)
        
        st.markdown("### Detailed Data")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("#### Market Data")
            if market_data:
                st.metric("Price", f"${market_data['price']:,.2f}")
                st.metric("Market Cap", f"${market_data['market_cap']:,.0f}")
                st.metric("Rank", f"#{market_data['rank']}")
                st.metric("24h Change", f"{market_data['change_24h']:.2f}%")
            else:
                st.warning("No market data found")
        
        with col2:
            st.markdown("#### Latest News")
            if news:
                for item in news:
                    st.markdown(f"##### {item['title']}")
                    st.caption(f"Source: {item['source']['title']} - {item['published_at']}")
                    st.write(item['url'])
            else:
                st.warning("No recent news found")