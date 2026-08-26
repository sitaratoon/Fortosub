from pyrogram import Client
from aiohttp import web
import config
import asyncio

app = Client(
    "SubXChangeBot",
    api_id=config.API_ID,
    api_hash=config.API_HASH,
    bot_token=config.BOT_TOKEN,
    plugins=dict(root="plugins")
)

# Koyeb Health Check Handler
async def handle_ping(request):
    return web.Response(text="Bot is Alive!", status=200)

async def start_web_server():
    server = web.Application()
    server.router.add_get("/", handle_ping)
    server.router.add_get("/health", handle_ping)
    
    runner = web.AppRunner(server)
    await runner.setup()
    
    # Koyeb default PORT env variable use karega, fallback 8080 rahega
    port = int(config.os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Web server running on port {port}")

async def main():
    await start_web_server()
    await app.start()
    print("🤖 Bot is running...")
    await asyncio.Event().wait()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
    
