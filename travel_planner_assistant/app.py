import os, json
from pathlib import Path
from datetime import date, timedelta
import requests
import pandas as pd
import streamlit as st

ROOT = Path(__file__).parent
DATA = ROOT / "data"

def load_records(filename):
    path = DATA / filename
    if not path.exists():
        return []
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            for key in ("data", "results", "records", "items"):
                if isinstance(obj.get(key), list):
                    return obj[key]
    except (OSError, json.JSONDecodeError) as exc:
        st.warning(f"Unable to load {filename}: {exc}")
    return []

def val(row, *keys, default=""):
    for key in keys:
        if row.get(key) not in (None, ""):
            return row[key]
    return default

def number(value, default=0):
    try:
        return float(str(value).replace(",", "").replace("₹", "").strip())
    except (ValueError, TypeError):
        return default

def rupees(value):
    return f"₹{value:,.0f}"

# Tool 1: Flight Search
def flight_search(origin, destination, records, preference):
    found = []
    for r in records:
        src = str(val(r, "source", "from", "origin", "departure_city")).lower()
        dst = str(val(r, "destination", "to", "arrival_city")).lower()
        if origin.lower() in src and destination.lower() in dst:
            x = dict(r)
            x["_price"] = number(val(r, "price", "fare", "cost", default=0))
            x["_duration"] = number(val(r, "duration_hours", "duration", default=999))
            found.append(x)
    return sorted(found, key=lambda x: x["_duration"] if preference == "Fastest" else x["_price"])

# Tool 2: Hotel Recommendation
def hotel_search(city, records, max_price, min_rating):
    found = []
    for r in records:
        hotel_city = str(val(r, "city", "destination", "location")).lower()
        price = number(val(r, "price_per_night", "price", "nightly_rate", "cost", default=0))
        rating = number(val(r, "rating", "stars", "guest_rating", default=0))
        if city.lower() in hotel_city and (not max_price or price <= max_price) and rating >= min_rating:
            x = dict(r); x["_price"] = price; x["_rating"] = rating
            found.append(x)
    return sorted(found, key=lambda x: (-x["_rating"], x["_price"]))

# Tool 3: Places / POI discovery
def places_search(city, records, category, limit):
    found = []
    for r in records:
        place_city = str(val(r, "city", "destination", "location")).lower()
        kind = str(val(r, "type", "category", "kind")).lower()
        if city.lower() in place_city and (category == "All" or category.lower() in kind):
            x = dict(r); x["_rating"] = number(val(r, "rating", "score", default=0))
            found.append(x)
    return sorted(found, key=lambda x: -x["_rating"])[:limit]

# Tool 4: Live weather via Open-Meteo (no API key)
@st.cache_data(ttl=1800, show_spinner=False)
def weather_search(city, start, end):
    geo = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                       params={"name": city, "count": 1, "language": "en", "format": "json"}, timeout=20)
    geo.raise_for_status()
    results = geo.json().get("results", [])
    if not results:
        return {"error": f"Could not find {city}."}
    loc = results[0]
    response = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": loc["latitude"], "longitude": loc["longitude"],
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "timezone": "auto", "start_date": start, "end_date": end
    }, timeout=20)
    response.raise_for_status()
    return {"location": loc, "daily": response.json().get("daily", {})}

def weather_name(code):
    labels = {0:"Clear sky",1:"Mainly clear",2:"Partly cloudy",3:"Overcast",45:"Fog",48:"Fog",
              51:"Light drizzle",53:"Drizzle",55:"Heavy drizzle",61:"Light rain",63:"Rain",
              65:"Heavy rain",71:"Light snow",73:"Snow",75:"Heavy snow",80:"Rain showers",
              81:"Rain showers",82:"Heavy showers",95:"Thunderstorm",96:"Thunderstorm with hail",
              99:"Thunderstorm with hail"}
    return labels.get(int(code), "Conditions unavailable")

# Tool 5: Budget estimation
def budget_estimate(flight, hotel_nightly, nights, daily_local, people):
    return {"Flights": flight * people, "Hotel": hotel_nightly * nights,
            "Food + local travel": daily_local * (nights + 1) * people}

def itinerary_builder(places, days):
    return [{"day": d, "places": places[(d-1)*2:d*2]} for d in range(1, days+1)]

