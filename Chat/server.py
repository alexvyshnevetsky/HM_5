import asyncio
import logging
import httpx
import websockets
import names
import json
from datetime import datetime, timedelta
from websockets import WebSocketServerProtocol
from websockets.exceptions import ConnectionClosedOK
from aiofile import AIOFile
from aiopath import AsyncPath

logging.basicConfig(level=logging.INFO)


class HttpError(Exception):
    pass


async def request(url: str) -> dict | str:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            r.raise_for_status()
            return r.json()
    except httpx.ReadTimeout:
        return "⏳ Server took too long to respond. Try again later."
    except httpx.HTTPStatusError as e:
        return f"❌ HTTP Error: {e.response.status_code}"
    except httpx.RequestError as e:
        return f"⚠️ Request failed: {str(e)}"


async def log_request(days, currency, result):
    """Logs exchange rate requests to a JSON file asynchronously."""
    log_entry = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "days_requested": days,
        "currency_requested": currency if currency else "EUR, USD",
        "result": result
    }

    log_file = AsyncPath("exchange_log.json")

    if await log_file.exists():
        async with AIOFile(log_file, "r") as afp:
            try:
                content = await afp.read()
                logs = json.loads(content) if content else []
            except json.JSONDecodeError:
                logs = []
    else:
        logs = []

    logs.append(log_entry)

    async with AIOFile(log_file, "w") as afp:
        await afp.write(json.dumps(logs, ensure_ascii=False, indent=4))


async def get_exchange(days=1, currency=None):
    """ Get exchange rates for the last 'days' days. """
    if int(days) > 10:
        return "Request cannot be older than 10 days."

    results = []
    for i in range(int(days)):
        date = datetime.now() - timedelta(days=i)
        formatted_date = date.strftime("%d.%m.%Y")

        url = f'https://api.privatbank.ua/p24api/exchange_rates?date={formatted_date}'
        response = await request(url)

        if isinstance(response, str):
            return response

        formatted_data = {formatted_date: {}}
        target_currencies = {"EUR", "USD"}
        if currency:
            target_currencies.add(currency.upper())

        for rate in response.get('exchangeRate', []):
            curr = rate.get('currency')
            if curr in target_currencies:
                sale = rate.get('saleRate', rate.get('saleRateNB'))
                purchase = rate.get('purchaseRate', rate.get('purchaseRateNB'))

                if sale and purchase:
                    formatted_data[formatted_date][curr] = {
                        'sale': sale,
                        'purchase': purchase
                    }

        results.append(formatted_data)

    await log_request(days, currency, results)

    return json.dumps(results, ensure_ascii=False, indent=4)


class Server:
    clients = set()

    async def register(self, ws: WebSocketServerProtocol):
        ws.name = names.get_full_name()
        self.clients.add(ws)
        logging.info(f'{ws.remote_address} connects')

    async def unregister(self, ws: WebSocketServerProtocol):
        self.clients.remove(ws)
        logging.info(f'{ws.remote_address} disconnects')

    async def send_to_clients(self, message: str):
        if self.clients:
            [await client.send(message) for client in self.clients]

    async def ws_handler(self, ws: WebSocketServerProtocol):
        await self.register(ws)
        try:
            await self.distribute(ws)
        except ConnectionClosedOK:
            pass
        finally:
            await self.unregister(ws)

    async def distribute(self, ws: WebSocketServerProtocol):
        async for message in ws:
            parts = message.split()
            command = parts[0].lower()

            if command == "exchange":
                days_ago = 1
                currency = None

                if len(parts) > 1:
                    if parts[1].isdigit():
                        days_ago = int(parts[1])
                        if len(parts) > 2:
                            currency = parts[2]
                    else:
                        currency = parts[1]

                exchange = await get_exchange(days_ago, currency)
                await self.send_to_clients(exchange)

            elif message == "Hello server":
                await self.send_to_clients("Привіт мої карапузи!")
            else:
                await self.send_to_clients(f"{ws.name}: {message}")


async def main():
    server = Server()
    async with websockets.serve(server.ws_handler, 'localhost', 8080):
        await asyncio.Future()  # run forever


if __name__ == '__main__':
    asyncio.run(main())
