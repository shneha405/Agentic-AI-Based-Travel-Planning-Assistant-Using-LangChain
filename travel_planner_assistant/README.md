# Agentic AI-Based Travel Planning Assistant Using LangChain

A Streamlit application based on the supplied project brief. It uses JSON datasets for flights, hotels and places; the free Open-Meteo API for weather; budget estimation; and a day-wise itinerary. An optional LangChain tool-calling agent uses OpenAI when an API key is configured.

## Included features
- Flight search by origin and destination; cheapest or fastest ranking.
- Hotel filtering by destination, nightly price and rating.
- Attraction discovery by destination and interest category.
- Live daily weather from Open-Meteo (no API key required).
- Estimated flight + hotel + food/local travel budget.
- Day-wise itinerary and downloadable JSON trip plan.
- Optional LangChain agent; deterministic tool workflow remains available without an LLM key.

## Files
- `app.py` — Streamlit application and five project tools.
- `requirements.txt` — Python dependencies.
- `data/flights.json`, `data/hotels.json`, `data/places.json` — illustrative starter datasets.

## Run locally
Use Python 3.10+:
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Enable LangChain agent mode
Set an OpenAI API key as `OPENAI_API_KEY` in your environment, or add it to Streamlit Community Cloud → App settings → Secrets:
```toml
OPENAI_API_KEY = "your-api-key"
```
Never commit the key to GitHub. Without a key, the app still runs using the built-in tool workflow.

## Replace demo datasets
The included JSON records are illustrative examples, not live flight or hotel inventory. Replace them with the larger project JSON datasets referenced in your brief. Keep each file as a JSON list.

Suggested fields:
- Flights: `airline`, `source`, `destination`, `price`, `departure_time`, `duration_hours`
- Hotels: `name`, `city`, `price_per_night`, `rating`, `area`
- Places: `name`, `city`, `type`, `rating`, `description`

The application also recognizes several alternative field names. City names should match the city names entered in the sidebar.

## Deploy on Streamlit Community Cloud
1. Upload the complete project folder to a GitHub repository.
2. Ensure `app.py`, `requirements.txt`, and `data/` are at the repository root.
3. Go to https://share.streamlit.io/ and sign in with GitHub.
4. Choose **Create app**, select your repository, branch and `app.py`.
5. Deploy. Add `OPENAI_API_KEY` in Secrets only if you want the LLM agent.
6. Push later code/data changes to GitHub; Streamlit Cloud will redeploy.

## How this meets the project brief
1. Flight Search Tool reads `flights.json` and ranks cheapest/fastest routes.
2. Hotel Recommendation Tool reads `hotels.json` and filters city, rating and price.
3. Places Discovery Tool reads `places.json` and filters destination and attraction type.
4. Weather Lookup Tool calls Open-Meteo.
5. Budget Estimation Tool totals flights, accommodation and per-day local expenses.
6. LangChain tool-calling agent can choose tools and explain its recommendations.
7. Output includes trip summary, flight, hotel, day-wise plan, weather, budget and JSON.

## Limitations
- Demo flight and hotel entries are static examples, not live fares or availability.
- Weather is live; forecast horizon depends on Open-Meteo.
- Costs are estimates and may omit taxes, fees and optional activities.
- The app suggests options; it does not book flights or hotels.
