import time
import random
import json
import urllib.parse
import threading
import requests
from datetime import datetime
from requests.exceptions import HTTPError, RequestException
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn
from rich.text import Text
from rich import box

class GameDisplay:
    def __init__(self):
        self.console = Console()
        self.is_playing = False
        self.current_status = "Idle"
        self.blink_thread = None
        self.stop_blinking = False

    def create_header(self):
        return Panel(
            "[bold cyan]Tokoplay Bot[/bold cyan]\n"
            f"[grey70]Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}[/grey70]",
            box=box.ROUNDED,
            border_style="blue"
        )

    def create_status_table(self, stats):
        table = Table(box=box.ROUNDED, border_style="cyan", show_header=False)
        table.add_column("Parameter", style="white", width=15)
        table.add_column("Value", style="green", justify="right")

        for key, value in stats.items():
            table.add_row(key, str(value))

        return Panel(table, title="[bold cyan]GAME STATUS", border_style="cyan")

    def create_game_progress(self):
        return Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(complete_style="green", finished_style="green"),
            TimeElapsedColumn(),
            console=self.console
        )

    def update_display(self, stats):
        self.console.clear()
        self.console.print(self.create_header())
        self.console.print(self.create_status_table(stats))

class TokoplayAPI:
    def __init__(self, config_file='config.json'):
        self.display = GameDisplay()
        self.config = self._load_config(config_file)
        self.base_url = self.config.get("base_url", "https://play.tokopedia.com/api")
        self.token_file = self.config.get("token_file", 'tokens.json')
        self.token = self._load_token()
        self.user_id = self._extract_user_id()
        self.headers = self._initialize_headers()
        self.stats = {
            "Energy": 0,
            "Total Games": 0,
            "Last Score": "N/A",
            "Multiplier": "N/A",
            "Total Points": 0,
            "Last Update": "Never"
        }
        self.update_energy()

    def _load_config(self, file_path):
        try:
            with open(file_path, 'r') as file:
                return json.load(file)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            self.display.console.print(f"[red]Error loading configuration: {e}[/red]")
            return {}

    def _load_token(self):
        try:
            with open(self.token_file, 'r') as file:
                data = json.load(file)
            return data.get('token')
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def _save_token(self, token):
        try:
            with open(self.token_file, 'w') as file:
                json.dump({'token': token}, file)
            return True
        except Exception as e:
            self.display.console.print(f"[red]Failed to save token: {e}[/red]")
            return False

    def _extract_user_id(self):
        try:
            with open('data.txt', 'r') as file:
                data = file.read().strip()
            parsed_data = urllib.parse.parse_qs(data)
            user_info = json.loads(parsed_data['user'][0])
            return user_info['id']
        except Exception as e:
            self.display.console.print(f"[red]Error extracting User ID: {e}[/red]")
            return None

    def _initialize_headers(self):
        headers = {
            "sec-ch-ua-platform": "Android",
            "user-agent": self.config.get("user_agent", "Mozilla/5.0"),
            "accept": "application/json, text/plain, */*",
            "sec-fetch-site": "same-origin",
            "sec-fetch-mode": "cors",
            "sec-fetch-dest": "empty",
            "referer": self.config.get("referer", "https://play.tokopedia.com"),
            "accept-encoding": "gzip, deflate, br, zstd",
            "accept-language": "en,en-AU;q=0.9,en-US;q=0.8",
        }
        if self.token:
            headers['authorization'] = self.token
        return headers

    def _request(self, method, endpoint, params=None, data=None, retry_count=0):
        if retry_count >= 3:
            self.display.console.print("[red]Maximum retry attempts reached[/red]")
            return None

        if not self.token:
            self.update_token()

        url = f"{self.base_url}/{endpoint}"
        try:
            if method.lower() == 'get':
                response = requests.get(url, headers=self.headers, params=params)
            elif method.lower() == 'post':
                response = requests.post(url, headers=self.headers, json=data)
            else:
                raise ValueError("Unsupported HTTP method")

            response.raise_for_status()
            return response.json()
        except HTTPError as http_err:
            if http_err.response.status_code == 401:
                self.update_token()
                return self._request(method, endpoint, params, data, retry_count + 1)
            self.display.console.print(f"[red]HTTP error: {http_err}[/red]")
        except Exception as e:
            self.display.console.print(f"[red]Request error: {e}[/red]")
        return None

    def update_token(self):
        try:
            with open('data.txt', 'r') as file:
                init_data_raw = file.read().strip()

            response = self._request('get', 'user/getToken',
                                  params={"initDataRaw": init_data_raw, "platform": "TOKO"})

            if response and response.get('status') == 'OK':
                self.token = response['data']['token']
                self.headers['authorization'] = self.token
                if self._save_token(self.token):
                    self.display.console.print("[green]Token updated successfully[/green]")
                    return True
        except Exception as e:
            self.display.console.print(f"[red]Token update failed: {e}[/red]")
        return False

    def update_energy(self):
        try:
            response = self._request('get', 'game/getUserGameInfo',
                params={
                    "userId": self.user_id,
                    "gameId": 1,
                    "platform": "TOKO"
                }
            )
            if response and response.get('status') == 'OK':
                self.stats["Energy"] = response["data"].get("userCurrentEnergy", 0)
                self.stats["Last Update"] = datetime.now().strftime("%H:%M:%S")
                return True
        except Exception as e:
            self.display.console.print(f"[red]Failed to update energy: {e}[/red]")
        return False

    def play_game(self, game_id, score, multiplier):
        self.display.console.print(f"[cyan]Starting game with score {score} and multiplier {multiplier}[/cyan]")

        with self.display.create_game_progress() as progress:
            game_task = progress.add_task("[cyan]Playing game...", total=60)

            for _ in range(60):
                time.sleep(1)
                progress.update(game_task, advance=1)
                if _ % 5 == 0:
                    self.update_energy()
                    self.display.update_display(self.stats)

        response = self._request('post', 'game/playGameGetReward', data={
            "categories": "Matches",
            "userId": self.user_id,
            "platform": "TOKO",
            "gameId": game_id,
            "score": score,
            "multiplier": multiplier
        })

        if response and response.get('status') == 'OK':
            self.stats["Total Games"] += 1
            self.stats["Last Score"] = score
            self.stats["Multiplier"] = multiplier
            if 'data' in response:
                self.stats["Energy"] = response['data'].get('userCurrentEnergy', self.stats["Energy"])
                points = score
                self.stats["Total Points"] += points
                self.display.console.print(f"[green]Game completed! Points earned: {points}[/green]")
            return True
        return False

