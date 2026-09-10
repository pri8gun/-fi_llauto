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
    """Save enough browser state to diagnose a blank/blocked Smartsheet page."""
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
            lines.append(f"FRAME_{i}_TITLE: {frame.title()}")
            lines.append(f"FRAME_{i}_HTML_LENGTH: {len(frame.content())}")
            lines.append(f"FRAME_{i}_INPUTS: {frame.locator('input').count()}")
            lines.append(f"FRAME_{i}_BUTTONS: {frame.locator('button').count()}")
            lines.append(f"FRAME_{i}_TEXTAREAS: {frame.locator('textarea').count()}")
            lines.append(f"FRAME_{i}_SELECTS: {frame.locator('select').count()}")
            lines.append(f"FRAME_{i}_BODY_TEXT: {frame.locator('body').inner_text(timeout=3000)[:3000]}")
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
    """Find visible editable text/date fields; custom dropdowns are handled by label below."""
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


def select_smartsheet_dropdown(frame, label: str, value: str) -> None:
    """Select a value from Smartsheet's custom role=combobox control by its label."""
    combo_input = frame.get_by_label(label, exact=True)
    combo_input.wait_for(state="visible", timeout=10000)
    combo_input.click()

    # Smartsheet renders the menu as a listbox/option set after the combobox opens.
    option = frame.get_by_role("option", name=value, exact=True)
    option.wait_for(state="visible", timeout=10000)
    option.click()

    # Confirm that the custom combobox now contains the selected value.
    if combo_input.input_value() != value:
        raise RuntimeError(
            f"Не удалось выбрать '{value}' в поле '{label}'. "
            f"Текущее значение: '{combo_input.input_value()}'."
        )

    print(f"Dropdown '{label}': {value}")


def fill_form(test_mode: bool = False) -> None:
    now_local = datetime.now(ZoneInfo(TIMEZONE))
    today_str = now_local.strftime("%m/%d/%Y")

    console_messages = []
    page_errors = []
    failed_requests = []

    with sync_playwright() as p:
        # Smartsheet can render differently in a headless browser. TEST_MODE runs
        # headed under Xvfb so we can verify the same page a normal browser sees.
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
            with open("diagnostics/diagnostic.txt", "a", encoding="utf-8") as f:
                f.write("\nCONSOLE_MESSAGES:\n" + "\n".join(console_messages[-100:]))
                f.write("\nPAGE_ERRORS:\n" + "\n".join(page_errors[-100:]))
                f.write("\nFAILED_REQUESTS:\n" + "\n".join(failed_requests[-100:]))

            fields = find_form_fields(page)
            print(f"Найдено видимых редактируемых полей: {len(fields)}")
            print(f"URL после загрузки: {page.url}")
            print(f"Title: {page.title()}")
            print(f"HTTP status: {response_status}")
            print(f"Frames: {len(page.frames)}")
            print(f"Console messages: {len(console_messages)}")
            print(f"Page errors: {len(page_errors)}")
            print(f"Failed requests: {len(failed_requests)}")

            if len(fields) < 6:
                raise RuntimeError(
                    f"Найдено только {len(fields)} видимых редактируемых полей, нужно минимум 6. "
                    "Подробная диагностика сохранена в diagnostics/."
                )

            values = get_field_values(today_str)

            # The first field is a normal text input.
            fields[0].scroll_into_view_if_needed()
            fields[0].click()
            fields[0].fill(values[0])
            fields[0].dispatch_event("input")
            fields[0].dispatch_event("change")
            print(f"Поле 1: {values[0]}")

            # These two are Smartsheet custom comboboxes, not ordinary text fields.
            # Filling their input with text does not select an actual option.
            form_frame = page.main_frame
            select_smartsheet_dropdown(form_frame, "Dayshift/Nightshift", values[1])
            select_smartsheet_dropdown(form_frame, "Staff/Craft/Visitor/Sub", values[2])

            # Remaining fields: Discipline, Time In, Date.
            for index, value in ((3, values[3]), (4, values[4]), (5, values[5])):
                field = fields[index]
                field.scroll_into_view_if_needed()
                field.click()
                field.fill(value)
                field.dispatch_event("input")
                field.dispatch_event("change")
                print(f"Поле {index + 1}: {value}")

            page.wait_for_timeout(1500)

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
