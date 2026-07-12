"""This is a bot that can summarize a transcript of a meeting"""

import asyncio
import os
import sys

from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from stt import DeepgramStreamer
if len(sys.argv) < 3:
    print("Usage: python bot.py <meeting_url> <user_id>")
    sys.exit(1)

MEET_URL = sys.argv[1]
USER_ID = sys.argv[2]
PROFILE_DIR = os.path.abspath(f"profiles/{USER_ID}")

stealth = Stealth()

async def join_meeting(meet_url: str):
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            channel="chrome",
            headless=False,
            args=[
                "--use-fake-ui-for-media-stream",
                "--disable-blink-features=AutomationControlled",
            ],
            ignore_default_args=["--enable-automation"],
            permissions=["camera", "microphone"],
        )

        with open("injected/rtc_capture.js") as f:
            await context.add_init_script(f.read())

        page = context.pages[0] if context.pages else await context.new_page()
        await stealth.apply_stealth_async(page)

        def handle_transcript(text: str, is_final: bool):
            tag = "[FINAL]" if is_final else "[...]"
            print(f"{tag} {text}")

        streamer = DeepgramStreamer(on_transcript=handle_transcript)
        await streamer.start()

        async def handle_audio_chunk(b64_data: str):
            streamer.push_audio(b64_data)

        await page.expose_function("send_audio_chunk", handle_audio_chunk)

        try:
            print(f"[bot] navigating to {meet_url}")
            await page.goto(meet_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            try:
                await page.get_by_role("button", name="Turn off microphone").click(timeout=3000)
            except Exception:
                print("[bot] mic toggle not found/already off")

            try:
                await page.get_by_role("button", name="Turn off camera").click(timeout=3000)
            except Exception:
                print("[bot] camera toggle not found/already off")

            joined = False
            for label in ["Ask to join", "Join now"]:
                try:
                    await page.get_by_role("button", name=label).click(timeout=5000)
                    print(f"[bot] clicked '{label}'")
                    joined = True
                    break
                except Exception:
                    continue

            if not joined:
                print("[bot] could not find join button, dumping screenshot")
                await page.screenshot(path="join_failed.png")
                return

            print("[bot] waiting to be admitted...")
            admitted = False
            for _ in range(60):
                try:
                    await page.get_by_role("button", name="Leave call").wait_for(timeout=5000)
                    admitted = True
                    break
                except Exception:
                    await page.wait_for_timeout(5000)

            if not admitted:
                print("[bot] never got admitted, timing out")
                await page.screenshot(path="not_admitted.png")
                return

            print("[bot] admitted! now in the meeting.")

            while True:
                await page.wait_for_timeout(10_000)
                leave_btn = page.get_by_role("button", name="Leave call")
                if not await leave_btn.is_visible():
                    print("[bot] looks like we got kicked/left the call")
                    break
        except KeyboardInterrupt:
            pass
        finally:
            await streamer.stop()
            await context.close()
            

if __name__ == "__main__":
    asyncio.run(join_meeting(MEET_URL))