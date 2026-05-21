"""
computer/apis.py — Free API integrations for Parker AI

All APIs wired here. Zero-key APIs work out of the box.
Keyed APIs read from .env — gracefully skip if key missing.

APIs included:
  ZERO KEY:
    - Open-Meteo        → weather, forecast, air quality, UV, historical
    - Open-Meteo Geo    → city name → coordinates
    - ip-api            → auto location from IP
    - WorldTimeAPI      → current time for any timezone
    - wttr.in           → fast one-line weather fallback
    - HackerNews        → top tech stories
    - REST Countries    → country info
    - Nager.Date        → public holidays
    - Open Library      → books & authors
    - Wikipedia         → factual summaries

  FREE KEY (from .env):
    - NewsData.io       → latest news by topic/country
    - Alpha Vantage     → stocks, crypto, forex
"""

import os
import time
import requests
from datetime import datetime, timedelta
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

NEWSDATA_KEY     = os.getenv("NEWSDATA_API_KEY", "")
ALPHA_VANTAGE_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")

# ── Simple in-memory cache (key → (timestamp, data)) ──────────────────────────
_cache: dict = {}
CACHE_TTL = {
    "weather":   600,    # 10 min
    "air":       600,
    "news":      900,    # 15 min
    "stock":     300,    # 5 min
    "location":  3600,   # 1 hr
    "holiday":   86400,  # 1 day
    "wiki":      86400,
    "country":   86400,
    "books":     86400,
    "hn":        600,
    "time":      60,     # 1 min
}

def _get_cache(key: str):
    if key in _cache:
        ts, data = _cache[key]
        category = key.split(":")[0]
        ttl = CACHE_TTL.get(category, 600)
        if time.time() - ts < ttl:
            return data
    return None

def _set_cache(key: str, data):
    _cache[key] = (time.time(), data)
    return data

def _get(url: str, params: dict = None, timeout: int = 8) -> dict | None:
    try:
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"[API] Request failed: {url} — {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
# LOCATION
# ══════════════════════════════════════════════════════════════════════════════

def get_my_location() -> dict:
    """Auto-detect current location from IP."""
    cached = _get_cache("location:auto")
    if cached:
        return cached

    data = _get("http://ip-api.com/json")
    if not data or data.get("status") != "success":
        return {"city": "Hanamkonda", "lat": 18.0, "lon": 79.6,
                "country": "India", "timezone": "Asia/Kolkata"}

    result = {
        "city":     data.get("city", "Unknown"),
        "region":   data.get("regionName", ""),
        "country":  data.get("country", ""),
        "lat":      data.get("lat", 0),
        "lon":      data.get("lon", 0),
        "timezone": data.get("timezone", "Asia/Kolkata"),
        "isp":      data.get("isp", ""),
    }
    return _set_cache("location:auto", result)


def geocode_city(city: str) -> dict | None:
    """Convert city name to lat/lon using Open-Meteo Geocoding."""
    cache_key = f"location:{city.lower()}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get("https://geocoding-api.open-meteo.com/v1/search",
                params={"name": city, "count": 1, "language": "en", "format": "json"})

    if not data or not data.get("results"):
        return None

    r = data["results"][0]
    result = {
        "city":    r.get("name", city),
        "country": r.get("country", ""),
        "lat":     r.get("latitude", 0),
        "lon":     r.get("longitude", 0),
        "timezone": r.get("timezone", "Asia/Kolkata"),
    }
    return _set_cache(cache_key, result)


def _resolve_location(city: str = None) -> dict:
    """Resolve location — use city if given, else auto-detect from IP."""
    if city:
        geo = geocode_city(city)
        if geo:
            return geo
    return get_my_location()


# ══════════════════════════════════════════════════════════════════════════════
# WEATHER
# ══════════════════════════════════════════════════════════════════════════════

