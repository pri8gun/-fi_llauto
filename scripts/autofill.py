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
WORK_RANGES_2026 = [(9, 16, 9, 29), (10, 7, 10, 20), (10, 28, 11, 10), (11, 18, 12, 1), (12, 9, 12, 22)]


def get_field_values(date_str: str) -> list[str]:
    return [os.environ["WORKER_NAME"], "Dayshift", "Craft", "Mechanical", "7:30", date_str]


def is_work_day(today: date) -> bool:
    return any(date(today.year, a, b) <= today <= date(today.year, c, d) for a, b, c, d in WORK_RANGES_2026)


def send_email(subject: str, body: str) -> None:
    user, password = os.environ["SMTP_USER"], os.environ["SMTP_PASS"]
    to_addr = os.environ.get("NOTIFY_EMAIL", user)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user, to_addr
    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls(); server.login(user, password); server.sendmail(user, [to_addr], msg.as_string())


def diagnostics(page, status=None) -> None:
    out = Path("diagnostics"); out.mkdir(exist_ok=True)
    lines = [f"URL: {page.url}", f"TITLE: {page.title()}", f"RESPONSE_STATUS: {status}", f"FRAMES: {len(page.frames)}"]
    for i, frame in enumerate(page.frames):
        try:
            lines += [f"FRAME_{i}_URL: {frame.url}", f"FRAME_{i}_INPUTS: {frame.locator('input').count()}", f"FRAME_{i}_BUTTONS: {frame.locator('button').count()}", f"FRAME_{i}_BODY_TEXT: {frame.locator('body').inner_text(timeout=3000)[:4000]}"]
        except Exception as exc: lines.append(f"FRAME_{i}_ERROR: {exc}")
    try: (out / "page.html").write_text(page.content(), encoding="utf-8")
    except Exception: pass
    try: page.screenshot(path=str(out / "page.png"), full_page=True)
    except Exception: pass
    (out / "diagnostic.txt").write_text("\n".join(lines), encoding="utf-8")


def fill_like_bookmarklet(page, values: list[str]) -> None:
    result = page.evaluate("""
        ({values}) => {
            const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
            const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            return Object.keys(values).map(key => {
                const i = Number(key), el = inputs[i];
                if (!el) return {index:i, ok:false, reason:'missing input'};
                el.focus();
                setter.call(el, values[i]);
                el.dispatchEvent(new Event('input', {bubbles:true}));
                el.dispatchEvent(new Event('change', {bubbles:true}));
                el.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
                el.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true}));
                el.blur();
                return {index:i, value:el.value, ok:true};
            });
        }
    """, {"values": {str(i): v for i, v in enumerate(values)}})
    print(f"Bookmarklet-style results: {result}")
    page.wait_for_timeout(1500)


def read_form_state(page) -> dict:
    inputs = page.locator('input[type="text"]')
    combos = [x.strip() for x in page.locator('[role="combobox"]').all_inner_texts()]
    return {
        "name": inputs.nth(0).input_value().strip(),
        "dayshift": combos[0] if len(combos) > 0 else "",
        "craft": combos[1] if len(combos) > 1 else "",
        "discipline": inputs.nth(3).input_value().strip(),
        "time": inputs.nth(4).input_value().strip(),
        "date": inputs.nth(5).input_value().strip(),
    }


def run_form(test_mode=False, submit=False, date_override=None) -> None:
    now = datetime.now(ZoneInfo(TIMEZONE))
    date_str = date_override or now.strftime("%m/%d/%Y")
    values = get_field_values(date_str)
    errors, failed = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not test_mode)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed", lambda r: failed.append(f"{r.url} :: {r.failure}"))
        status = None
        try:
            response = page.goto(FORM_URL, wait_until="domcontentloaded", timeout=60000)
            status = response.status if response else None
            page.wait_for_timeout(10000)
            diagnostics(page, status)
            inputs = page.locator('input[type="text"]')
            if inputs.count() < 6: raise RuntimeError(f"Найдено только {inputs.count()} input[type=text].")

            fill_like_bookmarklet(page, values)
            state = read_form_state(page)
            expected = {"name":values[0], "dayshift":values[1], "craft":values[2], "discipline":values[3], "time":values[4], "date":values[5]}
            print(f"Состояние формы: {state}")
            if state != expected: raise RuntimeError(f"Ожидалось {expected}, получено {state}")

            submit_button = page.get_by_role("button", name="Submit")
            submit_button.wait_for(state="visible", timeout=15000)
            print(f"Submit visible={submit_button.is_visible()}, enabled={submit_button.is_enabled()}")

            if not submit:
                print("TEST_MODE=true: форма заполнена, Submit НЕ нажат.")
                page.screenshot(path="diagnostics/filled-form.png", full_page=True)
                return

            if not submit_button.is_enabled():
                raise RuntimeError("Submit остаётся disabled после заполнения всех полей.")

            print(f"НАЖИМАЮ РЕАЛЬНЫЙ SUBMIT. Дата формы: {date_str}")
            submit_button.click(timeout=15000)
            page.wait_for_timeout(5000)
            diagnostics(page, status)
            page.screenshot(path="diagnostics/submitted-form.png", full_page=True)
            body = page.locator("body").inner_text(timeout=5000)
            print(f"После Submit URL: {page.url}")
            print("Текст после Submit:\n" + body[:5000])
            (Path("diagnostics") / "submit-result.txt").write_text(body, encoding="utf-8")
        except Exception:
            try:
                diagnostics(page, status)
                with open("diagnostics/diagnostic.txt", "a", encoding="utf-8") as f:
                    f.write("\nEXPECTED_VALUES:\n" + repr(values))
                    f.write("\nFORM_STATE:\n" + repr(read_form_state(page)))
                    f.write("\nPAGE_ERRORS:\n" + repr(errors[-100:]))
                    f.write("\nFAILED_REQUESTS:\n" + repr(failed[-100:]))
            except Exception: pass
            raise
        finally:
            browser.close()


def main() -> int:
    now = datetime.now(ZoneInfo(TIMEZONE))
    today = now.date()
    test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"
    submit_test = os.environ.get("SUBMIT_TEST", "false").lower() == "true"

    if submit_test:
        # Explicit one-time real test requested by the user. This intentionally
        # uses a known correct past work date instead of today's date.
        print("SUBMIT_TEST=true: реальная тестовая отправка за 09/08/2026")
        run_form(test_mode=True, submit=True, date_override="09/08/2026")
        return 0
    if test_mode:
        print(f"TEST_MODE=true, Vancouver time: {now.isoformat()}")
        run_form(test_mode=True, submit=False)
        return 0
    if now.hour != 7:
        print(f"Локальное время {now.isoformat()} — не 7 утра, выходим.")
        return 0
    if not is_work_day(today):
        print(f"{today} не рабочий день — выходим.")
        return 0
    try:
        run_form(test_mode=False, submit=True)
    except Exception as exc:
        send_email("Smartsheet Autofill — ОШИБКА", f"Не удалось отправить форму за {today}.\n\nОшибка: {exc}")
        raise
    send_email("Smartsheet Autofill — форма отправлена", f"Форма Woodfibre Daily Head Count успешно отправлена за {today}.")
    return 0


if __name__ == "__main__": sys.exit(main())
