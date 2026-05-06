import betfairlightweight as bfl

c = bfl.APIClient('leahy.ray@gmail.com', '@RoyJames2009', app_key='ydBmfXxZMsfDWumi', certs='C:/certs')
c.login()
print("Logged in OK")

result = c.betting.list_market_catalogue(
    filter=bfl.filters.market_filter(market_ids=['1.257831672']),
    market_projection=['RUNNER_DESCRIPTION', 'EVENT', 'MARKET_START_TIME'],
    max_results=1,
)
print("Catalogue:", result)

if result:
    books = c.betting.list_market_book(
        market_ids=['1.257831672'],
    )
    print("Book:", books)