def get_weather(city: str = None) -> dict:
    """
    Current weather + today's forecast from Open-Meteo.
    Falls back to wttr.in if Open-Meteo fails or geocoding fails.
    """
    if city:
        loc = geocode_city(city)
        if not loc:
            return _weather_fallback(city)
    else:
        loc = get_my_location()

    cache_key = f"weather:{loc['city'].lower()}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get("https://api.open-meteo.com/v1/forecast", params={
        "latitude":  loc["lat"],
        "longitude": loc["lon"],
        "current": ",".join([
            "temperature_2m", "relative_humidity_2m", "apparent_temperature",
            "weather_code", "wind_speed_10m", "wind_direction_10m",
            "precipitation", "cloud_cover", "pressure_msl", "visibility",
        ]),
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": ",".join([
            "temperature_2m_max", "temperature_2m_min", "sunrise", "sunset",
            "precipitation_sum", "weather_code", "uv_index_max",
            "precipitation_probability_max",
        ]),
        "timezone": loc.get("timezone", "Asia/Kolkata"),
        "forecast_days": 3,
    })

    if not data:
        return _weather_fallback(loc["city"])

    current = data.get("current", {})
    daily   = data.get("daily", {})
    hourly  = data.get("hourly", {})

    result = {
        "location":     loc["city"],
        "country":      loc.get("country", ""),
        "temperature":  current.get("temperature_2m"),
        "feels_like":   current.get("apparent_temperature"),
        "humidity":     current.get("relative_humidity_2m"),
        "wind_speed":   current.get("wind_speed_10m"),
        "precipitation":current.get("precipitation"),
        "cloud_cover":  current.get("cloud_cover"),
        "visibility":   current.get("visibility"),
        "condition":    _weather_code(current.get("weather_code", 0)),
        "sunrise":      daily.get("sunrise", [None])[0],
        "sunset":       daily.get("sunset", [None])[0],
        "uv_index":     daily.get("uv_index_max", [None])[0],
        "today_high":   daily.get("temperature_2m_max", [None])[0],
        "today_low":    daily.get("temperature_2m_min", [None])[0],
        "rain_chance":  daily.get("precipitation_probability_max", [None])[0],
        "forecast_3day": _parse_3day(daily),
    }
    return _set_cache(cache_key, result)


def get_air_quality(city: str = None) -> dict:
    """Air quality — PM2.5, PM10, NO2, O3, UV, AQI from Open-Meteo."""
    if city:
        loc = geocode_city(city)
        if not loc:
            return {"error": f"Could not resolve location: {city}", "location": city}
    else:
        loc = get_my_location()

    cache_key = f"air:{loc['city'].lower()}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get("https://air-quality-api.open-meteo.com/v1/air-quality", params={
        "latitude":  loc["lat"],
        "longitude": loc["lon"],
        "hourly":    "pm2_5,pm10,nitrogen_dioxide,ozone,us_aqi,uv_index",
        "forecast_days": 1,
        "timezone":  loc.get("timezone", "Asia/Kolkata"),
    })

    if not data:
        return {"error": "Air quality data unavailable"}

    hourly = data.get("hourly", {})
    # Get current hour index
    now_hour = datetime.now().hour
    idx = min(now_hour, len(hourly.get("us_aqi", [0])) - 1)

    def _val(key):
        arr = hourly.get(key, [])
        return arr[idx] if idx < len(arr) else None

    aqi = _val("us_aqi")
    result = {
        "location":  loc["city"],
        "aqi":       aqi,
        "aqi_label": _aqi_label(aqi),
        "pm2_5":     _val("pm2_5"),
        "pm10":      _val("pm10"),
        "no2":       _val("nitrogen_dioxide"),
        "ozone":     _val("ozone"),
        "uv_index":  _val("uv_index"),
        "uv_label":  _uv_label(_val("uv_index")),
    }
    return _set_cache(cache_key, result)


