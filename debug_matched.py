import betfairlightweight as bfl

c = bfl.APIClient('leahy.ray@gmail.com', '@RoyJames2009', app_key='ydBmfXxZMsfDWumi', certs='C:/certs')
c.login()
print("Logged in OK")

# Get a current live market
catalogues = c.betting.list_market_catalogue(
    filter=bfl.filters.market_filter(
        event_type_ids=["7"],
        market_countries=["GB"],
    ),
    market_projection=["RUNNER_DESCRIPTION", "EVENT", "MARKET_START_TIME"],
    sort="FIRST_TO_START",
    max_results=1,
)

if not catalogues:
    print("No GB markets found")
    exit()

cat = catalogues[0]
market_id = cat.market_id
print(f"Market: {cat.event.name} - {cat.market_name} - ID: {market_id}")

books = c.betting.list_market_book(
    market_ids=[market_id],
    price_projection=bfl.filters.price_projection(
        price_data=["EX_BEST_OFFERS", "EX_TRADED", "TRADED"],
    ),
)

book = books[0]
print(f"Market total matched: {book.total_matched}")

for r in book.runners:
    if r.status == "ACTIVE":
        ex = r.ex
        print(f"\nFirst active runner {r.selection_id}:")
        print(f"  total_matched: {r.total_matched}")
        print(f"  last_price_traded: {r.last_price_traded}")
        if ex:
            print(f"  back: {[(p.price, p.size) for p in ex.available_to_back[:3]]}")
            print(f"  lay:  {[(p.price, p.size) for p in ex.available_to_lay[:3]]}")
            print(f"  ex attributes: {[a for a in dir(ex) if not a.startswith('_')]}")
        break
