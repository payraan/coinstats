from fastapi import FastAPI, HTTPException, Query, Request, Header, Depends
import requests
import os
import uvicorn
import time
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv
from pathlib import Path

# تعیین مسیر دقیق فایل .env
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(os.path.join(BASE_DIR, '.env'), override=True)

# دریافت API key
API_KEY = os.getenv("COINSTATS_API_KEY")
if not API_KEY:
    raise ValueError("❌ COINSTATS_API_KEY not found in environment variables")

app = FastAPI(
    title="CoinStats API",
    description="API for retrieving cryptocurrency data, news, and wallet information from CoinStats",
    version="1.0.0"
)

BASE_URL = "https://openapiv1.coinstats.app"

# نگهداری آمار درخواست‌ها
request_count = 0
last_reset = time.time()
REQUEST_LIMIT = 950000  # محدودیت ماهانه 1,000,000 با کمی حاشیه امن

@app.middleware("http")
async def track_requests(request: Request, call_next):
    global request_count, last_reset
    
    # بازنشانی شمارنده هر ماه (تقریبی)
    if time.time() - last_reset > 2592000:  # 30 روز = 2592000 ثانیه
        request_count = 0
        last_reset = time.time()
    
    # افزایش شمارنده درخواست‌ها (فقط برای درخواست‌های API واقعی نه مستندات و غیره)
    if not request.url.path.startswith(("/docs", "/openapi.json", "/redoc", "/favicon.ico", "/")):
        request_count += 1
        
        # بررسی محدودیت درخواست
        if request_count > REQUEST_LIMIT:
            return {
                "status_code": 429,
                "content": {"detail": "Monthly request limit reached. Please try again next month."}
            }
    
    response = await call_next(request)
    return response

def get_api_key():
    return API_KEY

@app.get("/")
def home():
    return {
        "message": "✅ CoinStats API is running!", 
        "version": "1.0.0",
        "documentation": "/docs",
        "requests_this_month": request_count,
        "monthly_limit": "1,000,000 credits",
        "rate_limit": "5 requests per second",
        "status": "Free API plan with 1,000,000 credits per month"
    }