def get_historical_weather(city: str, date: str) -> dict:
    """
    Historical weather for a specific date (YYYY-MM-DD).
    Uses Open-Meteo ERA5 archive — goes back to 1940.
    """
    if city:
        loc = geocode_city(city)
        if not loc:
            return {"error": f"Could not resolve location: {city}", "location": city}
    else:
        loc = get_my_location()

    cache_key = f"weather:hist:{loc['city'].lower()}:{date}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get("https://archive-api.open-meteo.com/v1/archive", params={
        "latitude":   loc["lat"],
        "longitude":  loc["lon"],
        "start_date": date,
        "end_date":   date,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "timezone": loc.get("timezone", "Asia/Kolkata"),
    })

    if not data or not data.get("daily"):
        return {"error": f"No historical data for {date}"}

    daily = data["daily"]
    result = {
        "location": loc["city"],
        "date":     date,
        "high":     daily.get("temperature_2m_max", [None])[0],
        "low":      daily.get("temperature_2m_min", [None])[0],
        "rain_mm":  daily.get("precipitation_sum", [None])[0],
        "max_wind": daily.get("wind_speed_10m_max", [None])[0],
    }
    return _set_cache(cache_key, result)


def _weather_fallback(city: str) -> dict:
    """wttr.in fast fallback."""
    try:
        url_city = city.replace(" ", "+")
        r = requests.get(f"http://wttr.in/{url_city}?format=j1", timeout=5)
        if r.status_code == 200:
            d = r.json()
            cc = d["current_condition"][0]
            return {
                "location":    city,
                "temperature": int(cc["temp_C"]),
                "feels_like":  int(cc["FeelsLikeC"]),
                "humidity":    int(cc["humidity"]),
                "wind_speed":  int(cc["windspeedKmph"]),
                "condition":   cc["weatherDesc"][0]["value"],
                "source":      "wttr.in",
            }
    except Exception:
        pass
    return {"error": "Weather unavailable", "location": city}


# ══════════════════════════════════════════════════════════════════════════════
# TIME
# ══════════════════════════════════════════════════════════════════════════════

def get_time(timezone: str = "Asia/Kolkata") -> dict:
    """Current time for any timezone."""
    cache_key = f"time:{timezone}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get(f"http://worldtimeapi.org/api/timezone/{timezone}")
    if not data:
        # Local fallback
        now = datetime.now()
        return {"timezone": timezone, "datetime": now.isoformat(), "day": now.strftime("%A")}

    result = {
        "timezone": data.get("timezone"),
        "datetime": data.get("datetime"),
        "day":      data.get("day_of_week"),
        "utc_offset": data.get("utc_offset"),
    }
    return _set_cache(cache_key, result)


# ══════════════════════════════════════════════════════════════════════════════
# NEWS
# ══════════════════════════════════════════════════════════════════════════════

def get_news(query: str = None, category: str = None, country: str = "in") -> dict:
    """
    Latest news from NewsData.io.
    category options: technology, science, sports, entertainment, business, health
    """
    if not NEWSDATA_KEY:
        return {"error": "NEWSDATA_API_KEY not set in .env"}

    cache_key = f"news:{query or ''}:{category or ''}:{country}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    params = {
        "apikey":   NEWSDATA_KEY,
        "language": "en",
        "country":  country,
    }
    if query:
        params["q"] = query
    if category:
        params["category"] = category

    data = _get("https://newsdata.io/api/1/news", params=params)
    if not data or data.get("status") != "success":
        return {"error": "News fetch failed"}

    articles = data.get("results", [])[:8]
    result = {
        "total":    data.get("totalResults", 0),
        "articles": [
            {
                "title":       a.get("title", ""),
                "source":      a.get("source_name", ""),
                "published":   a.get("pubDate", ""),
                "description": (a.get("description") or "")[:200],
                "url":         a.get("link", ""),
                "category":    a.get("category", []),
            }
            for a in articles
        ],
    }
    return _set_cache(cache_key, result)


# ══════════════════════════════════════════════════════════════════════════════
# STOCKS & CRYPTO
# ══════════════════════════════════════════════════════════════════════════════