def langchain_agent_enabled():
    key = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
    if not key:
        return None, "No OPENAI_API_KEY found. Showing the built-in tool workflow."
    try:
        from langchain.agents import create_agent
        from langchain.tools import tool
        from langchain_openai import ChatOpenAI

        flights, hotels, places = (load_records("flights.json"), load_records("hotels.json"), load_records("places.json"))

        @tool
        def flight_search_tool(origin: str, destination: str, preference: str = "Cheapest") -> str:
            """Search the project flights JSON for a route and rank cheapest or fastest."""
            return json.dumps(flight_search(origin, destination, flights, preference)[:5], default=str)

        @tool
        def hotel_recommendation_tool(city: str, max_nightly_price: float = 0) -> str:
            """Recommend hotels from hotels.json by city and nightly price."""
            return json.dumps(hotel_search(city, hotels, max_nightly_price, 0)[:5], default=str)

        @tool
        def places_discovery_tool(city: str, category: str = "All") -> str:
            """Find destination attractions from places.json."""
            return json.dumps(places_search(city, places, category, 12), default=str)

        @tool
        def weather_lookup_tool(city: str, start_date: str, end_date: str) -> str:
            """Get daily destination weather from Open-Meteo."""
            try: return json.dumps(weather_search(city, start_date, end_date))
            except Exception as exc: return json.dumps({"error": str(exc)})

        @tool
        def budget_estimation_tool(flight_cost: float, hotel_per_night: float, nights: int,
                                   daily_local_cost: float, travelers: int = 1) -> str:
            """Estimate flight, hotel and local expenses in INR."""
            return json.dumps(budget_estimate(flight_cost, hotel_per_night, nights, daily_local_cost, travelers))

        model = ChatOpenAI(model="gpt-4o-mini", temperature=0.2, api_key=key)
        agent = create_agent(model, [flight_search_tool, hotel_recommendation_tool,
                                     places_discovery_tool, weather_lookup_tool, budget_estimation_tool],
            system_prompt=("You are a careful travel expert. Use tools for dataset-backed travel options, "
            "weather and costs. Never claim anything is booked. Do not invent fares, ratings or weather. "
            "Create a practical day-wise itinerary and explain recommendations."))
        return agent, None
    except Exception as exc:
        return None, f"LangChain setup issue: {exc}. Built-in workflow will be used."

st.set_page_config(page_title="AI Travel Planner", page_icon="✈️", layout="wide")
st.title("✈️ Agentic AI Travel Planning Assistant")
st.caption("Personalized trip planning with flights, hotels, attractions, live weather and budget estimation.")

flights = load_records("flights.json")
hotels = load_records("hotels.json")
places = load_records("places.json")

with st.sidebar:
    st.header("Trip preferences")
    origin = st.text_input("Departure city", "Delhi")
    destination = st.text_input("Destination city", "Goa")
    today = date.today()
    start = st.date_input("Departure date", today + timedelta(days=14), min_value=today)
    end = st.date_input("Return date", today + timedelta(days=17), min_value=start)
    people = st.number_input("Travelers", 1, 20, 1)
    max_hotel = st.number_input("Maximum hotel price/night (₹)", min_value=0, value=5000, step=500)
    min_rating = st.slider("Minimum hotel rating", 0.0, 5.0, 3.5, 0.5)
    daily_cost = st.number_input("Food + local travel/person/day (₹)", min_value=0, value=1500, step=250)
    preference = st.selectbox("Flight preference", ["Cheapest", "Fastest"])
    category = st.selectbox("Attraction interest", ["All", "Beach", "Nature", "History", "Culture", "Adventure", "Shopping", "Food"])
    extra = st.text_area("Other preferences", placeholder="Family-friendly, relaxed pace, vegetarian food...")

nights = max((end-start).days, 1)
days = nights + 1
c1,c2,c3,c4 = st.columns(4)
c1.metric("Trip length", f"{days} days")
c2.metric("Travelers", int(people))
c3.metric("Flight records", len(flights))
c4.metric("Hotel / attraction records", f"{len(hotels)} / {len(places)}")

if not all([flights, hotels, places]):
    st.warning("One or more JSON datasets are empty. Replace the included demo files in the data folder with your project datasets.")

