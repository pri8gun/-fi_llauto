"""Automated Smartsheet form submission for the Woodfibre daily head count."""

import os
import smtplib
import sys
from datetime import date, datetime
from email.mime.text import MIMEText
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

FORM_URL = "https://app.smartsheet.com/b/form/2bc79c969d504a948791cb84fcf751e7"
TIMEZONE = "America/Vancouver"

WORK_RANGES_2026 = [
    (9, 16, 9, 29),
    (10, 7, 10, 20),
    (10, 28, 11, 10),
    (11, 18, 12, 1),
    (12, 9, 12, 22),
]


def get_field_values(today_str: str) -> list[str]:
    return [
        os.environ["WORKER_NAME"],
        "Dayshift",
        "Craft",
        "Mechanical",
        "7:30",
        today_str,
    ]


def is_work_day(today: date) -> bool:
    return any(
        date(today.year, m1, d1) <= today <= date(today.year, m2, d2)
        for m1, d1, m2, d2 in WORK_RANGES_2026
    )


def send_email(subject: str, body: str) -> None:
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    to_addr = os.environ.get("NOTIFY_EMAIL", smtp_user)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_addr], msg.as_string())


def collect_diagnostics(page, response_status=None) -> None:
    out = Path("diagnostics")
    out.mkdir(exist_ok=True)
    lines = [
        f"URL: {page.url}",
        f"TITLE: {page.title()}",
        f"RESPONSE_STATUS: {response_status}",
        f"FRAMES: {len(page.frames)}",
    ]
    for i, frame in enumerate(page.frames):
        lines.append(f"FRAME_{i}_URL: {frame.url}")
        try:
            lines.extend([
                f"FRAME_{i}_TITLE: {frame.title()}",
                f"FRAME_{i}_HTML_LENGTH: {len(frame.content())}",
                f"FRAME_{i}_INPUTS: {frame.locator('input').count()}",
                f"FRAME_{i}_BUTTONS: {frame.locator('button').count()}",
                f"FRAME_{i}_TEXTAREAS: {frame.locator('textarea').count()}",
                f"FRAME_{i}_SELECTS: {frame.locator('select').count()}",
                f"FRAME_{i}_BODY_TEXT: {frame.locator('body').inner_text(timeout=3000)[:3000]}",
            ])
        except Exception as exc:
            lines.append(f"FRAME_{i}_ERROR: {exc}")
    try:
        html = page.content()
        (out / "page.html").write_text(html, encoding="utf-8")
        lines.append(f"MAIN_HTML_LENGTH: {len(html)}")
    except Exception as exc:
        lines.append(f"MAIN_HTML_ERROR: {exc}")
    try:
        page.screenshot(path=str(out / "page.png"), full_page=True)
    except Exception as exc:
        lines.append(f"SCREENSHOT_ERROR: {exc}")
    (out / "diagnostic.txt").write_text("\n".join(lines), encoding="utf-8")


def find_form_fields(page):
    """Find the visible text inputs in the form, including custom combobox inputs."""
    fields = []
    for frame in page.frames:
        locator = frame.locator('input[type="text"]')
        for i in range(locator.count()):
            field = locator.nth(i)
            try:
                if field.is_visible() and field.is_enabled():
                    fields.append(field)
            except Exception:
                pass
    return fields