def get_stock(symbol: str) -> dict:
    """Stock price from Alpha Vantage."""
    if not ALPHA_VANTAGE_KEY:
        return {"error": "ALPHA_VANTAGE_API_KEY not set in .env"}

    cache_key = f"stock:{symbol.upper()}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get("https://www.alphavantage.co/query", params={
        "function": "GLOBAL_QUOTE",
        "symbol":   symbol.upper(),
        "apikey":   ALPHA_VANTAGE_KEY,
    })

    if not data or "Global Quote" not in data:
        return {"error": f"No data for {symbol}"}

    q = data["Global Quote"]
    result = {
        "symbol":   q.get("01. symbol"),
        "price":    q.get("05. price"),
        "change":   q.get("09. change"),
        "change_pct": q.get("10. change percent"),
        "high":     q.get("03. high"),
        "low":      q.get("04. low"),
        "volume":   q.get("06. volume"),
        "updated":  q.get("07. latest trading day"),
    }
    return _set_cache(cache_key, result)


def get_crypto(symbol: str = "BTC") -> dict:
    """Crypto price from Alpha Vantage (vs USD)."""
    if not ALPHA_VANTAGE_KEY:
        return {"error": "ALPHA_VANTAGE_API_KEY not set in .env"}

    cache_key = f"stock:crypto:{symbol.upper()}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get("https://www.alphavantage.co/query", params={
        "function":    "CURRENCY_EXCHANGE_RATE",
        "from_currency": symbol.upper(),
        "to_currency": "USD",
        "apikey":      ALPHA_VANTAGE_KEY,
    })

    if not data or "Realtime Currency Exchange Rate" not in data:
        return {"error": f"No crypto data for {symbol}"}

    r = data["Realtime Currency Exchange Rate"]
    result = {
        "symbol":    r.get("1. From_Currency Code"),
        "name":      r.get("2. From_Currency Name"),
        "price_usd": r.get("5. Exchange Rate"),
        "updated":   r.get("6. Last Refreshed"),
    }
    return _set_cache(cache_key, result)


# ══════════════════════════════════════════════════════════════════════════════
# HOLIDAYS
# ══════════════════════════════════════════════════════════════════════════════

def get_holidays(country_code: str = "IN", year: int = None) -> dict:
    """Public holidays for any country."""
    year = year or datetime.now().year
    cache_key = f"holiday:{country_code}:{year}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get(f"https://date.nager.at/api/v3/publicholidays/{year}/{country_code}")
    if not data:
        return {"error": "Holiday data unavailable"}

    today = datetime.now().date()
    upcoming = []
    for h in data:
        try:
            hdate = datetime.strptime(h["date"], "%Y-%m-%d").date()
            if hdate >= today:
                upcoming.append({
                    "date":  h["date"],
                    "name":  h["name"],
                    "local": h.get("localName", ""),
                    "days_away": (hdate - today).days,
                })
        except Exception:
            continue

    result = {
        "country":  country_code,
        "year":     year,
        "upcoming": upcoming[:5],
        "all":      [{"date": h["date"], "name": h["name"]} for h in data],
    }
    return _set_cache(cache_key, result)


# ══════════════════════════════════════════════════════════════════════════════
# HACKER NEWS
# ══════════════════════════════════════════════════════════════════════════════

def get_tech_news(limit: int = 5) -> dict:
    """Top tech stories from HackerNews."""
    cache_key = f"hn:top:{limit}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    ids = _get("https://hacker-news.firebaseio.com/v0/topstories.json")
    if not ids:
        return {"error": "HackerNews unavailable"}

    stories = []
    for story_id in ids[:limit * 2]:  # fetch extra in case some fail
        story = _get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json")
        if story and story.get("title") and story.get("type") == "story":
            stories.append({
                "title":  story.get("title"),
                "url":    story.get("url", f"https://news.ycombinator.com/item?id={story_id}"),
                "score":  story.get("score"),
                "comments": story.get("descendants", 0),
            })
        if len(stories) >= limit:
            break

    result = {"source": "HackerNews", "stories": stories}
    return _set_cache(cache_key, result)


# ══════════════════════════════════════════════════════════════════════════════
# COUNTRIES
# ══════════════════════════════════════════════════════════════════════════════

