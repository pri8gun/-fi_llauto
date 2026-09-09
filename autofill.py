"""
Автоматическая отправка формы Smartsheet "Woodfibre Daily Head Count"
только в дни, входящие в заданные диапазоны рабочей ротации.

Запускается GitHub Actions по расписанию (см. .github/workflows/autofill.yml).
"""

import os
import smtplib
import sys
from datetime import date
from email.mime.text import MIMEText
from zoneinfo import ZoneInfo
from datetime import datetime

from playwright.sync_api import sync_playwright

# ---------- НАСТРОЙКИ ----------

FORM_URL = "https://app.smartsheet.com/b/form/2bc79c969d504a948791cb84fcf751e7"

def get_field_values() -> list[str]:
    """Значения полей формы. Имя берётся из секрета WORKER_NAME, а не
    хранится в коде — это важно, так как репозиторий публичный."""
    return [
        os.environ["WORKER_NAME"],  # Name
        "Dayshift",                 # Dayshift/Nightshift
        "Craft",                    # Staff/Craft/Visitor/Sub
        "Mechanical",                # Discipline/Department
        "7:30",                      # Time In
        # Date заполняется отдельно текущей датой ниже
    ]

TIMEZONE = "America/Vancouver"

# Диапазоны рабочих дней (включительно), год берётся из текущей даты по умолчанию.
# Формат: (месяц_начала, день_начала, месяц_конца, день_конца)
WORK_RANGES_2026 = [
    (9, 16, 9, 29),
    (10, 7, 10, 20),
    (10, 28, 11, 10),
    (11, 18, 12, 1),
    (12, 9, 12, 22),
]

# ---------- ЛОГИКА ДАТ ----------


def is_work_day(today: date) -> bool:
    for m1, d1, m2, d2 in WORK_RANGES_2026:
        start = date(today.year, m1, d1)
        # диапазон может переходить через смену месяца, но не через смену года
        end = date(today.year, m2, d2)
        if start <= today <= end:
            return True
    return False


# ---------- EMAIL ----------


def send_email(subject: str, body: str) -> None:
    smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    to_addr = os.environ.get("NOTIFY_EMAIL", smtp_user)

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = smtp_user
    msg["To"] = to_addr

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(smtp_user, [to_addr], msg.as_string())


# ---------- ЗАПОЛНЕНИЕ ФОРМЫ ----------


def fill_and_submit() -> None:
    now_local = datetime.now(ZoneInfo(TIMEZONE))
    today_str = now_local.strftime("%m/%d/%Y")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(FORM_URL, wait_until="networkidle")
        page.wait_for_timeout(4000)  # дать форме Smartsheet отрисоваться

        text_inputs = page.locator('input[type="text"]')
        count = text_inputs.count()
        if count < 6:
            raise RuntimeError(
                f"Ожидалось минимум 6 текстовых полей, найдено {count}. "
                "Возможно, структура формы изменилась."
            )

        values = get_field_values() + [today_str]
        for i, value in enumerate(values):
            field = text_inputs.nth(i)
            field.click()
            field.fill(value)
            field.dispatch_event("change")

        page.wait_for_timeout(500)

        submit_button = page.get_by_role("button", name="Submit")
        submit_button.click()

        page.wait_for_timeout(3000)  # дать формe время подтвердить отправку

        browser.close()


# ---------- ТОЧКА ВХОДА ----------


def main() -> int:
    now_local = datetime.now(ZoneInfo(TIMEZONE))
    today = now_local.date()

    # Скрипт может запускаться дважды в день (из-за перехода на летнее/зимнее
    # время в расписании), реально работаем только если сейчас 7 утра по Ванкуверу.
    if now_local.hour != 7:
        print(f"Локальное время {now_local.isoformat()} — не 7 утра, выходим.")
        return 0

    if not is_work_day(today):
        print(f"{today} не входит в рабочие диапазоны — форма не отправляется.")
        return 0

    try:
        fill_and_submit()
    except Exception as exc:  # noqa: BLE001
        send_email(
            subject="Smartsheet Autofill — ОШИБКА",
            body=(
                f"Не удалось отправить форму за {today}.\n\n"
                f"Ошибка: {exc}"
            ),
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