# Helper function to send requests to CoinStats API
async def fetch_from_coinstats(endpoint: str, params: Optional[Dict[str, Any]] = None, method: str = "GET"):
    url = f"{BASE_URL}/{endpoint}"
    
    headers = {
        "accept": "application/json",
        "X-API-KEY": API_KEY
    }
    
    print(f"🔍 Sending {method} request to: {url}")
    if params:
        print(f"🔍 With params: {params}")
    
    try:
        if method.upper() == "GET":
            response = requests.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = requests.post(url, headers=headers, json=params)
        elif method.upper() == "PATCH":
            response = requests.patch(url, headers=headers, json=params)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")
        
        print(f"✅ Response status: {response.status_code}")
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 400:
            print(f"❌ Bad Request: {response.text}")
            raise HTTPException(status_code=400, detail=f"❌ Bad Request: {response.text}")
        elif response.status_code == 401:
            print(f"❌ Unauthorized: {response.text}")
            raise HTTPException(status_code=401, detail="❌ Invalid API key or unauthorized access")
        elif response.status_code == 429:
            print(f"❌ Too Many Requests: {response.text}")
            raise HTTPException(status_code=429, detail="❌ Rate limit exceeded (5 requests per second). Please try again later.")
        else:
            print(f"⚠ Unexpected Error: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=f"⚠ Unexpected Error: {response.text[:200]}")
    except requests.RequestException as e:
        print(f"❌ Request error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"❌ Connection Error: {str(e)}")

# 1️⃣ Get all coins
@app.get("/coins")
async def get_coins(
    skip: Optional[int] = Query(0, description="Number of items to skip"),
    limit: Optional[int] = Query(20, description="Number of items to return"),
    currency: Optional[str] = Query("USD", description="Currency for prices")
):
    """
    Get a list of all cryptocurrencies with market data
    """
    params = {
        "skip": skip,
        "limit": limit,
        "currency": currency
    }
    
    return await fetch_from_coinstats("coins", params)

# 2️⃣ Get specific coin
@app.get("/coins/{coin_id}")
async def get_coin(
    coin_id: str,
    currency: Optional[str] = Query("USD", description="Currency for prices")
):
    """
    Get detailed information about a specific cryptocurrency
    """
    params = {
        "currency": currency
    }
    
    return await fetch_from_coinstats(f"coins/{coin_id}", params)

# 3️⃣ Get coin charts
@app.get("/coins/{coin_id}/charts")
async def get_coin_charts(
    coin_id: str,
    period: Optional[str] = Query("1m", description="Chart period (24h, 1w, 1m, 3m, 6m, 1y, all)"),
    currency: Optional[str] = Query("USD", description="Currency for prices")
):
    """
    Get chart data for a specific cryptocurrency
    """
    params = {
        "period": period,
        "currency": currency
    }
    
    return await fetch_from_coinstats(f"coins/{coin_id}/charts", params)

# 4️⃣ Get average price
@app.get("/coins/price/avg")
async def get_average_price(
    coin_id: Optional[str] = Query(None, description="Coin ID (e.g., bitcoin)"),
    currency: Optional[str] = Query("USD", description="Currency for prices")
):
    """
    Get average price across exchanges
    """
    params = {}
    
    if coin_id:
        params["coinId"] = coin_id
    if currency:
        params["currency"] = currency
    
    return await fetch_from_coinstats("coins/price/avg", params)

# 5️⃣ Get price by exchange
@app.get("/coins/price/exchange")
async def get_exchange_price(
    coin_id: Optional[str] = Query(None, description="Coin ID (e.g., bitcoin)"),
    exchange_id: Optional[str] = Query(None, description="Exchange ID (e.g., binance)"),
    currency: Optional[str] = Query("USD", description="Currency for prices")
):
    """
    Get price for a cryptocurrency on a specific exchange
    """
    params = {}
    
    if coin_id:
        params["coinId"] = coin_id
    if exchange_id:
        params["exchangeId"] = exchange_id
    if currency:
        params["currency"] = currency
    
    return await fetch_from_coinstats("coins/price/exchange", params)

# 6️⃣ Get exchange tickers
@app.get("/tickers/exchanges")
async def get_exchange_tickers(
    exchange: Optional[str] = Query(None, description="Exchange ID (e.g., binance)"),
    skip: Optional[int] = Query(0, description="Number of items to skip"),
    limit: Optional[int] = Query(20, description="Number of items to return")
):
    """
    Get ticker data from exchanges
    """
    params = {
        "skip": skip,
        "limit": limit
    }
    
    if exchange:
        params["exchange"] = exchange
    
    return await fetch_from_coinstats("tickers/exchanges", params)

# 7️⃣ Get market tickers
@app.get("/tickers/markets")
async def get_market_tickers(
    pair: Optional[str] = Query(None, description="Trading pair (e.g., BTC-USDT)"),
    exchange: Optional[str] = Query(None, description="Exchange ID (e.g., binance)"),
    skip: Optional[int] = Query(0, description="Number of items to skip"),
    limit: Optional[int] = Query(20, description="Number of items to return")
):
    """
    Get market ticker data
    """
    params = {
        "skip": skip,
        "limit": limit
    }
    
    if pair:
        params["pair"] = pair
    if exchange:
        params["exchange"] = exchange
    
    return await fetch_from_coinstats("tickers/markets", params)

# 8️⃣ Get fiats
@app.get("/fiats")
async def get_fiats():
    """
    Get list of supported fiat currencies
    """
    return await fetch_from_coinstats("fiats")

# 9️⃣ Get markets
@app.get("/markets")
async def get_markets():
    """
    Get list of supported markets/exchanges
    """
    return await fetch_from_coinstats("markets")

# 🔟 Get currencies
@app.get("/currencies")
async def get_currencies():
    """
    Get list of all available currencies
    """
    return await fetch_from_coinstats("currencies")

# 1️⃣1️⃣ Get news sources
@app.get("/news/sources")
async def get_news_sources():
    """
    Get list of supported news sources
    """
    return await fetch_from_coinstats("news/sources")

# 1️⃣2️⃣ Get news
@app.get("/news")
async def get_news(
    skip: Optional[int] = Query(0, description="Number of items to skip"),
    limit: Optional[int] = Query(20, description="Number of items to return"),
    filter: Optional[str] = Query(None, description="Filter news by source, coin, or category")
):
    """
    Get cryptocurrency news articles
    """
    params = {
        "skip": skip,
        "limit": limit
    }
    
    if filter:
        params["filter"] = filter
    
    return await fetch_from_coinstats("news", params)

# 1️⃣3️⃣ Get news by type
@app.get("/news/type/{type}")
async def get_news_by_type(
    type: str,
    skip: Optional[int] = Query(0, description="Number of items to skip"),
    limit: Optional[int] = Query(20, description="Number of items to return")
):
    """
    Get news articles by type (e.g., handpicked)
    """
    params = {
        "skip": skip,
        "limit": limit
    }
    
    return await fetch_from_coinstats(f"news/type/{type}", params)

# 1️⃣4️⃣ Get specific news article
@app.get("/news/{news_id}")
async def get_news_article(news_id: str):
    """
    Get a specific news article by ID
    """
    return await fetch_from_coinstats(f"news/{news_id}")

# 1️⃣5️⃣ Get supported blockchains for wallet
@app.get("/wallet/blockchains")
async def get_wallet_blockchains():
    """
    Get list of supported blockchains for wallet tracking
    """
    return await fetch_from_coinstats("wallet/blockchains")

# 1️⃣6️⃣ Get wallet balance
@app.get("/wallet/balance")
async def get_wallet_balance(
    address: str = Query(..., description="Wallet address"),
    blockchain: str = Query(..., description="Blockchain (e.g., ethereum, bitcoin)")
):
    """
    Get balance for a specific wallet address
    """
    params = {
        "address": address,
        "blockchain": blockchain
    }
    
    return await fetch_from_coinstats("wallet/balance", params)

# 1️⃣7️⃣ Get wallet balances
@app.get("/wallet/balances")
async def get_wallet_balances(
    address: str = Query(..., description="Wallet address"),
    networks: str = Query("all", description="Networks to include (comma-separated or 'all')")
):
    """
    Get balances for a wallet across multiple networks
    """
    params = {
        "address": address,
        "networks": networks
    }
    
    return await fetch_from_coinstats("wallet/balances", params)

# 1️⃣8️⃣ Get wallet transactions
@app.get("/wallet/transactions")
async def get_wallet_transactions(
    address: str = Query(..., description="Wallet address"),
    blockchain: str = Query(..., description="Blockchain (e.g., ethereum, bitcoin)"),
    skip: Optional[int] = Query(0, description="Number of items to skip"),
    limit: Optional[int] = Query(20, description="Number of items to return")
):
    """
    Get transaction history for a specific wallet
    """
    params = {
        "address": address,
        "blockchain": blockchain,
        "skip": skip,
        "limit": limit
    }
    
    return await fetch_from_coinstats("wallet/transactions", params)

# 1️⃣9️⃣ Update wallet transactions
@app.patch("/wallet/transactions")
async def update_wallet_transactions(
    address: str = Query(..., description="Wallet address"),
    blockchain: str = Query(..., description="Blockchain (e.g., ethereum, bitcoin)")
):
    """
    Update transaction data for a specific wallet
    """
    params = {
        "address": address,
        "blockchain": blockchain
    }
    
    return await fetch_from_coinstats("wallet/transactions", params, method="PATCH")

# Run the server
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8093))  # Using port 8093 as requested
    print(f"🚀 Starting CoinStats API server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