def get_country_info(name: str) -> dict:
    """Country facts — capital, currency, population, languages."""
    cache_key = f"country:{name.lower()}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get(f"https://restcountries.com/v3.1/name/{name}")
    if not data or not isinstance(data, list):
        return {"error": f"Country not found: {name}"}

    c = data[0]
    currencies = c.get("currencies", {})
    currency_str = ", ".join(
        f"{v.get('name')} ({k})" for k, v in currencies.items()
    )
    languages = ", ".join(c.get("languages", {}).values())

    result = {
        "name":       c.get("name", {}).get("common", name),
        "official":   c.get("name", {}).get("official", ""),
        "capital":    c.get("capital", [""])[0],
        "population": c.get("population"),
        "region":     c.get("region"),
        "subregion":  c.get("subregion"),
        "currency":   currency_str,
        "languages":  languages,
        "timezone":   c.get("timezones", [""])[0],
        "flag":       c.get("flag", ""),
    }
    return _set_cache(cache_key, result)


# ══════════════════════════════════════════════════════════════════════════════
# WIKIPEDIA
# ══════════════════════════════════════════════════════════════════════════════

def get_wiki_summary(topic: str) -> dict:
    """Wikipedia page summary for any topic."""
    cache_key = f"wiki:{topic.lower().replace(' ', '_')}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    slug = topic.replace(" ", "_")
    data = _get(f"https://en.wikipedia.org/api/rest_v1/page/summary/{slug}")
    if not data or data.get("type") == "https://mediawiki.org/wiki/HyperSwitch/errors/not_found":
        return {"error": f"No Wikipedia page found for: {topic}"}

    result = {
        "title":   data.get("title"),
        "summary": data.get("extract", "")[:500],
        "url":     data.get("content_urls", {}).get("desktop", {}).get("page", ""),
    }
    return _set_cache(cache_key, result)


# ══════════════════════════════════════════════════════════════════════════════
# BOOKS
# ══════════════════════════════════════════════════════════════════════════════

def search_books(query: str, limit: int = 5) -> dict:
    """Search books from Open Library."""
    cache_key = f"books:{query.lower()}"
    cached = _get_cache(cache_key)
    if cached:
        return cached

    data = _get("https://openlibrary.org/search.json",
                params={"q": query, "limit": limit, "fields": "title,author_name,first_publish_year,subject"})
    if not data:
        return {"error": "Book search failed"}

    books = [
        {
            "title":   b.get("title"),
            "authors": b.get("author_name", []),
            "year":    b.get("first_publish_year"),
            "subjects": b.get("subject", [])[:3],
        }
        for b in data.get("docs", [])[:limit]
    ]
    result = {"query": query, "books": books}
    return _set_cache(cache_key, result)


# ══════════════════════════════════════════════════════════════════════════════
# INTENT ENGINE — Option B: Parker specifies intent, backend combines APIs
# ══════════════════════════════════════════════════════════════════════════════

def resolve_intent(intent: str, params: dict = None) -> str:
    """
    Main entry point. Parker emits an intent string, this function
    decides which APIs to call, combines results, returns formatted string.

    Intent options:
        weather             → current weather + air quality + UV
        forecast            → 3-day forecast
        morning_briefing    → weather + news + holidays + tech news
        air_quality         → air quality only
        historical_weather  → weather on a specific past date
        news                → latest news (optional: topic, category)
        tech_news           → HackerNews top stories
        stock               → stock price
        crypto              → crypto price
        holiday             → upcoming holidays
        country             → country info
        wiki                → wikipedia summary
        books               → book search
        time                → current time for timezone
        location            → auto-detect current location
    """
    params = params or {}
    city    = params.get("city")
    topic   = params.get("topic", "")
    symbol  = params.get("symbol", "BTC")
    date    = params.get("date", "")
    country = params.get("country", "IN")
    timezone = params.get("timezone", "Asia/Kolkata")
    category = params.get("category", "")

    try:
        if intent == "weather":
            return _fmt_weather_full(city)

        elif intent == "forecast":
            return _fmt_forecast(city)

        elif intent == "morning_briefing":
            return _fmt_morning_briefing(city)

        elif intent == "air_quality":
            return _fmt_air_quality(city)

        elif intent == "historical_weather":
            return _fmt_historical(city or "Hanamkonda", date)

        elif intent == "news":
            return _fmt_news(topic, category, country)

        elif intent == "tech_news":
            return _fmt_tech_news()

        elif intent == "stock":
            return _fmt_stock(symbol)

        elif intent == "crypto":
            return _fmt_crypto(symbol)

        elif intent == "holiday":
            return _fmt_holidays(country)

        elif intent == "country":
            return _fmt_country(topic or city or "India")

        elif intent == "wiki":
            return _fmt_wiki(topic)

        elif intent == "books":
            return _fmt_books(topic)

        elif intent == "time":
            return _fmt_time(timezone)

        elif intent == "location":
            loc = get_my_location()
            return f"Current location: {loc['city']}, {loc['region']}, {loc['country']} (timezone: {loc['timezone']})"

        else:
            return f"[API] Unknown intent: {intent}"

    except Exception as e:
        return f"[API] Error resolving intent '{intent}': {e}"


