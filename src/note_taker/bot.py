import base64
import contextlib
import logging
import time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

from playwright.async_api import ConsoleMessage, Page, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright_stealth import Stealth

from .paths import data_dir
from .stt import SpeakerCallback
from .stt.router import SpeakerRouter
from .transcript import TranscriptCollector

logger = logging.getLogger(__name__)

RTC_SCRIPT = Path(__file__).parent / "injected" / "rtc_capture.js"
MUTE_LABELS = ("Turn off microphone", "Turn off camera")
JOIN_LABELS = ("Ask to join", "Join now")
LEAVE_LABELS = ("Leave call", "Leave meeting", "Hang up")
POLL_MS = 5000
ADMIT_POLLS = 60
LEFT_AFTER_MISSES = 4


class JoinError(RuntimeError):
    pass


def _log_capture_problem(message: ConsoleMessage) -> None:
    if message.text.startswith("[rtc]"):
        logger.warning(message.text)


def _in_english(meet_url: str) -> str:
    # Buttons are found by their English labels, whatever the account language is.
    parts = urlsplit(meet_url)
    query = dict(parse_qsl(parts.query)) | {"hl": "en"}
    return parts._replace(query=urlencode(query)).geturl()


async def _fail(page: Page, reason: str) -> None:
    screenshot = data_dir("screenshots") / f"{reason.replace(' ', '_')}.png"
    await page.screenshot(path=screenshot)
    raise JoinError(f"{reason}, see {screenshot}")


async def _click_first(page: Page, labels: tuple[str, ...], timeout: int) -> bool:
    for label in labels:
        with contextlib.suppress(PlaywrightError):
            await page.get_by_role("button", name=label).click(timeout=timeout)
            return True
    return False


async def _in_call(page: Page) -> bool:
    for label in LEAVE_LABELS:
        with contextlib.suppress(PlaywrightError):
            if await page.get_by_role("button", name=label).is_visible():
                return True
    return False


async def _wait_until_admitted(page: Page) -> None:
    for _ in range(ADMIT_POLLS):
        if await _in_call(page):
            return
        await page.wait_for_timeout(POLL_MS)
    await _fail(page, "not admitted")


async def _wait_until_left(page: Page) -> None:
    # Meet auto-hides the toolbar; don't treat one miss as "left"
    misses = 0
    while misses < LEFT_AFTER_MISSES:
        await page.wait_for_timeout(POLL_MS)
        # nudge UI so leave control can reappear
        with contextlib.suppress(PlaywrightError):
            await page.mouse.move(400, 700)
        misses = 0 if await _in_call(page) else misses + 1


async def join_meeting(
    meet_url: str,
    profile: str,
    on_transcript: SpeakerCallback | None = None,
    stt_mode: str | None = None,
) -> TranscriptCollector:
    """Join a Google Meet call and transcribe it until the call ends or the task is cancelled."""
    collector = TranscriptCollector(data_dir("transcripts") / f"{profile}_{int(time.time())}")

    def handle_transcript(text: str, is_final: bool, speaker: str) -> None:
        collector.add(text, is_final, speaker)
        if on_transcript:
            on_transcript(text, is_final, speaker)

    router = SpeakerRouter(handle_transcript, stt_mode)
    await router.start()
    try:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=data_dir("profiles") / profile,
                channel="chrome",
                locale="en-US",
                headless=False,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--disable-blink-features=AutomationControlled",
                ],
                ignore_default_args=["--enable-automation"],
                permissions=["camera", "microphone"],
            )
            try:
                await context.add_init_script(path=RTC_SCRIPT)
                page = context.pages[0] if context.pages else await context.new_page()
                await Stealth().apply_stealth_async(page)
                page.on("console", _log_capture_problem)
                await page.expose_function(
                    "send_audio_chunk",
                    lambda b64_data, source: router.push_audio(base64.b64decode(b64_data), source),
                )

                await page.goto(_in_english(meet_url), wait_until="domcontentloaded")
                await page.wait_for_timeout(3000)
                for label in MUTE_LABELS:
                    await _click_first(page, (label,), timeout=3000)

                if not await _click_first(page, JOIN_LABELS, timeout=5000):
                    await _fail(page, "join button not found")

                logger.info("waiting to be admitted")
                await _wait_until_admitted(page)
                logger.info("in the meeting, transcript -> %s", collector.txt_path)
                await _wait_until_left(page)
            finally:
                await context.close()
    finally:
        await router.stop()
    return collector