def main():
    console = Console()
    console.clear()

    try:
        api_client = TokoplayAPI()
        game_id = 1

        while True:
            try:
                api_client.update_energy()
                api_client.display.update_display(api_client.stats)

                if api_client.stats["Energy"] <= 0:
                    console.print("[yellow]Energy depleted, waiting for recharge...[/yellow]")
                    with Progress() as progress:
                        wait_task = progress.add_task("[yellow]Waiting for energy...", total=10800)
                        while not progress.finished:
                            time.sleep(1)
                            progress.update(wait_task, advance=1)
                            if int(progress.tasks[0].completed) % 300 == 0:
                                if api_client.update_energy() and api_client.stats["Energy"] > 0:
                                    console.print("[green]Energy recharged![/green]")
                                    break
                        if api_client.stats["Energy"] <= 0:
                            continue

                score = random.randint(170, 200)
                multiplier = "1"

                if api_client.play_game(game_id, score, multiplier):
                    wait_time = random.randint(5, 10)
                    with Progress() as progress:
                        wait_task = progress.add_task("[cyan]Preparing next game...", total=wait_time)
                        while not progress.finished:
                            time.sleep(1)
                            progress.update(wait_task, advance=1)
                else:
                    console.print("[red]Game play failed, retrying in 30 seconds...[/red]")
                    time.sleep(30)

            except Exception as e:
                console.print(f"[red]Game error: {e}[/red]")
                time.sleep(30)

    except KeyboardInterrupt:
        console.print("\n[yellow]Bot stopped by user[/yellow]")
    except Exception as e:
        console.print(f"[red]Critical error: {e}[/red]")

if __name__ == "__main__":
    main()