# ══════════════════════════════════════════════════════════════════════════════
# FORMATTERS — combine multiple API results into clean strings for Parker
# ══════════════════════════════════════════════════════════════════════════════

def _fmt_weather_full(city: str = None) -> str:
    w  = get_weather(city)
    aq = get_air_quality(city)

    if "error" in w:
        return f"Weather unavailable: {w['error']}"

    lines = [f"Weather in {w['location']}:"]
    lines.append(f"  Condition : {w.get('condition', 'N/A')}")
    lines.append(f"  Temp      : {w.get('temperature')}°C (feels like {w.get('feels_like')}°C)")
    lines.append(f"  Humidity  : {w.get('humidity')}%")
    lines.append(f"  Wind      : {w.get('wind_speed')} km/h")
    lines.append(f"  Rain chance: {w.get('rain_chance')}%")
    lines.append(f"  High/Low  : {w.get('today_high')}°C / {w.get('today_low')}°C")
    lines.append(f"  Sunrise   : {_fmt_time_short(w.get('sunrise'))}")
    lines.append(f"  Sunset    : {_fmt_time_short(w.get('sunset'))}")

    if "aqi" in aq and aq["aqi"] is not None:
        lines.append(f"  AQI       : {aq['aqi']} ({aq.get('aqi_label', '')})")
        lines.append(f"  UV Index  : {aq.get('uv_index')} ({aq.get('uv_label', '')})")
        lines.append(f"  PM2.5     : {aq.get('pm2_5')} µg/m³")

    return "\n".join(lines)


def _fmt_forecast(city: str = None) -> str:
    w = get_weather(city)
    if "error" in w:
        return f"Forecast unavailable: {w['error']}"

    forecast = w.get("forecast_3day", [])
    lines = [f"3-Day Forecast for {w['location']}:"]
    for day in forecast:
        lines.append(
            f"  {day['date']}: {day['condition']} | "
            f"High {day['high']}°C / Low {day['low']}°C | "
            f"Rain {day['rain_chance']}%"
        )
    return "\n".join(lines)


