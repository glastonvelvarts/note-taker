"""This is a bot that can summarize a transcript of a meeting"""

import asyncio
import os
import sys
import time

from playwright.async_api import async_playwright
from playwright_stealth import Stealth
from stt import create_stt_provider
from transcript import TranscriptCollector

if len(sys.argv) < 3:
    print("Usage: python bot.py <meeting_url> <user_id>")
    sys.exit(1)

MEET_URL = sys.argv[1]
USER_ID = sys.argv[2]
PROFILE_DIR = os.path.abspath(f"profiles/{USER_ID}")
LEAVE_LABELS = ("Leave call", "Leave meeting", "Hang up")

stealth = Stealth()


async def leave_control_visible(page) -> bool:
    for label in LEAVE_LABELS:
        try:
            if await page.get_by_role("button", name=label).is_visible():
                return True
        except Exception:
            continue
    return False


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

        provider = None
        collector = TranscriptCollector()
        transcript_base = f"transcripts/{USER_ID}_{int(time.time())}"
        collector.set_output(transcript_base)
        print(f"[bot] live transcript -> {transcript_base}.txt")

        try:
            with open("injected/rtc_capture.js") as f:
                rtc_script = f.read()
            await context.add_init_script(rtc_script)

            page = context.pages[0] if context.pages else await context.new_page()
            await page.add_init_script(rtc_script)
            await stealth.apply_stealth_async(page)
            page.on(
                "console",
                lambda msg: print(f"[browser/{msg.type}] {msg.text}"),
            )

            def handle_transcript(text: str, is_final: bool):
                tag = "[FINAL]" if is_final else "[...]"
                print(f"{tag} {text}")
                collector.add(text, is_final)

            provider = create_stt_provider(on_transcript=handle_transcript)
            await provider.start()

            audio_chunks = {"n": 0}

            async def handle_audio_chunk(b64_data: str):
                audio_chunks["n"] += 1
                if audio_chunks["n"] == 1 or audio_chunks["n"] % 50 == 0:
                    print(f"[bot] received audio chunk {audio_chunks['n']}")
                provider.push_audio(b64_data)

            await page.expose_function("send_audio_chunk", handle_audio_chunk)

            print(f"[bot] navigating to {meet_url}")
            await page.goto(meet_url, wait_until="domcontentloaded")
            await page.wait_for_timeout(3000)

            hooked = await page.evaluate("() => window.__rtcHooked === true")
            print(f"[bot] rtc hook active: {hooked}")

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
                if await leave_control_visible(page):
                    admitted = True
                    break
                await page.wait_for_timeout(5000)

            if not admitted:
                print("[bot] never got admitted, timing out")
                await page.screenshot(path="not_admitted.png")
                return

            print("[bot] admitted! now in the meeting.")
            print("[bot] stay in call — Ctrl+C to stop. Transcript updates live.")

            # Meet auto-hides the toolbar; don't treat one miss as "left"
            misses = 0
            while True:
                await page.wait_for_timeout(5_000)
                # nudge UI so leave control can reappear
                try:
                    await page.mouse.move(400, 700)
                except Exception:
                    pass

                if await leave_control_visible(page):
                    misses = 0
                    continue

                misses += 1
                if misses >= 4:  # ~20s without leave control
                    print("[bot] leave control missing ~20s, assuming left")
                    break
        except KeyboardInterrupt:
            print("[bot] interrupted, saving transcript")
        finally:
            try:
                if provider:
                    await provider.stop()
            finally:
                try:
                    await context.close()
                finally:
                    collector.save()
                    if not collector.entries:
                        print(
                            "[bot] transcript empty — no final speech segments "
                            "were received (audio tap or STT likely failed)"
                        )
                    else:
                        print(
                            f"[bot] saved {len(collector.entries)} segments -> "
                            f"{transcript_base}.json"
                        )


if __name__ == "__main__":
    asyncio.run(join_meeting(MEET_URL))
