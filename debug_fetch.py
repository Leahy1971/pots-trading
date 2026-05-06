import betfairlightweight as bfl
from datetime import datetime, timezone

MARKET_ID = "1.257760189"

c = bfl.APIClient('leahy.ray@gmail.com', '@RoyJames2009', app_key='ydBmfXxZMsfDWumi', certs='C:/certs')
c.login()
print("Logged in OK")

# Step 1 - catalogue
try:
    catalogue = c.betting.list_market_catalogue(
        filter=bfl.filters.market_filter(market_ids=[MARKET_ID]),
        market_projection=["RUNNER_DESCRIPTION", "EVENT", "MARKET_START_TIME"],
        max_results=1,
    )
    print("Catalogue OK:", catalogue)
    cat = catalogue[0]
    print("Market name:", cat.market_name)
    print("Start time:", cat.market_start_time)
    print("Runners:", [(r.selection_id, r.runner_name) for r in cat.runners])
except Exception as e:
    print("CATALOGUE ERROR:", e)
    raise

# Step 2 - book
try:
    books = c.betting.list_market_book(
        market_ids=[MARKET_ID],
        price_projection=bfl.filters.price_projection(
            price_data=["EX_BEST_OFFERS", "EX_TRADED"],
        ),
    )
    print("\nBook OK:", books)
    book = books[0]
    print("Status:", book.status)
    for r in book.runners:
        print(f"  Runner {r.selection_id}: status={r.status}, ex={r.ex}")
except Exception as e:
    print("BOOK ERROR:", e)
    raise

# Step 3 - seconds to start
start_dt = cat.market_start_time
now_utc = datetime.now(timezone.utc)
secs = (start_dt - now_utc).total_seconds()
print(f"\nSeconds to start: {secs:.0f}")
print("DONE - all steps passed")
