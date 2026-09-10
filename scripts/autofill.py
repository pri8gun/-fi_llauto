"""Automated Smartsheet form submission for the Woodfibre daily head count."""

import os
import smtplib
import sys
from datetime import date, datetime
from email.mime.text import MIMEText
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
    for m1, d1, m2, d2 in WORK_RANGES_2026:
        if date(today.year, m1, d1) <= today <= date(today.year, m2, d2):
            return True
    return False


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


def find_form_fields(page):
    """Find visible editable fields in the page and any iframes."""
    candidates = []
    selectors = [
        'input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="file"]):not([type="submit"]):not([type="button"])',
        "textarea",
        '[contenteditable="true"]',
    ]

    for frame in page.frames:
        for selector in selectors:
            locator = frame.locator(selector)
            for i in range(locator.count()):
                field = locator.nth(i)
                try:
                    if field.is_visible() and field.is_enabled():
                        candidates.append(field)
                except Exception:
                    pass

    return candidates


def fill_form(test_mode: bool = False) -> None:
    now_local = datetime.now(ZoneInfo(TIMEZONE))
    today_str = now_local.strftime("%m/%d/%Y")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})

        try:
            page.goto(FORM_URL, wait_until="networkidle", timeout=60000)
            page.wait_for_timeout(5000)

            fields = find_form_fields(page)
            print(f"Найдено видимых редактируемых полей: {len(fields)}")

            if len(fields) < 6:
                # Diagnostic information helps if Smartsheet changes its form markup.
                print(f"Количество iframe: {len(page.frames)}")
                for index, frame in enumerate(page.frames):
                    try:
                        print(f"  iframe/frame {index}: {frame.url}")
                    except Exception:
                        pass
                page.screenshot(path="test-mode.png", full_page=True)
                raise RuntimeError(
                    f"Найдено только {len(fields)} видимых редактируемых полей, нужно минимум 6. "
                    "Скриншот сохранён как test-mode.png."
                )

            values = get_field_values(today_str)
            for i, value in enumerate(values):
                field = fields[i]
                field.scroll_into_view_if_needed()
                field.click()
                field.fill(value)
                field.dispatch_event("input")
                field.dispatch_event("change")
                print(f"Поле {i + 1}: {value}")

            page.wait_for_timeout(1500)

            # TEST_MODE: заполняем форму, но НЕ нажимаем Submit.
            if test_mode:
                print("TEST_MODE=true: форма заполнена, Submit НЕ нажат.")
                page.screenshot(path="test-mode.png", full_page=True)
                return

            page.get_by_role("button", name="Submit").click(timeout=15000)
            page.wait_for_timeout(3000)
        except Exception:
            try:
                page.screenshot(path="test-mode.png", full_page=True)
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
        try:
            fill_form(test_mode=True)
        except Exception as exc:
            print(f"TEST_MODE ошибка: {exc}")
            raise
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
            subject="Smartsheet Autofill — ОШИБКА",
            body=f"Не удалось отправить форму за {today}.\n\nОшибка: {exc}",
        )
        raise

    send_email(
        subject="Smartsheet Autofill — форма отправлена",
        body=f"Форма Woodfibre Daily Head Count успешно отправлена за {today}.",
    )
    print(f"Форма за {today} успешно отправлена.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