def fill_like_working_bookmarklet(page, values: list[str]) -> None:
    """Reproduce the user's proven browser-bookmarklet technique exactly.

    The bookmarklet does not click Smartsheet dropdown options. It uses the
    native HTMLInputElement value setter, dispatches input/change, then sends
    Enter. This is the interaction sequence known to work in the real browser.
    """
    result = page.evaluate(
        """
        ({values}) => {
            const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;
            const results = [];

            Object.keys(values).forEach((key) => {
                const i = Number(key);
                const el = inputs[i];
                if (!el) {
                    results.push({index: i, ok: false, reason: 'missing input'});
                    return;
                }
                el.focus();
                setter.call(el, values[i]);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter', bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keyup', {key: 'Enter', bubbles: true}));
                el.blur();
                results.push({index: i, value: el.value, name: el.name || '', ok: true});
            });
            return results;
        }
        """,
        {"values": {str(i): value for i, value in enumerate(values)}},
    )
    print(f"Bookmarklet-style results: {result}")
    page.wait_for_timeout(1500)

    actual = page.locator('input[type="text"]')
    current = []
    for i in range(min(6, actual.count())):
        current.append(actual.nth(i).input_value())
    print(f"Первые 6 text inputs после заполнения: {current}")

    # The sixth visible text input is the Date field. The seventh is a hidden
    # anti-spam/system field, so the first six are the actual form fields.
    for i, expected in enumerate(values):
        if i >= actual.count():
            raise RuntimeError(f"Не найден text input #{i + 1}.")
        got = actual.nth(i).input_value().strip()
        if got != expected:
            raise RuntimeError(
                f"Поле #{i + 1} не приняло значение. Ожидалось '{expected}', получено '{got}'."
            )


def fill_form(test_mode: bool = False) -> None:
    now_local = datetime.now(ZoneInfo(TIMEZONE))
    today_str = now_local.strftime("%m/%d/%Y")
    console_messages, page_errors, failed_requests = [], [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not test_mode)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        page.on("console", lambda msg: console_messages.append(f"{msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("requestfailed", lambda req: failed_requests.append(f"{req.url} :: {req.failure}"))
        response_status = None
        try:
            response = page.goto(FORM_URL, wait_until="domcontentloaded", timeout=60000)
            response_status = response.status if response else None
            page.wait_for_timeout(10000)
            collect_diagnostics(page, response_status)

            fields = find_form_fields(page)
            print(f"Найдено видимых text input полей: {len(fields)}")
            if len(fields) < 6:
                raise RuntimeError(
                    f"Найдено только {len(fields)} видимых text input полей, нужно минимум 6."
                )

            values = get_field_values(today_str)
            fill_like_working_bookmarklet(page, values)

            if test_mode:
                print("TEST_MODE=true: форма заполнена, Submit НЕ нажат.")
                page.screenshot(path="diagnostics/filled-form.png", full_page=True)
                return

            page.get_by_role("button", name="Submit").click(timeout=15000)
            page.wait_for_timeout(3000)
        except Exception:
            try:
                collect_diagnostics(page, response_status)
                with open("diagnostics/diagnostic.txt", "a", encoding="utf-8") as f:
                    f.write("\nCONSOLE_MESSAGES:\n" + "\n".join(console_messages[-100:]))
                    f.write("\nPAGE_ERRORS:\n" + "\n".join(page_errors[-100:]))
                    f.write("\nFAILED_REQUESTS:\n" + "\n".join(failed_requests[-100:]))
            except Exception:
                pass
            raise
        finally:
            browser.close()


def main() -> int:
    now_local = datetime.now(ZoneInfo(TIMEZONE))
    today = now_local.date()
    test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"

    if test_mode:
        print(f"TEST_MODE включён. Локальное время: {now_local.isoformat()}")
        fill_form(test_mode=True)
        return 0

    if now_local.hour != 7:
        print(f"Локальное время {now_local.isoformat()} — не 7 утра, выходим.")
        return 0

    if not is_work_day(today):
        print(f"{today} не входит в рабочие диапазоны — форма не отправляется.")
        return 0

    try:
        fill_form(test_mode=False)
    except Exception as exc:
        send_email(
            "Smartsheet Autofill — ОШИБКА",
            f"Не удалось отправить форму за {today}.\n\nОшибка: {exc}",
        )
        raise

    send_email(
        "Smartsheet Autofill — форма отправлена",
        f"Форма Woodfibre Daily Head Count успешно отправлена за {today}.",
    )
    print(f"Форма за {today} успешно отправлена.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
