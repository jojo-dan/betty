"""T-007 /model command E2E test"""
import asyncio
import time
from pathlib import Path
from dotenv import dotenv_values
from telethon import TelegramClient

env = dotenv_values(Path(__file__).parent / '.env.telethon')
API_ID = int(env['TELETHON_API_ID'])
API_HASH = env['TELETHON_API_HASH']
BOT_USERNAME = 're_betty_bot'
SESSION_FILE = str(Path(__file__).parent / 'telethon_session')
TIMEOUT = 60

async def wait_for_response(client, bot_entity, after_id, timeout=TIMEOUT):
    """Wait for a new message from the bot after a given message ID."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        messages = await client.get_messages(bot_entity, limit=10)
        for msg in messages:
            if msg.id > after_id and not msg.out:
                return msg
        await asyncio.sleep(2)
    return None

async def send_and_wait(client, bot, text, pause=5):
    """Send a message and wait for the bot's next response."""
    # Get current latest message ID
    latest = await client.get_messages(bot, limit=1)
    last_id = latest[0].id if latest else 0
    
    await client.send_message(bot, text)
    await asyncio.sleep(pause)  # give bot time to respond
    resp = await wait_for_response(client, bot, last_id)
    return resp

async def main():
    client = TelegramClient(SESSION_FILE, API_ID, API_HASH)
    await client.start()
    bot = await client.get_entity(BOT_USERNAME)
    results = []

    # Warmup: wait a moment after fresh session
    await asyncio.sleep(3)

    # Test 1: /model (no args)
    print('\n--- T1: /model (인자 없음) ---')
    resp = await send_and_wait(client, bot, '/model', pause=8)
    if resp:
        print(f'  응답: {resp.text}')
        # Could be SDK default or a previously set model
        ok = 'SDK default' in resp.text or 'claude-' in resp.text
        results.append(('T1 /model 조회', ok))
        print(f'  {"✅" if ok else "❌"}')
    else:
        print('  ❌ 응답 없음')
        results.append(('T1 /model 조회', False))

    await asyncio.sleep(5)

    # Test 2: /model sonnet
    print('\n--- T2: /model sonnet ---')
    resp = await send_and_wait(client, bot, '/model sonnet', pause=8)
    if resp:
        print(f'  응답: {resp.text}')
        ok = '변경' in resp.text and 'sonnet' in resp.text.lower()
        results.append(('T2 /model sonnet', ok))
        print(f'  {"✅" if ok else "❌"}')
    else:
        print('  ❌ 응답 없음')
        results.append(('T2 /model sonnet', False))

    await asyncio.sleep(5)

    # Test 3: /model (confirm)
    print('\n--- T3: /model (변경 확인) ---')
    resp = await send_and_wait(client, bot, '/model', pause=8)
    if resp:
        print(f'  응답: {resp.text}')
        ok = 'sonnet' in resp.text.lower()
        results.append(('T3 변경 확인', ok))
        print(f'  {"✅" if ok else "❌"}')
    else:
        print('  ❌ 응답 없음')
        results.append(('T3 변경 확인', False))

    await asyncio.sleep(5)

    # Test 4: /model badmodel
    print('\n--- T4: /model badmodel ---')
    resp = await send_and_wait(client, bot, '/model badmodel', pause=8)
    if resp:
        print(f'  응답: {resp.text}')
        ok = '알 수 없는' in resp.text and 'sonnet' in resp.text
        results.append(('T4 잘못된 모델', ok))
        print(f'  {"✅" if ok else "❌"}')
    else:
        print('  ❌ 응답 없음')
        results.append(('T4 잘못된 모델', False))

    await asyncio.sleep(5)

    # Test 5: /model haiku — reset to a different model
    print('\n--- T5: /model haiku ---')
    resp = await send_and_wait(client, bot, '/model haiku', pause=8)
    if resp:
        print(f'  응답: {resp.text}')
        ok = '변경' in resp.text and 'haiku' in resp.text.lower()
        results.append(('T5 /model haiku', ok))
        print(f'  {"✅" if ok else "❌"}')
    else:
        print('  ❌ 응답 없음')
        results.append(('T5 /model haiku', False))

    # Summary
    print('\n=== 결과 ===')
    all_pass = True
    for name, ok in results:
        print(f'  {"✅" if ok else "❌"} {name}')
        if not ok:
            all_pass = False
    print(f'\n{"ALL PASS" if all_pass else "SOME FAILED"}')

    await client.disconnect()
    return 0 if all_pass else 1

exit(asyncio.run(main()))
