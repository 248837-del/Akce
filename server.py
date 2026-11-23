import html
import io
import json
import logging
import re
import math
import os
import base64
import unicodedata
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request as UrlRequest, urlopen

import segno


ROOT = Path(__file__).resolve().parent
PAGES_DIR = ROOT / "Akce"
GITHUB_API = "https://api.github.com"


class GithubApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


class SupabaseApiError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def github_settings():
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip().strip("/")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not repository or not token or "/" not in repository:
        return None
    return repository, token


def supabase_settings():
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return None
    return url, key


def supabase_request(method, path, url, key, data=None, prefer=None):
    body = None if data is None else json.dumps(data).encode("utf-8")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    request = UrlRequest(
        url + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            response_body = response.read()
            return json.loads(response_body.decode("utf-8")) if response_body else None
    except HTTPError as error:
        try:
            response_body = error.read()
        finally:
            error.close()
        try:
            response_data = json.loads(response_body.decode("utf-8"))
            message = (
                response_data.get("message", "Database request failed.")
                if isinstance(response_data, dict)
                else "Database request failed."
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = "Database request failed."
        raise SupabaseApiError(error.code, message) from error
    except URLError as error:
        raise SupabaseApiError(None, "Database service is unreachable.") from error


def get_shared_counters(event_slug):
    settings = supabase_settings()
    if not settings:
        raise SupabaseApiError(None, "Shared storage is not configured.")
    query = urlencode({
        "select": "cell_key,value",
        "event_slug": "eq." + event_slug,
    })
    rows = supabase_request(
        "GET",
        f"/rest/v1/event_counters?{query}",
        settings[0],
        settings[1],
    )
    return {row["cell_key"]: row["value"] for row in rows}


def save_shared_counters(event_slug, values, ignore_duplicates=False):
    settings = supabase_settings()
    if not settings:
        raise SupabaseApiError(None, "Shared storage is not configured.")
    rows = [
        {"event_slug": event_slug, "cell_key": cell_key, "value": value}
        for cell_key, value in values.items()
    ]
    if not rows:
        return
    query = urlencode({"on_conflict": "event_slug,cell_key"})
    resolution = "ignore-duplicates" if ignore_duplicates else "merge-duplicates"
    supabase_request(
        "POST",
        f"/rest/v1/event_counters?{query}",
        settings[0],
        settings[1],
        rows,
        f"resolution={resolution},return=minimal",
    )


def github_request(method, path, token, data=None):
    body = None if data is None else json.dumps(data).encode("utf-8")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Akce-app",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = UrlRequest(
        GITHUB_API + path,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        try:
            response_body = error.read()
        finally:
            error.close()
        try:
            response_data = json.loads(response_body.decode("utf-8"))
            message = (
                response_data.get("message", "GitHub request failed.")
                if isinstance(response_data, dict)
                else "GitHub request failed."
            )
        except (json.JSONDecodeError, UnicodeDecodeError):
            message = "GitHub request failed."
        raise GithubApiError(error.code, message) from error
    except URLError as error:
        raise GithubApiError(None, "GitHub API is unreachable.") from error


def list_github_pages(repository, token):
    owner, name = repository.split("/", 1)
    result = github_request(
        "GET",
        f"/repos/{quote(owner)}/{quote(name)}/contents/Akce",
        token,
    )
    return [
        {
            "title": item["name"][:-5],
            "path": "/Akce/" + item["name"],
        }
        for item in result
        if item.get("type") == "file" and item.get("name", "").endswith(".html")
    ]


def save_github_page(repository, token, filename, content):
    owner, name = repository.split("/", 1)
    path = f"/repos/{quote(owner)}/{quote(name)}/contents/Akce/{quote(filename)}"
    data = {
        "message": f"Vytvoření akce {filename[:-5]}",
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
    }
    github_request("PUT", path, token, data)


def read_github_page(repository, token, filename):
    owner, name = repository.split("/", 1)
    path = f"/repos/{quote(owner)}/{quote(name)}/contents/Akce/{quote(filename)}"
    result = github_request("GET", path, token)
    if not isinstance(result, dict) or result.get("encoding") != "base64":
        raise GithubApiError(None, "GitHub returned an invalid page.")
    return base64.b64decode(result["content"])


def make_slug(title):
    normalized = unicodedata.normalize("NFKD", title)
    plain = normalized.encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def iban_mod97(value):
    remainder = 0
    for character in value:
        if character.isdigit():
            digits = character
        elif "A" <= character <= "Z":
            digits = str(ord(character) - 55)
        else:
            raise ValueError("IBAN obsahuje neplatné znaky.")

        for digit in digits:
            remainder = (remainder * 10 + int(digit)) % 97
    return remainder


def normalize_account(account):
    if not isinstance(account, str):
        raise ValueError("Zadej číslo účtu nebo IBAN.")

    account = "".join(account.split()).upper()
    if re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", account):
        if iban_mod97(account[4:] + account[:4]) != 1:
            raise ValueError("Zadaný IBAN není platný.")
        return account

    match = re.fullmatch(r"(?:(\d{1,6})-)?(\d{1,10})/(\d{4})", account)
    if not match:
        raise ValueError("Použij IBAN nebo české číslo účtu ve tvaru 123456789/0100.")

    prefix = (match.group(1) or "").zfill(6)
    account_number = match.group(2).zfill(10)
    bank_code = match.group(3)
    bban = bank_code + prefix + account_number
    check_digits = 98 - iban_mod97(bban + "123500")
    return f"CZ{check_digits:02d}{bban}"


def build_spayd_payload(account, amount_halere, reference):
    if isinstance(amount_halere, bool) or not isinstance(amount_halere, int) or amount_halere <= 0:
        raise ValueError("Částka QR platby musí být kladná.")
    if not isinstance(reference, str) or not reference.strip() or len(reference) > 60:
        raise ValueError("Zpráva platby musí obsahovat 1 až 60 znaků.")
    if any(ord(character) < 32 or ord(character) == 127 for character in reference):
        raise ValueError("Zpráva platby obsahuje nepovolené znaky.")

    iban = normalize_account(account)
    amount = f"{amount_halere // 100}.{amount_halere % 100:02d}"
    message = quote(reference, safe="")
    return f"SPD*1.0*ACC:{iban}*AM:{amount}*CC:CZK*MSG:{message}"


def make_qr_svg(payload):
    qr = segno.make(payload, error="M", micro=False)
    output = io.BytesIO()
    qr.save(output, kind="svg", scale=6, border=4, xmldecl=False)
    return output.getvalue()


class ProjectHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", os.environ.get("CORS_ORIGIN", "*"))
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path
        state_match = re.fullmatch(r"/api/state/([a-z0-9]+(?:-[a-z0-9]+)*)", path)
        if state_match:
            try:
                self.send_json(200, {"values": get_shared_counters(state_match.group(1))})
            except SupabaseApiError as error:
                self.send_json(503, {"error": str(error)})
            except Exception:
                logging.exception("Unexpected error while reading shared counters")
                self.send_json(502, {"error": "Sdílené počítadla se nepodařilo načíst."})
            return

        page_match = re.fullmatch(r"/Akce/([a-z0-9]+(?:-[a-z0-9]+)*\.html)", path)
        settings = github_settings()
        if page_match and settings:
            try:
                body = read_github_page(settings[0], settings[1], page_match.group(1))
            except GithubApiError as error:
                if error.status == 404:
                    self.send_error(404, "Akce nebyla nalezena.")
                else:
                    self.send_json(502, {"error": "Stránku akce se nepodařilo načíst z GitHubu."})
                return

            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path == "/api/pages":
            settings = github_settings()
            try:
                if settings:
                    pages = list_github_pages(*settings)
                else:
                    pages = []
                    if PAGES_DIR.exists():
                        for file in sorted(PAGES_DIR.glob("*.html")):
                            pages.append({
                                "title": file.stem,
                                "path": "/Akce/" + file.name,
                            })
                self.send_json(200, pages)
            except Exception:
                self.send_json(502, {"error": "Seznam akcí se nepodařilo načíst."})
            return

        super().do_GET()

    def do_POST(self):
        path = urlsplit(self.path).path
        state_match = re.fullmatch(r"/api/state/([a-z0-9]+(?:-[a-z0-9]+)*)", path)
        if state_match:
            self.save_shared_counter_changes(state_match.group(1))
            return
        if path == "/api/qr":
            self.create_qr()
            return
        if path != "/api/pages":
            self.send_error(404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 10000:
                self.send_json(400, {"error": "Neplatný požadavek."})
                return

            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                self.send_json(400, {"error": "Požadavek musí obsahovat údaje akce."})
                return

            title = data.get("title")
            event_date = data.get("date", "")

            if not isinstance(title, str) or not title.strip():
                self.send_json(400, {"error": "Zadej název akce."})
                return

            title = title.strip()

            account = data.get("account", "")
            if not isinstance(account, str):
                self.send_json(400, {"error": "Číslo účtu není platné."})
                return
            account = account.strip()
            if account:
                try:
                    account = normalize_account(account)
                except ValueError as error:
                    self.send_json(400, {"error": str(error)})
                    return

            if not isinstance(event_date, str):
                self.send_json(400, {"error": "Datum není platné."})
                return

            if event_date:
                try:
                    date.fromisoformat(event_date)
                except ValueError:
                    self.send_json(400, {"error": "Zadané datum není platné."})
                    return

            participants = data.get("participants", [])
            if not isinstance(participants, list) or not all(
                isinstance(name, str) for name in participants
            ):
                self.send_json(400, {"error": "Seznam účastníků není platný."})
                return

            payer = data.get("payer", "")
            if not isinstance(payer, str) or (
                payer and payer not in participants
            ) or (participants and not payer):
                self.send_json(400, {"error": "Vyber platného plátce ze seznamu účastníků."})
                return
            if payer and not account:
                self.send_json(400, {"error": "Zadej účet vybraného plátce pro QR platby."})
                return

            shopping_list = data.get("shoppingList")
            items = (
                shopping_list.get("items")
                if isinstance(shopping_list, dict)
                else None
            )

            valid_items = (
                isinstance(shopping_list, dict)
                and shopping_list.get("currency") == "CZK"
                and isinstance(items, list)
                and len(items) > 0
                and all(
                    isinstance(item, dict)
                    and isinstance(item.get("product"), str)
                    and item["product"].strip()
                    and isinstance(item.get("quantity"), (int, float))
                    and not isinstance(item.get("quantity"), bool)
                    and math.isfinite(item["quantity"])
                    and item["quantity"] > 0
                    and isinstance(item.get("line_total_czk"), (int, float))
                    and not isinstance(item.get("line_total_czk"), bool)
                    and math.isfinite(item["line_total_czk"])
                    and item["line_total_czk"] >= 0
                    for item in items
                )
            )

            if not valid_items:
                self.send_json(400, {"error": "Nákupní seznam není platný."})
                return

            participant_headers = "".join(
                f'<th scope="col">{html.escape(name)}</th>'
                for name in participants
            )

            shopping_rows = []
            for item in items:
                product = item["product"]
                quantity = item["quantity"]
                total_halere = round(item["line_total_czk"] * 100)
                participant_cells = "".join(
                    f'<td><input type="number" class="input podil-kolecko" '
                    f'min="0" max="999" step="1" value="0"  '
                    f'data-participant-index="{index}" '
                    f'aria-label="{html.escape(name)}: {html.escape(product)}"></td>'
                    for index, name in enumerate(participants)
                )

                shopping_rows.append(
                    f'<tr data-total-halere="{total_halere}">'
                    f'<th scope="row">{html.escape(product)}</th>'
                    f'<td>{quantity}</td>'
                    f'<td>{total_halere / 100:.2f} Kč</td>'
                    f'{participant_cells}</tr>'
                )

            checklist_rows_html = "\n".join(shopping_rows)

            slug = make_slug(title)
            if not slug:
                self.send_json(
                    400,
                    {"error": "Název musí obsahovat písmena nebo čísla."},
                )
                return

            settings = github_settings()
            filename = slug + ".html"
            if settings:
                existing_pages = list_github_pages(*settings)
                existing_names = {page["path"].split("/")[-1] for page in existing_pages}
                suffix = 2
                while filename in existing_names:
                    filename = slug + "-" + str(suffix) + ".html"
                    suffix += 1
            else:
                PAGES_DIR.mkdir(exist_ok=True)
                page_file = PAGES_DIR / filename
                suffix = 2
                while page_file.exists():
                    filename = slug + "-" + str(suffix) + ".html"
                    page_file = PAGES_DIR / filename
                    suffix += 1

            safe_title = html.escape(title)
            safe_date = html.escape(event_date)
            safe_account = html.escape(account, quote=True)
            safe_payer = html.escape(payer, quote=True)

            template = (ROOT / "stranka-sablona.html").read_text(encoding="utf-8")
            page = template.replace("{{TITULEK}}", safe_title)
            page = page.replace("{{UCET}}", safe_account)
            page = page.replace("{{PLATCE}}", safe_payer)
            page = page.replace("{{CHECKLIST_HEADERS}}", participant_headers)
            page = page.replace("{{CHECKLIST_ROWS}}", checklist_rows_html)
            page = page.replace("{{DATUM}}", safe_date or "neuvedeno")

            if settings:
                save_github_page(settings[0], settings[1], filename, page)
            else:
                page_file.write_text(page, encoding="utf-8")

            self.send_json(201, {"path": "/Akce/" + filename})

        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "Požadavek obsahuje neplatná data."})
        except GithubApiError as error:
            status = f" ({error.status})" if error.status else ""
            self.send_json(
                502,
                {"error": f"GitHub odmítl požadavek{status}: {error}"},
            )
        except OSError as error:
            self.send_json(500, {"error": "Soubor se nepodařilo uložit: " + str(error)})
        except Exception:
            logging.exception("Unexpected error while creating an event page")
            self.send_json(502, {"error": "Akci se nepodařilo uložit do GitHubu."})

    def save_shared_counter_changes(self, event_slug):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Požadavek na sdílení není platný."})
            return
        if length <= 0 or length > 50000:
            self.send_json(400, {"error": "Požadavek na sdílení není platný."})
            return

        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "Požadavek na sdílení obsahuje neplatná data."})
            return
        if not isinstance(data, dict):
            self.send_json(400, {"error": "Požadavek na sdílení není platný."})
            return

        initial_seed = isinstance(data.get("values"), dict)
        if initial_seed:
            values = data["values"]
            if len(values) > 500:
                self.send_json(400, {"error": "Požadavek obsahuje příliš mnoho počítadel."})
                return
        else:
            values = {data.get("cell_key"): data.get("value")}

        valid_values = all(
            isinstance(cell_key, str)
            and re.fullmatch(r"\d{1,5}:\d{1,4}", cell_key)
            and isinstance(value, str)
            and (
                value == ""
                or (
                    value.isascii()
                    and value.isdigit()
                    and len(value) <= 3
                    and int(value) <= 999
                )
            )
            for cell_key, value in values.items()
        )
        if not values or not valid_values:
            self.send_json(400, {"error": "Hodnota počítadla není platná."})
            return

        try:
            save_shared_counters(event_slug, values, ignore_duplicates=initial_seed)
            self.send_json(200, {"saved": True})
        except SupabaseApiError as error:
            self.send_json(503, {"error": str(error)})
        except Exception:
            logging.exception("Unexpected error while saving shared counters")
            self.send_json(502, {"error": "Sdílené počítadlo se nepodařilo uložit."})

    def create_qr(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "Požadavek QR platby není platný."})
            return
        if length <= 0 or length > 10000:
            self.send_json(400, {"error": "Požadavek QR platby není platný."})
            return

        try:
            data = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "Požadavek QR platby obsahuje neplatná data."})
            return
        if not isinstance(data, dict):
            self.send_json(400, {"error": "Požadavek QR platby musí obsahovat údaje platby."})
            return

        try:
            payload = build_spayd_payload(
                data.get("account"),
                data.get("amount_halere"),
                data.get("reference"),
            )
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return

        svg = make_qr_svg(payload)
        self.send_response(200)
        self.send_header("Content-Type", "image/svg+xml; charset=utf-8")
        self.send_header("Content-Length", str(len(svg)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(svg)


if __name__ == "__main__":
    PAGES_DIR.mkdir(exist_ok=True)
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), ProjectHandler)
    print(f"Server běží na portu {port}.")
    print("Server zastavíš stisknutím Ctrl+C.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer ukončen.")
    finally:
        server.server_close()