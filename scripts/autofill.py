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

# Two UTC schedules are needed because Vancouver switches between PDT and PST.
PDT_CRON = "30 14 * * *"  # 07:30 Vancouver while UTC-7
PST_CRON = "30 15 * * *"  # 07:30 Vancouver while UTC-8

WORK_RANGES_2026 = [
    (9, 16, 9, 29),
    (10, 7, 10, 20),
    (10, 28, 11, 10),
    (11, 18, 12, 1),
    (12, 9, 12, 22),
]


def get_field_values(date_str: str) -> list[str]:
    return [
        os.environ["WORKER_NAME"],
        "Dayshift",
        "Craft",
        "Mechanical",
        "7:30",
        date_str,
    ]


def is_work_day(today: date) -> bool:
    return any(
        date(today.year, m1, d1) <= today <= date(today.year, m2, d2)
        for m1, d1, m2, d2 in WORK_RANGES_2026
    )


def send_email(subject: str, body: str) -> None:
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to_addr = os.environ.get("NOTIFY_EMAIL", user)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_addr], msg.as_string())


def diagnostics(page, status=None) -> None:
    out = Path("diagnostics")
    out.mkdir(exist_ok=True)
    lines = [
        f"URL: {page.url}",
        f"TITLE: {page.title()}",
        f"RESPONSE_STATUS: {status}",
        f"FRAMES: {len(page.frames)}",
    ]
    for i, frame in enumerate(page.frames):
        try:
            lines.extend([
                f"FRAME_{i}_URL: {frame.url}",
                f"FRAME_{i}_INPUTS: {frame.locator('input').count()}",
                f"FRAME_{i}_BUTTONS: {frame.locator('button').count()}",
                f"FRAME_{i}_BODY_TEXT: {frame.locator('body').inner_text(timeout=3000)[:4000]}",
            ])
        except Exception as exc:
            lines.append(f"FRAME_{i}_ERROR: {exc}")

    try:
        (out / "page.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(out / "page.png"), full_page=True)
    except Exception:
        pass

    (out / "diagnostic.txt").write_text("\n".join(lines), encoding="utf-8")


def fill_like_bookmarklet(page, values: list[str]) -> None:
    """Use the same native-input technique as the proven browser bookmarklet."""
    result = page.evaluate(
        """
        ({values}) => {
            const inputs = Array.from(document.querySelectorAll('input[type="text"]'));
            const setter = Object.getOwnPropertyDescriptor(
                window.HTMLInputElement.prototype, 'value'
            ).set;

            return Object.keys(values).map(key => {
                const i = Number(key);
                const el = inputs[i];
                if (!el) return {index: i, ok: false, reason: 'missing input'};

                el.focus();
                setter.call(el, values[i]);
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.dispatchEvent(new KeyboardEvent('keydown', {
                    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                }));
                el.dispatchEvent(new KeyboardEvent('keyup', {
                    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
                }));
                el.blur();
                return {index: i, value: el.value, ok: true};
            });
        }
        """,
        {"values": {str(i): value for i, value in enumerate(values)}},
    )
    print(f"Bookmarklet-style results: {result}")
    page.wait_for_timeout(1500)


def read_form_state(page) -> dict:
    inputs = page.locator('input[type="text"]')
    combos = [text.strip() for text in page.locator('[role="combobox"]').all_inner_texts()]
    return {
        "name": inputs.nth(0).input_value().strip(),
        "dayshift": combos[0] if len(combos) > 0 else "",
        "craft": combos[1] if len(combos) > 1 else "",
        "discipline": inputs.nth(3).input_value().strip(),
        "time": inputs.nth(4).input_value().strip(),
        "date": inputs.nth(5).input_value().strip(),
    }


def expected_cron_for_vancouver(now: datetime) -> str:
    """Return the UTC cron that corresponds to 07:30 in Vancouver today."""
    offset = now.utcoffset()
    if offset is None:
        raise RuntimeError("Не удалось определить UTC offset для Vancouver.")
    offset_hours = int(offset.total_seconds() // 3600)
    if offset_hours == -7:
        return PDT_CRON
    if offset_hours == -8:
        return PST_CRON
    raise RuntimeError(f"Неожиданный UTC offset Vancouver: {offset_hours}")


def scheduled_run_is_allowed(now: datetime) -> bool:
    """Accept only the correct DST/PST cron and tolerate a modest GitHub delay."""
    scheduled_cron = os.environ.get("SCHEDULED_CRON", "").strip()
    expected_cron = expected_cron_for_vancouver(now)

    # The second daily UTC cron is only a DST/PST fallback. Ignore whichever
    # one does not correspond to 07:30 Vancouver on this date.
    if scheduled_cron and scheduled_cron != expected_cron:
        print(
            f"Этот cron ({scheduled_cron}) сейчас не соответствует 07:30 Vancouver; "
            f"ожидается {expected_cron}. Выходим без отправки."
        )
        return False

    # Normal start is 07:30. GitHub Actions can start scheduled jobs late, so
    # allow a 45-minute grace period through 08:15. The cron guard above keeps
    # the second UTC schedule from causing a duplicate submission.
    minutes = now.hour * 60 + now.minute
    if not (7 * 60 <= minutes <= 8 * 60 + 15):
        print(
            f"Локальное время {now.isoformat()} вне допустимого окна "
            "07:00–08:15 Vancouver. Выходим без отправки."
        )
        return False

    return True


def run_form(test_mode: bool = False) -> None:
    now = datetime.now(ZoneInfo(TIMEZONE))
    date_str = now.strftime("%m/%d/%Y")
    values = get_field_values(date_str)
    errors, failed = [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not test_mode)
        page = browser.new_page(viewport={"width": 1440, "height": 1200})
        page.on("pageerror", lambda exc: errors.append(str(exc)))
        page.on("requestfailed", lambda req: failed.append(f"{req.url} :: {req.failure}"))
        status = None

        try:
            response = page.goto(FORM_URL, wait_until="domcontentloaded", timeout=60000)
            status = response.status if response else None
            page.wait_for_timeout(10000)
            diagnostics(page, status)

            inputs = page.locator('input[type="text"]')
            if inputs.count() < 6:
                raise RuntimeError(f"Найдено только {inputs.count()} input[type=text].")

            fill_like_bookmarklet(page, values)
            state = read_form_state(page)
            expected = {
                "name": values[0],
                "dayshift": values[1],
                "craft": values[2],
                "discipline": values[3],
                "time": values[4],
                "date": values[5],
            }
            print(f"Состояние формы: {state}")
            if state != expected:
                raise RuntimeError(f"Ожидалось {expected}, получено {state}")

            submit_button = page.get_by_role("button", name="Submit")
            submit_button.wait_for(state="visible", timeout=15000)
            print(
                f"Submit visible={submit_button.is_visible()}, "
                f"enabled={submit_button.is_enabled()}"
            )

            if test_mode:
                print("TEST_MODE=true: форма заполнена, Submit НЕ нажат.")
                page.screenshot(path="diagnostics/filled-form.png", full_page=True)
                return

            if not submit_button.is_enabled():
                raise RuntimeError("Submit остаётся disabled после заполнения всех полей.")

            print(f"Отправляю форму. Дата: {date_str}")
            submit_button.click(timeout=15000)

            # The successful real test proved that Smartsheet redirects to
            # ?confirm=true and shows the success confirmation. Require both
            # before reporting success or sending the success email.
            page.wait_for_url("**?confirm=true", timeout=20000)
            page.get_by_text("Success!", exact=True).wait_for(state="visible", timeout=10000)
            page.get_by_text("We've captured your response.", exact=True).wait_for(
                state="visible", timeout=10000
            )

            diagnostics(page, status)
            body = page.locator("body").inner_text(timeout=5000)
            (Path("diagnostics") / "submit-result.txt").write_text(body, encoding="utf-8")
            page.screenshot(path="diagnostics/submitted-form.png", full_page=True)
            print(f"Smartsheet подтвердил отправку. URL: {page.url}")

        except Exception:
            try:
                diagnostics(page, status)
                with open("diagnostics/diagnostic.txt", "a", encoding="utf-8") as f:
                    f.write("\nEXPECTED_VALUES:\n" + repr(values))
                    try:
                        f.write("\nFORM_STATE:\n" + repr(read_form_state(page)))
                    except Exception as state_exc:
                        f.write("\nFORM_STATE_ERROR:\n" + repr(state_exc))
                    f.write("\nPAGE_ERRORS:\n" + repr(errors[-100:]))
                    f.write("\nFAILED_REQUESTS:\n" + repr(failed[-100:]))
            except Exception:
                pass
            raise
        finally:
            browser.close()


def main() -> int:
    now = datetime.now(ZoneInfo(TIMEZONE))
    today = now.date()
    test_mode = os.environ.get("TEST_MODE", "false").lower() == "true"
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")

    if test_mode:
        print(f"TEST_MODE=true, Vancouver time: {now.isoformat()}")
        run_form(test_mode=True)
        return 0

    if not is_work_day(today):
        print(f"{today} не рабочий день — форма не отправляется.")
        return 0

    if event_name == "schedule":
        if not scheduled_run_is_allowed(now):
            return 0
    else:
        # Safety for any non-test manual invocation: keep the same time window.
        minutes = now.hour * 60 + now.minute
        if not (7 * 60 <= minutes <= 8 * 60 + 15):
            print(
                f"Ручной production-запуск в {now.isoformat()} вне окна "
                "07:00–08:15 Vancouver — выходим."
            )
            return 0

    try:
        run_form(test_mode=False)
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
    print(f"Форма за {today} успешно отправлена и подтверждена Smartsheet.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
