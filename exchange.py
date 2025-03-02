import sys
from datetime import datetime, timedelta
import httpx
import asyncio
import platform
import json


class HttpError(Exception):
    pass


class MyError(Exception):
    def __init__(self, message="Request cannot be older than 10 days"):
        super().__init__(message)
        print(message)


async def request(url: str):
    async with httpx.AsyncClient() as client:
        r = await client.get(url)
        if r.status_code == 200:
            return r.json()
        else:
            raise HttpError(f"Error status: {r.status_code} for {url}")


async def main(index_day, currency=None):
    if int(index_day) > 10:
        raise MyError
    else:
        d = datetime.now() - timedelta(days=int(index_day))
        shift = d.strftime("%d.%m.%Y")
        try:
            response = await request(f'https://api.privatbank.ua/p24api/exchange_rates?date={shift}')

            formatted_data = {shift: {}}
            target_currencies = {"EUR", "USD"}
            if currency:
                target_currencies.add(currency)

            for rate in response.get('exchangeRate', []):
                curr = rate.get('currency')
                if curr in target_currencies:
                    sale = rate.get('saleRate', rate.get('saleRateNB'))
                    purchase = rate.get('purchaseRate', rate.get('purchaseRateNB'))

                    if sale and purchase:
                        formatted_data[shift][curr] = {
                            'sale': sale,
                            'purchase': purchase
                        }

            return [formatted_data]

        except HttpError as err:
            print(err)
            return None


if __name__ == '__main__':
    if platform.system() == 'Windows':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    print(sys.argv)
    day = sys.argv[1]

    if len(sys.argv) > 2:
        currency = sys.argv[2]
    else:
        currency = None

    ex = asyncio.run(main(day, currency))
    print(ex)

    with open("exchange.json", "a+", encoding="utf-8") as file:
        file.write(json.dumps(ex, ensure_ascii=False, indent=4) + "\n")