if st.button("✨ Generate my travel plan", type="primary", use_container_width=True):
    if not origin.strip() or not destination.strip() or end <= start:
        st.error("Enter valid departure and destination cities and a return date after departure.")
        st.stop()
    with st.spinner("Searching datasets and checking destination weather..."):
        flight_options = flight_search(origin, destination, flights, preference)
        hotel_options = hotel_search(destination, hotels, max_hotel, min_rating)
        poi_options = places_search(destination, places, category, days*2)
        try: weather = weather_search(destination, start.isoformat(), end.isoformat())
        except Exception as exc: weather = {"error": f"Weather service unavailable: {exc}"}

    chosen_flight = flight_options[0] if flight_options else {}
    chosen_hotel = hotel_options[0] if hotel_options else {}
    flight_price = number(val(chosen_flight, "price", "fare", "cost", default=0))
    hotel_price = number(val(chosen_hotel, "price_per_night", "price", "nightly_rate", "cost", default=0))
    budget = budget_estimate(flight_price, hotel_price, nights, daily_cost, int(people))
    total = sum(budget.values())

    st.divider()
    st.subheader(f"Your {days}-day trip to {destination.title()}")
    st.write(f"**Dates:** {start:%d %b %Y} – {end:%d %b %Y}  |  **From:** {origin.title()}  |  **Travelers:** {people}")
    left, right = st.columns(2)
    with left:
        st.markdown("#### ✈️ Flight recommendation")
        if chosen_flight:
            st.success(f"{val(chosen_flight, 'airline', 'carrier', default='Airline')} · {rupees(flight_price) if flight_price else 'Price not listed'}")
            st.write("Departure:", val(chosen_flight, "departure_time", "departure", default="Not listed"))
            st.write("Duration:", val(chosen_flight, "duration_hours", "duration", default="Not listed"))
            st.caption("Dataset recommendation only — no booking is made.")
            with st.expander("Compare flights"):
                st.dataframe(pd.DataFrame(flight_options).drop(columns=["_price","_duration"], errors="ignore"), use_container_width=True)
        else: st.warning("No route match in flights.json. Add a matching flight record.")
    with right:
        st.markdown("#### 🏨 Hotel recommendation")
        if chosen_hotel:
            st.success(f"{val(chosen_hotel, 'name', 'hotel_name', default='Hotel')} · {rupees(hotel_price)}/night")
            st.write("Rating:", val(chosen_hotel, "rating", "stars", default="Not listed"))
            st.write("Area:", val(chosen_hotel, "area", "address", "location", default="Not listed"))
            st.caption("Dataset recommendation only — no room is booked.")
            with st.expander("Compare hotels"):
                st.dataframe(pd.DataFrame(hotel_options).drop(columns=["_price","_rating"], errors="ignore"), use_container_width=True)
        else: st.warning("No hotel matched your destination and filters.")

    st.markdown("#### 🌦️ Weather forecast")
    if weather.get("daily"):
        daily = weather["daily"]
        rows = []
        for i, day in enumerate(daily.get("time", [])):
            codes = daily.get("weather_code", [])
            rows.append({"Date":day, "Forecast":weather_name(codes[i]) if i < len(codes) else "N/A",
                "Max °C":daily.get("temperature_2m_max", [None]*len(daily["time"]))[i],
                "Min °C":daily.get("temperature_2m_min", [None]*len(daily["time"]))[i],
                "Rain probability %":daily.get("precipitation_probability_max", [None]*len(daily["time"]))[i]})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else: st.info(weather.get("error", "Forecast not available."))

    st.markdown("#### 🗺️ Day-wise itinerary")
    if poi_options:
        for day_plan in itinerary_builder(poi_options, days):
            with st.expander(f"Day {day_plan['day']}", expanded=True):
                if not day_plan["places"]:
                    st.write("Explore the destination at a relaxed pace.")
                for idx, poi in enumerate(day_plan["places"]):
                    st.write(f"**{'Morning' if idx == 0 else 'Afternoon'}: {val(poi, 'name', 'place_name', 'attraction', default='Attraction')}**")
                    st.caption(f"{val(poi, 'type', 'category', default='Place')} · Rating: {val(poi, 'rating', default='Not listed')} · {val(poi, 'description', 'details', default='')}")
    else: st.warning("No matching attractions in places.json.")

    st.markdown("#### 💰 Estimated budget")
    budget_rows = [{"Expense": k, "Estimated cost": rupees(v)} for k,v in budget.items()]
    budget_rows.append({"Expense":"Estimated total", "Estimated cost":rupees(total)})
    st.dataframe(pd.DataFrame(budget_rows), use_container_width=True, hide_index=True)
    st.caption("Estimate only; excludes unprovided taxes, optional activities and incidental expenses.")

    # Optional agent invocation: tool-based deterministic results above remain visible regardless.
    agent, note = langchain_agent_enabled()
    agent_text = ""
    if agent:
        prompt = (f"Plan a {days}-day trip from {origin} to {destination}, {start} to {end}, "
                  f"for {people} travelers. Flight preference: {preference}; interests: {category}; "
                  f"other preferences: {extra}. Estimated dataset budget: {rupees(total)}. "
                  "Use the tools and explain the choices.")
        try:
            result = agent.invoke({"messages":[{"role":"user","content":prompt}]})
            for msg in reversed(result.get("messages", [])):
                if getattr(msg, "content", None):
                    agent_text = msg.content; break
        except Exception as exc: note = f"Agent call failed: {exc}"
    if agent_text:
        with st.expander("🤖 LangChain agent reasoning", expanded=True):
            st.markdown(agent_text)
    elif note:
        st.info(note)

    export = {"origin":origin, "destination":destination, "start_date":str(start), "end_date":str(end),
              "travelers":int(people), "flight_options":flight_options, "hotel_options":hotel_options,
              "attractions":poi_options, "weather":weather, "budget_inr":budget, "estimated_total_inr":total}
    st.download_button("⬇️ Download trip plan as JSON", json.dumps(export, indent=2, ensure_ascii=False, default=str),
                       "travel_plan.json", "application/json", use_container_width=True)

with st.expander("About this project"):
    st.markdown("""
    **Project:** Agentic AI-Based Travel Planning Assistant Using LangChain

    **Tools:** Flight Search, Hotel Recommendation, Places Discovery, Open-Meteo Weather Lookup and Budget Estimation.

    **Agent workflow:** Understand preferences → select tools → retrieve and rank options → construct itinerary → estimate cost → return readable output and JSON.

    Add `OPENAI_API_KEY` in Streamlit secrets to enable the LangChain tool-calling agent. The deterministic tool workflow works without a key.
    """)