def _fmt_morning_briefing(city: str = None) -> str:
    """Combines weather + air quality + news + holidays + tech news."""
    sections = []

    # Weather
    w  = get_weather(city)
    aq = get_air_quality(city)
    loc_name = w.get("location", city or "your location")
    today = datetime.now().strftime("%A, %B %d %Y")

    sections.append(f"=== MORNING BRIEFING — {today} ===\n")

    if "error" not in w:
        sections.append(
            f"WEATHER ({loc_name}):\n"
            f"  {w.get('condition')} | {w.get('temperature')}°C "
            f"(feels {w.get('feels_like')}°C) | Humidity {w.get('humidity')}%\n"
            f"  High {w.get('today_high')}°C / Low {w.get('today_low')}°C | "
            f"Rain chance {w.get('rain_chance')}%\n"
            f"  Sunrise {_fmt_time_short(w.get('sunrise'))} | "
            f"Sunset {_fmt_time_short(w.get('sunset'))}"
        )
        if "aqi" in aq and aq["aqi"] is not None:
            sections.append(
                f"  Air Quality: AQI {aq['aqi']} ({aq.get('aqi_label')}) | "
                f"UV {aq.get('uv_index')} ({aq.get('uv_label')})"
            )

    # Upcoming holiday check
    holidays = get_holidays("IN")
    upcoming = holidays.get("upcoming", [])
    if upcoming:
        next_h = upcoming[0]
        if next_h["days_away"] == 0:
            sections.append(f"\nHOLIDAY: Today is {next_h['name']} 🎉")
        elif next_h["days_away"] <= 3:
            sections.append(f"\nUPCOMING HOLIDAY: {next_h['name']} in {next_h['days_away']} day(s) ({next_h['date']})")

    # News headlines
    if NEWSDATA_KEY:
        news = get_news(country="in")
        articles = news.get("articles", [])
        if articles:
            sections.append("\nTOP NEWS:")
            for a in articles[:4]:
                sections.append(f"  • {a['title']} ({a['source']})")

    # Tech news
    hn = get_tech_news(limit=3)
    stories = hn.get("stories", [])
    if stories:
        sections.append("\nTECH (HackerNews):")
        for s in stories:
            sections.append(f"  • {s['title']} [{s['score']} pts]")

    return "\n".join(sections)


def _fmt_air_quality(city: str = None) -> str:
    aq = get_air_quality(city)
    if "error" in aq:
        return f"Air quality unavailable: {aq['error']}"

    lines = [f"Air Quality in {aq['location']}:"]
    lines.append(f"  AQI     : {aq['aqi']} — {aq.get('aqi_label')}")
    lines.append(f"  PM2.5   : {aq.get('pm2_5')} µg/m³")
    lines.append(f"  PM10    : {aq.get('pm10')} µg/m³")
    lines.append(f"  NO₂     : {aq.get('no2')} µg/m³")
    lines.append(f"  Ozone   : {aq.get('ozone')} µg/m³")
    lines.append(f"  UV Index: {aq.get('uv_index')} — {aq.get('uv_label')}")
    return "\n".join(lines)


def _fmt_historical(city: str, date: str) -> str:
    if not date:
        return "Please specify a date (YYYY-MM-DD)"
    h = get_historical_weather(city, date)
    if "error" in h:
        return h["error"]
    return (
        f"Weather in {h['location']} on {h['date']}:\n"
        f"  High: {h['high']}°C | Low: {h['low']}°C\n"
        f"  Rain: {h['rain_mm']} mm | Max Wind: {h['max_wind']} km/h"
    )


def _fmt_news(topic: str = None, category: str = None, country: str = "in") -> str:
    news = get_news(query=topic, category=category, country=country)
    if "error" in news:
        return news["error"]

    articles = news.get("articles", [])
    if not articles:
        return "No news articles found."

    label = f"News — {topic or category or 'Top Headlines'}"
    lines = [label + ":"]
    for a in articles:
        lines.append(f"  • [{a['source']}] {a['title']}")
        if a["description"]:
            lines.append(f"    {a['description']}")
    return "\n".join(lines)


def _fmt_tech_news() -> str:
    hn = get_tech_news(limit=5)
    if "error" in hn:
        return hn["error"]
    lines = ["Top Tech Stories (HackerNews):"]
    for s in hn.get("stories", []):
        lines.append(f"  • {s['title']} [{s['score']} pts, {s['comments']} comments]")
    return "\n".join(lines)


def _fmt_stock(symbol: str) -> str:
    s = get_stock(symbol)
    if "error" in s:
        return s["error"]
    return (
        f"{s['symbol']} Stock:\n"
        f"  Price  : ${s['price']}\n"
        f"  Change : {s['change']} ({s['change_pct']})\n"
        f"  High   : ${s['high']} | Low: ${s['low']}\n"
        f"  Updated: {s['updated']}"
    )


def _fmt_crypto(symbol: str) -> str:
    c = get_crypto(symbol)
    if "error" in c:
        return c["error"]
    return (
        f"{c['name']} ({c['symbol']}):\n"
        f"  Price  : ${float(c['price_usd']):,.2f} USD\n"
        f"  Updated: {c['updated']}"
    )


def _fmt_holidays(country: str = "IN") -> str:
    h = get_holidays(country)
    if "error" in h:
        return h["error"]
    upcoming = h.get("upcoming", [])
    if not upcoming:
        return "No upcoming holidays found."
    lines = [f"Upcoming Holidays ({country}):"]
    for holiday in upcoming:
        lines.append(f"  • {holiday['date']} — {holiday['name']} (in {holiday['days_away']} days)")
    return "\n".join(lines)


def _fmt_country(name: str) -> str:
    c = get_country_info(name)
    if "error" in c:
        return c["error"]
    return (
        f"{c['flag']} {c['name']} ({c['official']}):\n"
        f"  Capital   : {c['capital']}\n"
        f"  Population: {c['population']:,}\n"
        f"  Region    : {c['subregion']}, {c['region']}\n"
        f"  Currency  : {c['currency']}\n"
        f"  Languages : {c['languages']}\n"
        f"  Timezone  : {c['timezone']}"
    )


def _fmt_wiki(topic: str) -> str:
    w = get_wiki_summary(topic)
    if "error" in w:
        return w["error"]
    return f"{w['title']}:\n{w['summary']}\nSource: {w['url']}"


def _fmt_books(query: str) -> str:
    b = search_books(query)
    if "error" in b:
        return b["error"]
    books = b.get("books", [])
    if not books:
        return f"No books found for: {query}"
    lines = [f"Books matching '{query}':"]
    for book in books:
        authors = ", ".join(book["authors"]) if book["authors"] else "Unknown"
        lines.append(f"  • {book['title']} by {authors} ({book['year']})")
    return "\n".join(lines)


def _fmt_time(timezone: str) -> str:
    t = get_time(timezone)
    if "error" in t:
        return t["error"]
    dt_str = t.get("datetime", "")
    try:
        dt = datetime.fromisoformat(dt_str)
        formatted = dt.strftime("%I:%M %p, %A %B %d %Y")
    except Exception:
        formatted = dt_str
    return f"Time in {t['timezone']}: {formatted} (UTC{t.get('utc_offset', '')})"


# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _parse_3day(daily: dict) -> list:
    dates    = daily.get("time", [])
    highs    = daily.get("temperature_2m_max", [])
    lows     = daily.get("temperature_2m_min", [])
    codes    = daily.get("weather_code", [])
    rain     = daily.get("precipitation_probability_max", [])
    result = []
    for i in range(min(3, len(dates))):
        result.append({
            "date":       dates[i] if i < len(dates) else "",
            "high":       highs[i] if i < len(highs) else None,
            "low":        lows[i] if i < len(lows) else None,
            "condition":  _weather_code(codes[i] if i < len(codes) else 0),
            "rain_chance": rain[i] if i < len(rain) else None,
        })
    return result


def _weather_code(code: int) -> str:
    codes = {
        0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
        45: "Foggy", 48: "Icy fog", 51: "Light drizzle", 53: "Moderate drizzle",
        55: "Dense drizzle", 61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
        71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
        80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
        95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm",
    }
    return codes.get(code, f"Code {code}")


def _aqi_label(aqi) -> str:
    if aqi is None:
        return "Unknown"
    aqi = int(aqi)
    if aqi <= 50:   return "Good"
    if aqi <= 100:  return "Moderate"
    if aqi <= 150:  return "Unhealthy for sensitive groups"
    if aqi <= 200:  return "Unhealthy"
    if aqi <= 300:  return "Very Unhealthy"
    return "Hazardous"


def _uv_label(uv) -> str:
    if uv is None:
        return "Unknown"
    uv = float(uv)
    if uv < 3:   return "Low"
    if uv < 6:   return "Moderate"
    if uv < 8:   return "High"
    if uv < 11:  return "Very High"
    return "Extreme"


def _fmt_time_short(dt_str: str) -> str:
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str)
        return dt.strftime("%I:%M %p")
    except Exception:
        return dt_str